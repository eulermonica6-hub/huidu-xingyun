"""Provider 在线能力探测。

每个候选模型通过基础对话、Pydantic 结构化输出、工具调用和中文意图分类四项后，
才算具备进入正式路由的资格（呼应 `03_model_and_secret_policy.md` 的上线前探测）。
错误信息只记录异常类型，绝不包含密钥或完整请求体。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import BaseModel, Field

CANDIDATE_MODELS: dict[str, list[str]] = {
    "deepseek": ["deepseek-chat"],
    "zhipu": ["glm-4-flash", "glm-4.6", "glm-4.5", "glm-4-plus"],
    "ali": ["qwen-plus", "qwen-flash", "qwen-turbo"],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen-2.5-32b",
    ],
    "nvapi": [
        "meta/llama-3.3-70b-instruct",
        "nvidia/llama-3.1-nemotron-70b-instruct",
    ],
}


class ProbeSample(BaseModel):
    label: str = Field(description="分类标签")
    confidence: float = Field(description="0到1置信度")


class ProbeTestResult(BaseModel):
    ok: bool
    latency_ms: int = 0
    error: str = ""


def _err(exc: Exception) -> str:
    return type(exc).__name__


def _run(fn: Callable[[], Any]) -> ProbeTestResult:
    start = time.perf_counter()
    try:
        fn()
        return ProbeTestResult(ok=True, latency_ms=round((time.perf_counter() - start) * 1000))
    except Exception as exc:  # noqa: BLE001 - 探测需捕获全部异常
        return ProbeTestResult(
            ok=False,
            latency_ms=round((time.perf_counter() - start) * 1000),
            error=_err(exc),
        )


def _chat_model(provider: str, model: str, api_key: str) -> Any:
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(model=model, api_key=api_key, temperature=0)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=api_key, temperature=0)
    if provider == "nvapi":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(model=model, api_key=api_key, temperature=0)
    if provider == "zhipu":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            temperature=0,
        )
    if provider == "ali":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0,
        )
    raise ValueError(f"unsupported provider {provider!r}")


def probe_model(provider: str, model: str, api_key: str) -> dict[str, Any]:
    result: dict[str, Any] = {"provider": provider, "model": model, "tests": {}}

    try:
        llm = _chat_model(provider, model, api_key)
    except Exception as exc:  # noqa: BLE001
        result["tests"]["construct"] = ProbeTestResult(ok=False, error=_err(exc)).model_dump()
        result["passed"] = False
        return result

    result["tests"]["chat"] = _run(
        lambda: llm.invoke("用一句话说明什么是人间佛教。")
    ).model_dump()

    def _structured() -> None:
        structured = llm.with_structured_output(ProbeSample)
        obj = structured.invoke("把「慈悲是佛教核心教义」这句话分类。")
        if not isinstance(obj, ProbeSample):
            raise AssertionError("structured output returned wrong type")

    result["tests"]["structured"] = _run(_structured).model_dump()

    def _tool_calling() -> None:
        from langchain_core.tools import tool

        @tool
        def add_numbers(a: int, b: int) -> int:
            """把两个整数相加。"""
            return a + b

        bound = llm.bind_tools([add_numbers])
        response = bound.invoke("请用工具计算 2 加 3 的结果。")
        if not getattr(response, "tool_calls", None):
            raise AssertionError("model did not issue a tool call")

    result["tests"]["tool_calling"] = _run(_tool_calling).model_dump()

    def _chinese_intent() -> None:
        from ..schemas.intent import IntentResult

        structured = llm.with_structured_output(IntentResult)
        obj = structured.invoke("《维摩经》如何连接到人间佛教实践？")
        if not isinstance(obj, IntentResult) or not obj.entities:
            raise AssertionError("chinese intent classification failed")

    result["tests"]["chinese_intent"] = _run(_chinese_intent).model_dump()

    result["passed"] = all(t.get("ok") for t in result["tests"].values())
    return result
