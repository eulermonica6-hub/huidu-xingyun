"""意图识别结构化输出契约。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentPrimary(str, Enum):
    ENTITY_EXPLAIN = "ENTITY_EXPLAIN"
    RELATION_QUERY = "RELATION_QUERY"
    PATH_QUERY = "PATH_QUERY"
    SOURCE_SEARCH = "SOURCE_SEARCH"
    COMPARATIVE_ANALYSIS = "COMPARATIVE_ANALYSIS"
    GRAPH_ANALYTICS = "GRAPH_ANALYTICS"
    READING_GUIDE = "READING_GUIDE"
    RESEARCH_ASSIST = "RESEARCH_ASSIST"
    GENERAL_CHAT = "GENERAL_CHAT"
    FEEDBACK_REVIEW = "FEEDBACK_REVIEW"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class EntityMention(BaseModel):
    mention: str
    candidate_type: str | None = None
    candidate_entity_id: str | None = None


class IntentResult(BaseModel):
    """LLM 意图分类的固定 JSON 输出。"""

    primary_intent: IntentPrimary
    secondary_intent: str = ""
    domain: str = "humanistic_buddhism"
    entities: list[EntityMention] = Field(default_factory=list)
    requires_graph: bool = False
    requires_corpus: bool = False
    requires_llm_reasoning: bool = False
    requires_statistics: bool = False
    answer_mode: str = "evidence_chain"
    need_clarification: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
