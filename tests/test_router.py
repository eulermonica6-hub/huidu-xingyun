"""模型路由（角色规格 + 主备回退）离线测试。"""

from __future__ import annotations

from huidu_xingyun.models.cache import LLMCache, _prompt_text, cache_key
from huidu_xingyun.models.router import ROLE_SPECS, invoke_with_fallback


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Transient(Exception):
    status_code = 429


class _Hard(Exception):
    status_code = 401


class _FakeModel:
    def __init__(self, content: str = "ok", transient_failures: int = 0, hard: bool = False) -> None:
        self.content = content
        self.calls = 0
        self._transient = transient_failures
        self._hard = hard

    def invoke(self, messages):
        self.calls += 1
        if self._hard:
            raise _Hard()
        if self.calls <= self._transient:
            raise _Transient()
        return _Msg(self.content)


def test_role_specs_complete() -> None:
    assert set(ROLE_SPECS) == {"router", "reasoner", "verifier", "fallback"}
    assert ROLE_SPECS["router"].cache is True
    assert ROLE_SPECS["reasoner"].cache is False
    assert ROLE_SPECS["verifier"].temperature == 0.0


def test_primary_succeeds_no_fallback() -> None:
    primary = _FakeModel(content="主")
    fallback = _FakeModel(content="兜底")
    assert invoke_with_fallback(primary, fallback, []) == "主"
    assert fallback.calls == 0


def test_hard_error_falls_back() -> None:
    primary = _FakeModel(hard=True)
    fallback = _FakeModel(content="兜底")
    assert invoke_with_fallback(primary, fallback, []) == "兜底"
    assert fallback.calls == 1


def test_both_fail_raises() -> None:
    import pytest

    with pytest.raises(Exception):
        invoke_with_fallback(_FakeModel(hard=True), _FakeModel(hard=True), [])


def test_cache_hit_short_circuits() -> None:
    primary = _FakeModel(content="主")
    cache = LLMCache()
    cache.set(cache_key("router", _prompt_text([])), "缓存")
    out = invoke_with_fallback(primary, None, [], cache_role="router", cache=cache)
    assert out == "缓存"
    assert primary.calls == 0