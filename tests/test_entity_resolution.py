"""实体解析与消歧测试（呼应 Stage289 指代敏感性）。"""

from __future__ import annotations

from huidu_xingyun.repositories.graph import GraphRepository


def test_master_resolves_to_person(graph_repo: GraphRepository) -> None:
    resolved = graph_repo.resolve_entities(["星雲大師"])[0]
    assert resolved.resolved
    assert resolved.entity_type == "Person"
    assert resolved.in_relation_graph is True


def test_dashi_does_not_equal_master(graph_repo: GraphRepository) -> None:
    dashi = graph_repo.resolve_entities(["大师"])[0]
    master = graph_repo.resolve_entities(["星雲大師"])[0]
    assert dashi.entity_id != master.entity_id
    assert dashi.entity_type == "RoleTitle"


def test_alias_resolves_classic(graph_repo: GraphRepository) -> None:
    resolved = graph_repo.resolve_entities(["维摩经"])[0]
    assert resolved.resolved
    assert resolved.entity_type == "Classic"


def test_ambiguous_mention_surfaces_candidates(graph_repo: GraphRepository) -> None:
    resolved = graph_repo.resolve_entities(["人间佛教"])[0]
    # 简化写法在冻结别名表中对应多个候选，必须显式消歧而非静默选取。
    assert resolved.is_ambiguous or not resolved.resolved


def test_extract_mentions_keeps_dashi_distinct(graph_repo: GraphRepository) -> None:
    mentions = graph_repo.extract_mentions("大师如何解释般若")
    assert "般若" in mentions
    assert "大师" in mentions
    assert "星雲大師" not in mentions
