"""Provider 模型工厂与角色装配。

模型 ID 通过 ``Settings`` 的 ``HUIDU_*_MODEL`` 环境变量注入，编排图不感知具体模型；
密钥由 :class:`~huidu_xingyun.config.secrets.SecretLoader` 提供，仅存内存。
角色分工与温度见 :data:`~huidu_xingyun.models.router.ROLE_SPECS`；
主模型失败时按兜底模型切换，见 :func:`~huidu_xingyun.models.router.invoke_with_fallback`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from ..config.secrets import SecretLoader
from ..config.settings import Settings
from .cache import LLMCache
from .router import ROLE_SPECS, invoke_with_fallback


def build_chat_model(
    provider: str, model: str, api_key: str, temperature: float
) -> BaseChatModel:
    """Provider 中性构建器：把角色无关的 ChatModel 构建收敛到一处。"""
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(model=model, api_key=api_key, temperature=temperature)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=api_key, temperature=temperature)
    if provider == "nvapi":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(model=model, api_key=api_key, temperature=temperature)
    if provider == "zhipu":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            temperature=temperature,
        )
    if provider == "ali":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=temperature,
        )
    raise RuntimeError(f"unsupported provider {provider!r}")


class ModelFactory:
    def __init__(self, settings: Settings, secrets: SecretLoader) -> None:
        self._settings = settings
        self._secrets = secrets

    def _provider_model(self, role: str) -> tuple[str, str]:
        if role == "router":
            return self._settings.router_provider, self._settings.router_model
        if role == "reasoner":
            return self._settings.reasoner_provider, self._settings.reasoner_model
        if role == "verifier":
            return self._settings.verifier_provider, self._settings.verifier_model
        if role == "fallback":
            return self._settings.fallback_provider, self._settings.fallback_model
        raise ValueError(f"unknown role {role!r}")

    def _api_key_for(self, provider: str) -> str:
        api_key = self._secrets.first_key(provider)
        if not api_key:
            raise RuntimeError(f"provider {provider!r} has no API key in the secret file")
        return api_key

    def chat(self, role: str) -> BaseChatModel:
        provider, model = self._provider_model(role)
        if not model:
            raise RuntimeError(
                f"role {role!r} provider {provider!r} has no model ID set; "
                "run scripts/probe_models.py first"
            )
        temperature = ROLE_SPECS[role].temperature
        return build_chat_model(provider, model, self._api_key_for(provider), temperature)

    def chat_fallback(self) -> BaseChatModel | None:
        """构建全局兜底模型；未配置或不可用时返回 None（禁用兜底，不阻断主链）。"""
        provider, model = self._provider_model("fallback")
        if not model:
            return None
        try:
            temperature = ROLE_SPECS["fallback"].temperature
            return build_chat_model(provider, model, self._api_key_for(provider), temperature)
        except Exception:  # noqa: BLE001 - 兜底可选，失败静默禁用
            return None

    def structured(self, role: str, schema: type[BaseModel]) -> BaseChatModel:
        return self.chat(role).with_structured_output(schema)

    def build_bundle(self, cache: LLMCache | None = None) -> "ModelBundle":
        return ModelBundle(
            router=self.chat("router"),
            reasoner=self.chat("reasoner"),
            verifier=self.chat("verifier"),
            fallback=self.chat_fallback(),
            cache=cache,
        )


@dataclass
class ModelBundle:
    """三个角色的主模型 + 共享兜底模型，参数与方法见各调用处。

    可靠性：主备回退与缓存统一在
    :func:`~huidu_xingyun.models.router.invoke_with_fallback` 中执行。
    三个方法都返回纯文本；结构化输出由意图/审校节点用
    :func:`~huidu_xingyun.agent.parsing.parse_json_object` 解析，避免依赖
    各 Provider 不一致的 JSON 模式。
    """

    router: Any = None
    reasoner: Any = None
    verifier: Any = None
    fallback: Any = None
    cache: LLMCache | None = None

    def _invoke(self, model: Any, messages: list[Any], cache_role: str | None) -> str:
        return invoke_with_fallback(
            model, self.fallback, messages, cache_role=cache_role, cache=self.cache
        )

    def classify(self, messages: list[Any]) -> str:
        return self._invoke(self.router, messages, "router")

    def generate(self, messages: list[Any]) -> str:
        return self._invoke(self.reasoner, messages, None)

    def verify(self, messages: list[Any]) -> str:
        return self._invoke(self.verifier, messages, "verifier")