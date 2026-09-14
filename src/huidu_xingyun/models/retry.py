"""LLM 瞬时错误重试：限流、网络、网关超时、内容过滤等可恢复错误短退避重试。

设计原则：只在「同一请求下次可能成功」的错误上重试，绝不吞掉可判定失败
（如鉴权错误、参数错误、模型不存在）。错误信息只记录异常类型与状态码，
不包含密钥或完整请求体。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_DEFAULT_BACKOFF = (0.5, 1.5, 3.0)


def is_transient(exc: BaseException) -> bool:
    """判断异常是否属于可重试的瞬时错误。"""
    status = getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    if status == 400:
        # 智谱/阿里等内容安全过滤（1301）是间歇性的，重试可能通过。
        raw = str(
            getattr(exc, "body", None)
            or getattr(exc, "response", None)
            or getattr(exc, "message", "")
            or exc
        )
        return "1301" in raw or "contentFilter" in raw or "content_filter" in raw
    name = type(exc).__name__
    return any(
        marker in name
        for marker in (
            "Connection",
            "Timeout",
            "RateLimit",
            "ServerError",
            "InternalServer",
            "SSL",
            "EOF",
            "ChunkedEncoding",
            "Protocol",
            "Reset",
            "RemoteDisconnected",
        )
    )


def retry_transient(
    fn: Callable[[], T],
    retries: int = 3,
    backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """执行 ``fn``，瞬时错误按退避序列重试；仍失败则抛出最后一次异常。"""
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 由 is_transient 判定是否重试
            last_exc = exc
            if not is_transient(exc) or attempt == retries - 1:
                raise
            delay = backoff[attempt] if attempt < len(backoff) else backoff[-1]
            sleep(delay)
    assert last_exc is not None  # 理论上不可达，保险起见
    raise last_exc