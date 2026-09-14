"""意图规则先验与路由映射。"""

from __future__ import annotations

import re
from typing import Any

from ..schemas.intent import IntentPrimary, IntentResult

# 顺序即优先级：先命中的规则胜出。
_RULES: list[tuple[IntentPrimary, re.Pattern[str]]] = [
    (IntentPrimary.SOURCE_SEARCH, re.compile(r"原文|出处|哪一篇|哪些文章|哪篇文章|引用|文章中")),
    (IntentPrimary.COMPARATIVE_ANALYSIS, re.compile(r"比较|区别|异同|差异|有什么不同|有何不同")),
    (IntentPrimary.PATH_QUERY, re.compile(r"路径|如何连接|如何联系|怎样连接|多跳|关联路径")),
    (IntentPrimary.GRAPH_ANALYTICS, re.compile(r"桥梁|中心性|统计|排名|社群|核心节点|承担.{0,8}作用")),
    (IntentPrimary.RELATION_QUERY, re.compile(r"什么关系|有何关系|有何联系|连接了|关系")),
    (IntentPrimary.READING_GUIDE, re.compile(r"阅读路线|阅读路径|导读|读书计划")),
    (IntentPrimary.RESEARCH_ASSIST, re.compile(r"研究问题|研究提纲|证据包|写一|生成一|帮我整理|论文")),
    (IntentPrimary.ENTITY_EXPLAIN, re.compile(r"什么是|是什么|如何理解|怎样理解|解释|含义|为什么|体现")),
    (IntentPrimary.FEEDBACK_REVIEW, re.compile(r"纠错|是不是反了|错了|修正|建议修改|复核")),
    (IntentPrimary.GENERAL_CHAT, re.compile(r"怎么用|如何使用|你好|谢谢|帮助|功能|你是谁")),
]

# 各一级意图的默认检索/推理需求。
PRIMARY_FLAGS: dict[IntentPrimary, tuple[bool, bool, bool, bool]] = {
    IntentPrimary.ENTITY_EXPLAIN: (True, True, True, False),
    IntentPrimary.RELATION_QUERY: (True, False, False, False),
    IntentPrimary.PATH_QUERY: (True, True, True, False),
    IntentPrimary.SOURCE_SEARCH: (False, True, False, False),
    IntentPrimary.COMPARATIVE_ANALYSIS: (True, True, True, False),
    IntentPrimary.GRAPH_ANALYTICS: (True, False, True, True),
    IntentPrimary.READING_GUIDE: (True, True, True, False),
    IntentPrimary.RESEARCH_ASSIST: (True, True, True, False),
    IntentPrimary.GENERAL_CHAT: (False, False, True, False),
    IntentPrimary.FEEDBACK_REVIEW: (False, False, False, False),
    IntentPrimary.OUT_OF_SCOPE: (False, False, True, False),
}


def rule_intent_hint(query: str) -> IntentPrimary | None:
    for primary, pattern in _RULES:
        if pattern.search(query):
            return primary
    return None


def rule_only_intent(query: str, hint: IntentPrimary | None) -> IntentResult:
    primary = hint or IntentPrimary.OUT_OF_SCOPE
    graph, corpus, llm, stats = PRIMARY_FLAGS[primary]
    return IntentResult(
        primary_intent=primary,
        secondary_intent="rule_prior",
        requires_graph=graph,
        requires_corpus=corpus,
        requires_llm_reasoning=llm,
        requires_statistics=stats,
        answer_mode="evidence_chain" if (graph or corpus) else "direct",
        confidence=0.85,
    )


# 有强特征词的一级意图：命中即纠正 LLM 分类，避免弱模型把「如何连接」判成关系查询等。
_STRONG_HINTS = {
    IntentPrimary.SOURCE_SEARCH,
    IntentPrimary.PATH_QUERY,
    IntentPrimary.COMPARATIVE_ANALYSIS,
    IntentPrimary.GRAPH_ANALYTICS,
    IntentPrimary.RELATION_QUERY,
    IntentPrimary.READING_GUIDE,
    IntentPrimary.RESEARCH_ASSIST,
    IntentPrimary.FEEDBACK_REVIEW,
}


def merge_with_rule_hint(intent: IntentResult, hint: IntentPrimary | None) -> IntentResult:
    """强信号规则直接纠正；弱信号仅在 LLM 低置信度时纠正。"""
    if hint is None or intent.primary_intent == hint:
        return intent
    if hint in _STRONG_HINTS or intent.confidence < 0.6:
        intent.primary_intent = hint
        intent.confidence = max(intent.confidence, 0.6)
    return intent


def _base_route(intent: IntentResult) -> str:
    primary = intent.primary_intent
    if primary in (IntentPrimary.GENERAL_CHAT, IntentPrimary.OUT_OF_SCOPE):
        return "llm_direct"
    if primary == IntentPrimary.FEEDBACK_REVIEW:
        return "clarify_or_refuse"
    if primary == IntentPrimary.GRAPH_ANALYTICS:
        return "graph_analytics"
    if primary == IntentPrimary.SOURCE_SEARCH:
        return "corpus_retrieve"
    if primary == IntentPrimary.RELATION_QUERY:
        return "graph_direct"
    return "graph_retrieve"


def route_for_intent(intent: IntentResult, resolved_entities: list[Any]) -> str:
    if intent.need_clarification:
        return "clarify_or_refuse"
    route = _base_route(intent)
    # 实体歧义只在「需要明确实体」的路由上强制澄清；指标计算与全文检索可继续。
    if route in ("graph_direct", "graph_retrieve") and any(
        getattr(entity, "is_ambiguous", False) for entity in resolved_entities
    ):
        return "clarify_or_refuse"
    return route
