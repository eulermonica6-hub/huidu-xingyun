"""离线端到端与密钥加载的固定用例。"""

from __future__ import annotations

from huidu_xingyun.agent import run_agent
from huidu_xingyun.config import SecretLoader, get_settings, redact


def test_offline_pipeline_relation_query(ctx):
    final = run_agent(ctx, "慈悲与教育是什么关系")
    assert final.route == "graph_direct"
    assert final.answer
    assert final.evidence_cards


def test_offline_pipeline_general_chat(ctx):
    final = run_agent(ctx, "怎么使用这个系统")
    assert final.route == "llm_direct"
    assert "不来自《星云大师全集》语料" in final.coverage_notice


def test_secret_loader_zhipu():
    loader = SecretLoader(get_settings().secret_path)
    loader.load()
    assert "zhipu" in loader.labels
    keys = loader.keys_for("zhipu")
    assert keys and keys[0]  # 只断言存在且非空，不检查具体值


def test_redact():
    assert redact("sk-abc123-def456") == "***"
    assert redact("nvapi-XYZ_123") == "***"
    assert "gsk_" not in redact("gsk_secretvalue")
