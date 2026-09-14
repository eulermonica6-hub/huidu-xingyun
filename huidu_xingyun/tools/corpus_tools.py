"""全文检索工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..repositories.corpus import CorpusRepository


def build_corpus_tools(corpus: CorpusRepository) -> list:
    @tool
    def search_corpus(query: str, k: int = 8) -> str:
        """关键词检索全文与文章元数据，返回带出处片段的候选文章。"""
        results = corpus.search(query, k=k)
        return json.dumps(results, ensure_ascii=False)

    return [search_corpus]
