"""可靠层（重试与缓存）离线测试。"""

from __future__ import annotations

from huidu_xingyun.models.cache import LLMCache, cache_key
from huidu_xingyun.models.retry import is_transient, retry_transient


class _StatusCodeError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"status {status_code}")


def test_is_transient_recognizes_retryable() -> None:
    assert is_transient(_StatusCodeError(429)) is True
    assert is_transient(_StatusCodeError(503)) is True
    assert is_transient(type("ConnectionError", (Exception,), {})()) is True
    assert is_transient(_StatusCodeError(400)) is False
    assert is_transient(_StatusCodeError(401)) is False


def test_retry_transient_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _StatusCodeError(429)
        return "ok"

    assert retry_transient(flaky, retries=3, backoff=(0.0, 0.0, 0.0), sleep=lambda _: None) == "ok"
    assert calls["n"] == 3


def test_retry_transient_reraise_non_transient() -> None:
    def boom():
        raise _StatusCodeError(401)

    import pytest

    with pytest.raises(_StatusCodeError):
        retry_transient(boom, retries=3, backoff=(0.0, 0.0), sleep=lambda _: None)


def test_cache_roundtrip(tmp_path) -> None:
    cache = LLMCache(tmp_path / "cache.jsonl")
    key = cache_key("router", "some prompt")
    assert cache.get(key) is None
    cache.set(key, "答案")
    assert cache.get(key) == "答案"
    # 重新实例化，磁盘持久化可读回。
    cache2 = LLMCache(tmp_path / "cache.jsonl")
    assert cache2.get(key) == "答案"


def test_cache_key_deterministic() -> None:
    assert cache_key("router", "你好") == cache_key("router", "你好")
    assert cache_key("router", "你好") != cache_key("verifier", "你好")