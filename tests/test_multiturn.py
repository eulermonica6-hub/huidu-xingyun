"""多轮指代与证据包导出的离线测试。"""

from __future__ import annotations

from huidu_xingyun.agent import export_evidence_package, history_entry, run_agent_verbose
from huidu_xingyun.agent.nodes import _has_backward_reference
from huidu_xingyun.schemas.response import EvidenceCard, FinalResponse


def test_backward_reference_detected() -> None:
    assert _has_backward_reference("它和哪些经典有关？") is True
    assert _has_backward_reference("星云大师连接了哪些机构？") is False


def test_multiturn_carryover(ctx) -> None:
    # 第一轮解析出上一轮实体。
    _, state1 = run_agent_verbose(ctx, "星云大师连接了哪些机构？")
    assert state1["resolved_entities"]

    history = [history_entry("星云大师连接了哪些机构？", state1)]
    # 第二轮用「它」回指，应把上一轮实体带入。
    _, state2 = run_agent_verbose(ctx, "它和哪些经典有关？", conversation_context=history)
    names = [e.name for e in state2["resolved_entities"]]
    assert any("星雲" in name or "星云" in name for name in names)


def test_history_entry_serializes_resolved(ctx) -> None:
    _, state = run_agent_verbose(ctx, "星云大师连接了哪些机构？")
    entry = history_entry("星云大师连接了哪些机构？", state)
    assert "query" in entry
    assert "entities" in entry
    assert all("name" in e and "entity_id" in e for e in entry["entities"])


def test_export_evidence_package(paths) -> None:
    final = FinalResponse(
        answer="示例结论",
        evidence_cards=[
            EvidenceCard(
                evidence_id="ev_1",
                layer="A",
                article_title="示例文章",
                volume="示例卷",
                quote="示例原文",
                url="https://example.com",
            )
        ],
        coverage_notice="结论基于：稳定关系（A 层）。",
        trace_id="test123",
    )
    path = export_evidence_package(final, paths)
    assert path.exists()
    path.unlink(missing_ok=True)