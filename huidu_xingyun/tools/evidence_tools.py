"""证据与原文工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..repositories.corpus import CorpusRepository
from ..repositories.graph import GraphRepository


def build_evidence_tools(graph: GraphRepository, corpus: CorpusRepository) -> list:
    @tool
    def get_relation_evidence(relation_id: str) -> str:
        """返回某条稳定关系关联的原文证据记录。"""
        return json.dumps(graph.get_relation_evidence(relation_id), ensure_ascii=False)

    @tool
    def get_article_metadata(document_id: str) -> str:
        """返回文章元数据（标题、分类、书目、原文链接）。"""
        doc = corpus.get(document_id)
        return json.dumps(doc or {}, ensure_ascii=False)

    @tool
    def get_source_passage(document_id: str) -> str:
        """返回文章正文原文。"""
        return corpus.get_text(document_id)

    return [get_relation_evidence, get_article_metadata, get_source_passage]
