"""图谱仓储测试：计数与冻结基线一致，关系/路径/指标可用。"""

from __future__ import annotations

from huidu_xingyun.repositories.graph import GraphRepository


def test_overview_matches_frozen_baseline(graph_repo: GraphRepository) -> None:
    overview = graph_repo.overview()
    assert overview["entities"] == 25560
    assert overview["stable_relations"] == 2745
    assert overview["entities_in_stable_graph"] == 1786
    assert overview["relation_types"] == 153


def test_search_relations_master_institution(graph_repo: GraphRepository) -> None:
    master = graph_repo.resolve_entities(["星雲大師"])[0]
    rels = graph_repo.search_relations([master.entity_id], neighbor_type="Institution")
    assert rels
    assert all(
        r["target_type"] == "Institution" or r["source_type"] == "Institution" for r in rels
    )


def test_search_relations_direction_out(graph_repo: GraphRepository) -> None:
    master = graph_repo.resolve_entities(["星雲大師"])[0]
    rels = graph_repo.search_relations([master.entity_id], direction="out", limit=10)
    assert all(r["source_id"] == master.entity_id for r in rels)


def test_find_paths_between_entities(graph_repo: GraphRepository) -> None:
    master = graph_repo.resolve_entities(["星雲大師"])[0]
    buddha_light = graph_repo.resolve_entities(["佛光山"])[0]
    assert master.resolved and buddha_light.resolved
    paths = graph_repo.find_paths(master.entity_id, buddha_light.entity_id, max_depth=3, limit=3)
    assert isinstance(paths, list)
    for steps in paths:
        assert steps  # 至少一跳
        assert all("relation_label" in step for step in steps)


def test_rank_entities_by_bridge(graph_repo: GraphRepository) -> None:
    top = graph_repo.rank_entities(metric="bridge_score", entity_type="Institution", k=5)
    assert len(top) == 5
    assert top[0]["name"]
    values = [row["value"] for row in top]
    assert values == sorted(values, reverse=True)
