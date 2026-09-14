"""实体工具：规范化、消歧与别名扩展。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..repositories.graph import GraphRepository


def build_entity_tools(graph: GraphRepository) -> list:
    @tool
    def resolve_entities(mentions: list[str]) -> str:
        """把用户问题中的实体提及规范化为实体ID，含别名匹配与歧义提示。"""
        resolved = graph.resolve_entities(mentions)
        return json.dumps([r.model_dump() for r in resolved], ensure_ascii=False)

    @tool
    def expand_aliases(name: str) -> str:
        """列出某个实体名或别名对应的候选实体。"""
        resolved = graph.resolve_entities([name])
        return json.dumps([r.model_dump() for r in resolved], ensure_ascii=False)

    return [resolve_entities, expand_aliases]
