"""在线能力探测脚本。

对候选模型依次执行：基础对话、JSON 结构化输出（提示词驱动）、工具调用，
结果写入 ``data/derived/model_probe_report.json``。密钥从外部秘密文件加载，
绝不明文打印。

用法（在项目根目录）：:

    python scripts/probe_models.py --provider zhipu
    python scripts/probe_models.py --provider zhipu --write-env
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from huidu_xingyun.agent.parsing import parse_json_object
from huidu_xingyun.config import SecretLoader, get_runtime_paths, get_settings
from huidu_xingyun.models.probe import CANDIDATE_MODELS, _chat_model
from huidu_xingyun.schemas.intent import IntentResult

INTENT_JSON_PROMPT = (
    "你是意图路由器。只输出一个 JSON 对象，字段：primary_intent（取值 ENTITY_EXPLAIN、"
    "RELATION_QUERY、PATH_QUERY、SOURCE_SEARCH、COMPARATIVE_ANALYSIS、GRAPH_ANALYTICS、"
    "READING_GUIDE、RESEARCH_ASSIST、GENERAL_CHAT、FEEDBACK_REVIEW、OUT_OF_SCOPE）、"
    "entities（数组，元素含 mention 与 candidate_type）、confidence（0到1浮点）。"
)


def _latency_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def test_chat(llm) -> dict:
    start = time.perf_counter()
    try:
        resp = llm.invoke("用一句话说明什么是人间佛教。")
        ok = bool((getattr(resp, "content", "") or "").strip())
        return {"ok": ok, "latency_ms": _latency_ms(start)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_ms": _latency_ms(start), "error": type(exc).__name__}


def test_json_intent(llm) -> dict:
    start = time.perf_counter()
    try:
        text = llm.invoke(
            [
                SystemMessage(content=INTENT_JSON_PROMPT),
                HumanMessage(content="《维摩经》如何连接到人间佛教实践？"),
            ]
        ).content
        obj = parse_json_object(text, IntentResult)
        return {"ok": obj is not None and bool(obj.entities), "latency_ms": _latency_ms(start)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_ms": _latency_ms(start), "error": type(exc).__name__}


def test_tool_calling(llm) -> dict:
    @tool
    def add_numbers(a: int, b: int) -> int:
        """把两个整数相加。"""
        return a + b

    start = time.perf_counter()
    try:
        resp = llm.bind_tools([add_numbers]).invoke("请用工具计算 2 加 3。")
        return {"ok": bool(getattr(resp, "tool_calls", None)), "latency_ms": _latency_ms(start)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_ms": _latency_ms(start), "error": type(exc).__name__}


def probe(provider: str, model: str, api_key: str) -> dict:
    result = {"provider": provider, "model": model, "tests": {}}
    try:
        llm = _chat_model(provider, model, api_key)
    except Exception as exc:  # noqa: BLE001
        result["tests"]["construct"] = {"ok": False, "error": type(exc).__name__}
        result["passed"] = False
        return result
    result["tests"]["chat"] = test_chat(llm)
    result["tests"]["json_intent"] = test_json_intent(llm)
    result["tests"]["tool_calling"] = test_tool_calling(llm)
    result["passed"] = all(t.get("ok") for t in result["tests"].values())
    return result


def _update_env_model(model: str) -> None:
    env_path = PROJECT_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    targets = {
        "HUIDU_ROUTER_MODEL": f"HUIDU_ROUTER_MODEL={model}",
        "HUIDU_REASONER_MODEL": f"HUIDU_REASONER_MODEL={model}",
        "HUIDU_VERIFIER_MODEL": f"HUIDU_VERIFIER_MODEL={model}",
    }
    kept = [line for line in lines if line.split("=", 1)[0] not in targets]
    kept.extend(targets.values())
    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="在线能力探测")
    parser.add_argument("--provider", default="zhipu")
    parser.add_argument("--write-env", action="store_true", help="把首个通过的模型写回 .env")
    args = parser.parse_args()

    settings = get_settings()
    paths = get_runtime_paths()
    loader = SecretLoader(settings.secret_path)
    loader.load()
    api_key = loader.first_key(args.provider)
    if not api_key:
        print(f"未在秘密文件中找到 {args.provider} 的密钥。")
        return 1

    candidates = CANDIDATE_MODELS.get(args.provider, [])
    if not candidates:
        print(f"provider {args.provider!r} 没有候选模型。")
        return 1

    report: dict = {"provider": args.provider, "results": []}
    first_passed = None
    for model in candidates:
        entry = probe(args.provider, model, api_key)
        report["results"].append(entry)
        detail = "; ".join(f"{k}={'OK' if v.get('ok') else 'FAIL'}" for k, v in entry["tests"].items())
        print(f"[{'PASS' if entry['passed'] else 'FAIL'}] {model}  {detail}")
        if entry["passed"] and first_passed is None:
            first_passed = model

    paths.derived_root.mkdir(parents=True, exist_ok=True)
    report_path = paths.derived_root / "model_probe_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {report_path}")

    if first_passed:
        print(f"首个通过全部探测的模型：{first_passed}")
        if args.write_env:
            _update_env_model(first_passed)
            print(f"已把三个角色模型写入 {PROJECT_ROOT / '.env'}")
        return 0
    print("没有模型通过全部探测。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
