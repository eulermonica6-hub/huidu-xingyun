"""意图规则先验与路由映射测试。"""

from __future__ import annotations

from huidu_xingyun.agent.routing import route_for_intent, rule_intent_hint, rule_only_intent
from huidu_xingyun.schemas.intent import IntentPrimary, IntentResult


def test_source_search_hint() -> None:
    assert rule_intent_hint("星云大师在哪些文章中谈到共生？") == IntentPrimary.SOURCE_SEARCH


def test_relation_query_hint() -> None:
    assert rule_intent_hint("慈悲与教育是什么关系？") == IntentPrimary.RELATION_QUERY


def test_path_query_hint() -> None:
    assert rule_intent_hint("《维摩经》如何连接到人间佛教实践？") == IntentPrimary.PATH_QUERY


def test_graph_analytics_hint() -> None:
    assert rule_intent_hint("哪些机构承担人间佛教传播的桥梁作用？") == IntentPrimary.GRAPH_ANALYTICS


def test_entity_explain_hint() -> None:
    assert rule_intent_hint("什么是人间佛教？") == IntentPrimary.ENTITY_EXPLAIN


def test_direct_relation_routes_to_graph_direct() -> None:
    query = "星云大师在当前稳定图中连接了哪些机构？"
    intent = rule_only_intent(query, rule_intent_hint(query))
    assert intent.primary_intent == IntentPrimary.RELATION_QUERY
    assert route_for_intent(intent, []) == "graph_direct"


def test_source_search_routes_to_corpus() -> None:
    query = "星云大师在哪些文章中谈到共生？"
    intent = rule_only_intent(query, rule_intent_hint(query))
    assert route_for_intent(intent, []) == "corpus_retrieve"


def test_ambiguous_entity_forces_clarify() -> None:
    intent = rule_only_intent("什么是人间佛教？", IntentPrimary.ENTITY_EXPLAIN)

    class _Ambiguous:
        is_ambiguous = True

    assert route_for_intent(intent, [_Ambiguous()]) == "clarify_or_refuse"


def test_merge_with_rule_hint_overrides_low_confidence() -> None:
    from huidu_xingyun.agent.routing import merge_with_rule_hint

    intent = IntentResult(primary_intent=IntentPrimary.GENERAL_CHAT, confidence=0.4)
    merged = merge_with_rule_hint(intent, IntentPrimary.RELATION_QUERY)
    assert merged.primary_intent == IntentPrimary.RELATION_QUERY
