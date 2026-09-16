"""同步运行入口：一次调用跑完整个状态图并返回结构化响应。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config.settings import RuntimePaths
from ..schemas.response import FinalResponse
from .context import AgentContext
from .graph import build_graph


def run_agent(
    ctx: AgentContext,
    query: str,
    conversation_context: list[dict[str, Any]] | None = None,
) -> FinalResponse:
    final, _ = run_agent_verbose(ctx, query, conversation_context)
    return final


def run_agent_verbose(
    ctx: AgentContext,
    query: str,
    conversation_context: list[dict[str, Any]] | None = None,
) -> tuple[FinalResponse, dict[str, Any]]:
    graph = build_graph(ctx)
    result = graph.invoke(
        {"user_query": query, "conversation_context": conversation_context or []}
    )
    final = result.get("final_response")
    if final is None:
        final = FinalResponse(
            answer="（处理失败，请查看 runtime/logs/audit.jsonl。）",
            route=result.get("route", ""),
            trace_id=result.get("trace_id", ""),
        )
    return final, result


def history_entry(query: str, state: dict[str, Any]) -> dict[str, Any]:
    """从一次运行的状态构造下一轮会话上下文条目（只保留可跨轮复用的实体名）。"""
    entities = [
        {"name": e.name, "entity_id": e.entity_id, "entity_type": e.entity_type}
        for e in state.get("resolved_entities", [])
        if getattr(e, "resolved", False) and e.name
    ]
    return {"query": query, "entities": entities}


def export_evidence_package(final: FinalResponse, paths: RuntimePaths) -> Path:
    """把一次问答的最终响应导出为 Markdown 研究证据包，置于 ``outputs/``。"""
    lines = [f"# 研究证据包 · {final.trace_id}", ""]
    lines.append("## 结论")
    lines.append(final.answer.rstrip())
    lines.append("")
    if final.coverage_notice:
        lines.append(f"> 覆盖说明：{final.coverage_notice}")
        lines.append("")
    if final.defense_notice:
        lines.append(f"> 防御说明：{final.defense_notice}")
        lines.append("")
    if final.graph_paths:
        lines.append("## 关系路径")
        for path in final.graph_paths:
            lines.append("- " + " → ".join(path.nodes))
        lines.append("")
    if final.evidence_cards:
        lines.append("## 证据")
        for card in final.evidence_cards:
            title = f"{card.volume} {card.article_title}".strip()
            lines.append(f"### [{card.layer}] {title}")
            if card.quote:
                lines.append(f"> {card.quote}")
            if card.url:
                lines.append(f"出处：{card.url}")
            lines.append("")
    if final.follow_up_actions:
        lines.append("## 后续操作")
        lines.append("；".join(a.label for a in final.follow_up_actions))
        lines.append("")
    outputs_dir = paths.outputs
    outputs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = outputs_dir / f"evidence_{final.trace_id}_{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
