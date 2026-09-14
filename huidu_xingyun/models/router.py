"""模型路由：角色规格 + 主备回退执行。

角色分工（延迟/能力双轴）与回退语义在此单一文件中声明，便于评审与离线单测：
- ``ROLE_SPECS`` —— 每个角色的温度、是否缓存、用途；
- :func:`invoke_with_fallback` —— 主模型瞬时错误重试、硬错误/穷尽切兜底、结果回填缓存。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cache import LLMCache, _prompt_text, cache_key
from .retry import retry_transient


@dataclass(frozen=True)
class RoleSpec:
    role: str
    temperature: float
    cache: bool
    purpose: str


ROLE_SPECS: dict[str, RoleSpec] = {
    "router": RoleSpec("router", 0.0, True, "意图分类——延迟优先"),
    "reasoner": RoleSpec("reasoner", 0.1, False, "证据内归纳——质量优先"),
    "verifier": RoleSpec("verifier", 0.0, True, "逐句审校——确定性优先"),
    "fallback": RoleSpec("fallback", 0.1, False, "跨 Provider 兜底"),
}


def _content(response: Any) -> str:
    return response.content if hasattr(response, "content") else str(response)


def invoke_with_fallback(
    primary: Any,
    fallback: Any,
    messages: list[Any],
    *,
    cache_role: str | None = None,
    cache: LLMCache | None = None,
) -> str:
    """执行一次模型调用。

    规则：主模型瞬时错误（限流/网络/内容过滤）由 ``retry_transient`` 原地重试；
    遇到硬错误或重试穷尽，则切换到兜底模型再试一次；兜底也失败则向上抛出，
    由编排节点 try/except 降级为离线/规则回答，绝不在此吞错。
    """
    if primary is None:
        raise RuntimeError(f"model for role {cache_role or 'reasoner'} is not configured")
    prompt = _prompt_text(messages)
    if cache_role is not None and cache is not None:
        key = cache_key(cache_role, prompt)
        hit = cache.get(key)
        if hit is not None:
            return hit

    try:
        output = _content(retry_transient(lambda: primary.invoke(messages)))
    except Exception:  # noqa: BLE001 - 主模型不可用，此时正好由兜底接管
        if fallback is None:
            raise
        output = _content(retry_transient(lambda: fallback.invoke(messages)))

    if cache_role is not None and cache is not None:
        cache.set(cache_key(cache_role, prompt), output)
    return output