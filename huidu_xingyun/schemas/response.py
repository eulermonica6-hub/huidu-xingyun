"""最终响应结构化合同（对应编排蓝图「输出合同」）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceCard(BaseModel):
    evidence_id: str
    layer: str
    article_title: str = ""
    volume: str = ""
    quote: str = ""
    url: str = ""
    paragraph_uid: str = ""


class GraphPath(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)


class FollowUpAction(BaseModel):
    label: str
    kind: str = "default"


class SentenceVerification(BaseModel):
    sentence: str
    has_evidence: bool
    evidence_ids: list[str] = Field(default_factory=list)
    issue: str = ""


class VerificationResult(BaseModel):
    passes: bool
    sentence_checks: list[SentenceVerification] = Field(default_factory=list)
    summary: str = ""


class FinalResponse(BaseModel):
    answer: str
    evidence_cards: list[EvidenceCard] = Field(default_factory=list)
    graph_paths: list[GraphPath] = Field(default_factory=list)
    contextual_claims: list[str] = Field(default_factory=list)
    coverage_notice: str = ""
    defense_notice: str = ""
    follow_up_actions: list[FollowUpAction] = Field(default_factory=list)
    route: str = ""
    trace_id: str = ""
