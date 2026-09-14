"""把节点装配为 LangGraph 状态图（对应编排蓝图「状态图」）。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..schemas.state import AgentState
from .context import AgentContext
from .nodes import build_nodes

_ROUTE_TARGETS = {
    "llm_direct": "generate_answer",
    "clarify_or_refuse": "generate_answer",
    "graph_direct": "graph_direct",
    "graph_retrieve": "graph_retrieve",
    "corpus_retrieve": "corpus_retrieve",
    "graph_analytics": "graph_analytics",
}

_RETRIEVAL_NODES = ("graph_direct", "graph_retrieve", "corpus_retrieve", "graph_analytics")


def build_graph(ctx: AgentContext):
    nodes = build_nodes(ctx)
    graph = StateGraph(AgentState)

    for name in (
        "normalize_input",
        "resolve_conversation_context",
        "classify_intent",
        "resolve_entities",
        "plan_route",
    ):
        graph.add_node(name, nodes[name])
    for name in (
        "graph_direct",
        "graph_retrieve",
        "corpus_retrieve",
        "graph_analytics",
        "llm_direct",
        "clarify_or_refuse",
        "fuse_evidence",
        "generate_answer",
        "verify_answer",
        "revise_answer",
        "format_response",
        "write_audit_log",
    ):
        graph.add_node(name, nodes[name])

    graph.add_edge(START, "normalize_input")
    graph.add_edge("normalize_input", "resolve_conversation_context")
    graph.add_edge("resolve_conversation_context", "classify_intent")
    graph.add_edge("classify_intent", "resolve_entities")
    graph.add_edge("resolve_entities", "plan_route")

    graph.add_conditional_edges(
        "plan_route",
        lambda state: state["route"],
        _ROUTE_TARGETS,
    )

    for name in _RETRIEVAL_NODES:
        graph.add_edge(name, "fuse_evidence")
    graph.add_edge("fuse_evidence", "generate_answer")
    graph.add_edge("generate_answer", "verify_answer")

    def after_verify(state: dict) -> str:
        result = state.get("verification_result") or {}
        if not result.get("passes") and state.get("revision_count", 0) < 1:
            return "revise_answer"
        return "format_response"

    graph.add_conditional_edges(
        "verify_answer",
        after_verify,
        {"revise_answer": "revise_answer", "format_response": "format_response"},
    )
    graph.add_edge("revise_answer", "verify_answer")
    graph.add_edge("format_response", "write_audit_log")
    graph.add_edge("write_audit_log", END)

    return graph.compile()
