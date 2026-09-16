"""LangGraph 主状态定义（对应编排蓝图「核心状态」）。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from .evidence import EvidenceItem, ResolvedEntity
from .intent import IntentResult
from .response import FinalResponse


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    conversation_context: list[dict[str, Any]]
    normalized_query: str
    intent: IntentResult
    resolved_entities: list[ResolvedEntity]
    carryover_names: list[str]
    graph_paths: list[dict[str, Any]]
    execution_plan: dict[str, Any]
    graph_results: list[dict[str, Any]]
    claim_results: list[dict[str, Any]]
    corpus_results: list[dict[str, Any]]
    evidence_items: list[EvidenceItem]
    draft_answer: str
    verification_result: dict[str, Any]
    final_response: FinalResponse
    d_layer: bool
    route: str
    errors: list[str]
    trace_id: str
    revision_count: int
