"""图谱工具：关系、路径、邻域与冻结指标。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..repositories.graph import GraphRepository


def build_graph_tools(graph: GraphRepository) -> list:
    @tool
    def search_relations(
        entity_id: str, relation_type: str = "", direction: str = "", limit: int = 20
    ) -> str:
        """查询某个实体的直接稳定关系，可按关系类型或方向过滤。"""
        rels = graph.search_relations(
            [entity_id],
            relation_type=relation_type or None,
            direction=direction or None,
            limit=limit,
        )
        return json.dumps(rels, ensure_ascii=False)

    @tool
    def find_graph_paths(source_id: str, target_id: str, max_depth: int = 3) -> str:
        """查询两个实体之间的多跳稳定关系路径。"""
        paths = graph.find_paths(source_id, target_id, max_depth=max_depth, limit=5)
        normalized = [
            {
                "nodes": [step["from_name"] for step in steps] + [steps[-1]["to_name"]]
                if steps
                else [],
                "relations": [step["relation_label"] for step in steps],
            }
            for steps in paths
        ]
        return json.dumps(normalized, ensure_ascii=False)

    @tool
    def get_entity_neighborhood(entity_id: str, depth: int = 1) -> str:
        """返回实体邻域子图（节点与关系），供前端可视化。"""
        return json.dumps(graph.get_neighborhood(entity_id, depth=depth), ensure_ascii=False)

    @tool
    def get_graph_metrics(metric: str = "bridge_score", entity_type: str = "", k: int = 10) -> str:
        """读取冻结的中心性/结构指标并按给定指标排序。"""
        top = graph.rank_entities(metric=metric, entity_type=entity_type or None, k=k)
        return json.dumps({"overview": graph.overview(), "top": top}, ensure_ascii=False)

    return [search_relations, find_graph_paths, get_entity_neighborhood, get_graph_metrics]
