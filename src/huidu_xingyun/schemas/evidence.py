"""四层证据体系与实体解析结果。

证据等级（呼应 roadmap 第六节）：

- ``A`` 稳定关系 + 直接原文证据；
- ``B`` Claim 语境命题 + 原文；
- ``C`` 全文检索片段，尚未进入图谱；
- ``D`` LLM 一般知识，不得冒充语料结论。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceLayer(str, Enum):
    STABLE = "A"
    CLAIM = "B"
    CORPUS = "C"
    GENERAL = "D"


class EntityCandidate(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    matched_alias: str = ""
    ambiguity_count: int = 1
    in_relation_graph: bool = False


class ResolvedEntity(BaseModel):
    entity_id: str = ""
    name: str
    entity_type: str = ""
    matched_alias: str = ""
    confidence: float = 1.0
    in_relation_graph: bool = False
    candidates: list[EntityCandidate] = Field(default_factory=list)

    @property
    def is_ambiguous(self) -> bool:
        return len(self.candidates) > 1

    @property
    def resolved(self) -> bool:
        return bool(self.entity_id)


class EvidenceItem(BaseModel):
    evidence_id: str
    layer: EvidenceLayer
    source: str = ""
    relation: str = ""
    target: str = ""
    article_title: str = ""
    volume: str = ""
    document_id: str = ""
    paragraph_uid: str = ""
    quote: str = ""
    url: str = ""
    article_support_count: int = 0
    reliability: str = ""


class EvidencePackage(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    graph_paths: list[list[str]] = Field(default_factory=list)
    coverage_notice: str = ""
