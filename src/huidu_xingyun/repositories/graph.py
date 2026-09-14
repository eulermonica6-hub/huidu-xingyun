"""知识图谱仓储：只读 ``data/package/graph`` 与 ``data/package/analytics``。

这是 Agent 的图谱真源（ADR-008）。稳定关系层用于直接关系、路径与邻域查询，
Claim 层只作语境旁证；两者在回答中必须可区分（证据四层 A/B）。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from ..config.settings import RuntimePaths
from ..schemas.evidence import EntityCandidate, ResolvedEntity
from .base import load_csv, to_bool, to_float, to_int

STABLE_LAYER = "stable_entity_graph"
_BRACKETS = "《》「」『』“”\"'（）()"


class GraphRepository:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._loaded = False

        self._entities: dict[str, dict[str, Any]] = {}
        self._name_index: dict[str, list[str]] = defaultdict(list)
        self._alias_index: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self._relations: list[dict[str, Any]] = []
        self._relations_by_id: dict[str, dict[str, Any]] = {}
        self._relation_types: dict[str, dict[str, Any]] = {}
        self._evidence_by_relation: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._claims: dict[str, dict[str, Any]] = {}
        self._claim_relations: list[dict[str, Any]] = []
        self._claim_evidence_by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._entity_metrics: dict[str, dict[str, Any]] = {}
        self._stable_adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)

    # ------------------------------------------------------------------ 加载
    def load(self) -> "GraphRepository":
        self._load_entities()
        self._load_relations()
        self._load_evidence()
        self._load_claims()
        self._load_metrics()
        self._build_adjacency()
        self._loaded = True
        return self

    def _load_entities(self) -> None:
        for row in load_csv(self.paths.entities):
            entity_id = row["entity_id"]
            self._entities[entity_id] = {
                "entity_id": entity_id,
                "name": row["name"].strip(),
                "entity_type": row["entity_type"].strip(),
                "node_class": row["node_class"].strip(),
                "mention_count": to_int(row["mention_count"]),
                "document_count": to_int(row["document_count"]),
                "in_relation_graph": to_bool(row["in_relation_graph"]),
                "in_claim_graph": to_bool(row["in_claim_graph"]),
                "analytics_enabled": to_bool(row["analytics_enabled"]),
            }
            name = row["name"].strip()
            if name:
                self._name_index[name].append(entity_id)

        for row in load_csv(self.paths.aliases):
            entity_id = row["entity_id"]
            ambiguity = to_int(row["ambiguity_count"], default=1)
            for key in {row["alias"].strip(), row["normalized_alias"].strip()}:
                if key:
                    self._alias_index[key].append((entity_id, ambiguity))

    def _load_relations(self) -> None:
        for row in load_csv(self.paths.relation_types):
            key = row["relation_type"].strip()
            self._relation_types[key] = {
                "relation_type": key,
                "label": row["label"].strip(),
                "definition": row["definition"].strip(),
                "source_types": row["source_types"].strip(),
                "target_types": row["target_types"].strip(),
                "direction": row["direction"].strip(),
                "status": row["status"].strip(),
            }

        for row in load_csv(self.paths.relations):
            relation = {
                "relation_id": row["relation_id"],
                "source_id": row["source_id"],
                "source_name": row["source_name"].strip(),
                "source_type": row["source_type"].strip(),
                "relation_type": row["relation_type"].strip(),
                "relation_label": row["relation_label"].strip(),
                "target_id": row["target_id"],
                "target_name": row["target_name"].strip(),
                "target_type": row["target_type"].strip(),
                "direction": row["direction"].strip(),
                "usage": row["usage"].strip(),
                "layer": row["layer"].strip(),
                "analytics_enabled": to_bool(row["analytics_enabled"]),
                "mention_count": to_int(row["mention_count"]),
                "document_count": to_int(row["document_count"]),
                "evidence_count": to_int(row["evidence_count"]),
                "evidence_strength": row["evidence_strength"].strip(),
                "example_text": row["example_text"].strip(),
                "example_url": row["example_url"].strip(),
            }
            self._relations.append(relation)
            self._relations_by_id[relation["relation_id"]] = relation

    def _load_evidence(self) -> None:
        for row in load_csv(self.paths.relation_evidence):
            self._evidence_by_relation[row["relation_id"]].append(
                {
                    "evidence_id": row["evidence_id"],
                    "relation_id": row["relation_id"],
                    "document_id": row["document_id"],
                    "paragraph_id": row["paragraph_id"],
                    "sentence_ids": row["sentence_ids"],
                    "category": row["category"].strip(),
                    "source_url": row["source_url"].strip(),
                    "text": row["text"].strip(),
                    "support_count": to_int(row["support_count"], default=1),
                    "review_status": row["review_status"].strip(),
                }
            )

    def _load_claims(self) -> None:
        for row in load_csv(self.paths.claims):
            self._claims[row["claim_id"]] = {
                "claim_id": row["claim_id"],
                "text": row["text"].strip(),
                "claim_type": row["claim_type"].strip(),
                "semantic_role": row["semantic_role"].strip(),
                "document_id": row["document_id"],
                "paragraph_id": row["paragraph_id"],
                "category": row["category"].strip(),
                "source_url": row["source_url"].strip(),
            }
        for row in load_csv(self.paths.claim_relations):
            self._claim_relations.append(
                {
                    "claim_relation_id": row["claim_relation_id"],
                    "source_id": row["source_id"],
                    "source_name": row["source_name"].strip(),
                    "source_type": row["source_type"].strip(),
                    "relation_type": row["relation_type"].strip(),
                    "relation_label": row["relation_label"].strip(),
                    "target_id": row["target_id"],
                    "target_name": row["target_name"].strip(),
                    "target_type": row["target_type"].strip(),
                    "layer": row["layer"].strip(),
                    "evidence_count": to_int(row["evidence_count"]),
                    "example_text": row["example_text"].strip(),
                    "example_url": row["example_url"].strip(),
                }
            )
        for row in load_csv(self.paths.claim_evidence):
            self._claim_evidence_by_claim[row["claim_id"]].append(
                {
                    "claim_evidence_id": row["claim_evidence_id"],
                    "claim_id": row["claim_id"],
                    "document_id": row["document_id"],
                    "paragraph_id": row["paragraph_id"],
                    "sentence_ids": row["sentence_ids"],
                    "category": row["category"].strip(),
                    "source_url": row["source_url"].strip(),
                    "text": row["text"].strip(),
                    "support_count": to_int(row["support_count"], default=1),
                }
            )

    def _load_metrics(self) -> None:
        for row in load_csv(self.paths.entity_metrics):
            self._entity_metrics[row["entity_id"]] = row

    def _build_adjacency(self) -> None:
        """稳定层无向邻接表，供多跳路径检索使用。"""
        for rel in self._relations:
            if rel["layer"] != STABLE_LAYER:
                continue
            forward = {
                "from_id": rel["source_id"],
                "from_name": rel["source_name"],
                "relation_label": rel["relation_label"],
                "relation_type": rel["relation_type"],
                "to_id": rel["target_id"],
                "to_name": rel["target_name"],
                "relation_id": rel["relation_id"],
            }
            backward = {
                "from_id": rel["target_id"],
                "from_name": rel["target_name"],
                "relation_label": rel["relation_label"],
                "relation_type": rel["relation_type"],
                "to_id": rel["source_id"],
                "to_name": rel["source_name"],
                "relation_id": rel["relation_id"],
            }
            self._stable_adjacency[rel["source_id"]].append((rel["target_id"], forward))
            self._stable_adjacency[rel["target_id"]].append((rel["source_id"], backward))

    # ------------------------------------------------------------------ 实体
    @property
    def loaded(self) -> bool:
        return self._loaded

    def entity(self, entity_id: str) -> dict[str, Any] | None:
        return self._entities.get(entity_id)

    @staticmethod
    def _normalize(text: str) -> str:
        value = text.strip()
        value = value.strip(_BRACKETS)
        return value.strip().strip("，。？!！；;：:")

    def resolve_entities(
        self, mentions: list[str], expected_types: set[str] | None = None
    ) -> list[ResolvedEntity]:
        """别名/名称规范化解出实体；歧义时返回候选并置空 ``entity_id``。"""
        resolved: list[ResolvedEntity] = []
        for mention in mentions:
            normalized = self._normalize(mention)
            candidates: dict[str, dict[str, Any]] = {}

            def add_candidate(entity_id: str, matched_alias: str, ambiguity: int = 1) -> None:
                entity = self._entities.get(entity_id)
                if entity is None:
                    return
                if expected_types and entity["entity_type"] not in expected_types:
                    return
                existing = candidates.setdefault(
                    entity_id,
                    {
                        "entity_id": entity_id,
                        "name": entity["name"],
                        "entity_type": entity["entity_type"],
                        "matched_alias": matched_alias,
                        "ambiguity_count": ambiguity,
                        "in_relation_graph": entity["in_relation_graph"],
                    },
                )
                existing["ambiguity_count"] = max(existing["ambiguity_count"], ambiguity)

            for key in {mention, normalized}:
                if not key:
                    continue
                for entity_id in self._name_index.get(key, []):
                    add_candidate(entity_id, key)
                for entity_id, ambiguity in self._alias_index.get(key, []):
                    add_candidate(entity_id, key, ambiguity)

            ordered = list(candidates.values())
            ordered.sort(key=lambda c: (not c["in_relation_graph"], c["entity_id"]))
            if not ordered:
                resolved.append(ResolvedEntity(name=mention))
            elif len(ordered) == 1:
                c = ordered[0]
                resolved.append(
                    ResolvedEntity(
                        entity_id=c["entity_id"],
                        name=c["name"],
                        entity_type=c["entity_type"],
                        matched_alias=c["matched_alias"],
                        confidence=0.98,
                        in_relation_graph=c["in_relation_graph"],
                        candidates=[EntityCandidate(**c)],
                    )
                )
            else:
                resolved.append(
                    ResolvedEntity(
                        name=mention,
                        candidates=[EntityCandidate(**c) for c in ordered],
                    )
                )
        return resolved

    def extract_mentions(self, query: str, min_len: int = 2, max_mentions: int = 12) -> list[str]:
        """从查询中抽出已知实体/别名，用于无 LLM 时的实体定位。按长度优先。"""
        hits: set[str] = set()
        for key in self._name_index:
            if len(key) >= min_len and key in query:
                hits.add(key)
        for key in self._alias_index:
            if len(key) >= min_len and key in query:
                hits.add(key)
        ordered = sorted(hits, key=len, reverse=True)
        # 去除被更长命中覆盖的子串（如「大师」被「星云大师」覆盖时保留后者）。
        filtered: list[str] = []
        for hit in ordered:
            if any(hit in existing for existing in filtered):
                continue
            filtered.append(hit)
            if len(filtered) >= max_mentions:
                break
        return filtered

    # ------------------------------------------------------------------ 关系
    def search_relations(
        self,
        entity_ids: list[str] | set[str],
        relation_type: str | None = None,
        direction: str | None = None,
        neighbor_type: str | None = None,
        layer: str = STABLE_LAYER,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        ids = set(entity_ids)
        output: list[dict[str, Any]] = []
        for rel in self._relations:
            if rel["layer"] != layer:
                continue
            if relation_type and rel["relation_type"] != relation_type:
                continue
            source_hit = rel["source_id"] in ids
            target_hit = rel["target_id"] in ids
            if direction == "out" and not source_hit:
                continue
            if direction == "in" and not target_hit:
                continue
            if direction not in ("out", "in") and not (source_hit or target_hit):
                continue
            if neighbor_type:
                if source_hit and rel["target_type"] != neighbor_type:
                    continue
                if target_hit and not source_hit and rel["source_type"] != neighbor_type:
                    continue
            output.append(rel)
            if len(output) >= limit:
                break
        return output

    def relation_types(self) -> dict[str, dict[str, Any]]:
        return self._relation_types

    def relation_label(self, relation_type: str) -> str:
        entry = self._relation_types.get(relation_type)
        return entry["label"] if entry else relation_type

    # ------------------------------------------------------------------ 路径
    def find_paths(
        self, source_id: str, target_id: str, max_depth: int = 3, limit: int = 5
    ) -> list[list[dict[str, Any]]]:
        """稳定层多跳路径（无向遍历，记录每一步方向与关系名）。"""
        if source_id == target_id:
            return [[]]
        queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(source_id, [])])
        visited: set[str] = {source_id}
        paths: list[list[dict[str, Any]]] = []
        while queue:
            node, steps = queue.popleft()
            if len(steps) >= max_depth:
                continue
            for neighbor, step in self._stable_adjacency.get(node, []):
                if neighbor in visited and neighbor != target_id:
                    continue
                new_steps = steps + [step]
                if neighbor == target_id:
                    paths.append(new_steps)
                    if len(paths) >= limit:
                        return paths
                else:
                    visited.add(neighbor)
                    queue.append((neighbor, new_steps))
        return paths

    # ------------------------------------------------------------------ 邻域
    def get_neighborhood(
        self, entity_id: str, depth: int = 1, limit_nodes: int = 50
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        frontier = {entity_id}
        seen: set[str] = set()
        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier:
                if current in seen:
                    continue
                seen.add(current)
                entity = self._entities.get(current)
                if entity:
                    nodes[current] = entity
                for neighbor, rel in self._relations_of(current):
                    next_frontier.add(neighbor)
                    edges.append(
                        {
                            "relation_id": rel["relation_id"],
                            "source_id": rel["source_id"],
                            "source_name": rel["source_name"],
                            "relation_label": rel["relation_label"],
                            "target_id": rel["target_id"],
                            "target_name": rel["target_name"],
                        }
                    )
            frontier = next_frontier
            if len(nodes) >= limit_nodes:
                break
        return {"nodes": list(nodes.values()), "edges": edges}

    def _relations_of(self, entity_id: str) -> list[tuple[str, dict[str, Any]]]:
        pairs: list[tuple[str, dict[str, Any]]] = []
        for rel in self._relations:
            if rel["layer"] != STABLE_LAYER:
                continue
            if rel["source_id"] == entity_id:
                pairs.append((rel["target_id"], rel))
            elif rel["target_id"] == entity_id:
                pairs.append((rel["source_id"], rel))
        return pairs

    # ------------------------------------------------------------------ 证据
    def get_relation_evidence(self, relation_id: str) -> list[dict[str, Any]]:
        return self._evidence_by_relation.get(relation_id, [])

    def claim_relations_for_entity(self, entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            rel
            for rel in self._claim_relations
            if rel["source_id"] == entity_id or rel["target_id"] == entity_id
        ][:limit]

    # ------------------------------------------------------------------ 指标
    def get_entity_metrics(self, entity_id: str) -> dict[str, Any] | None:
        return self._entity_metrics.get(entity_id)

    def rank_entities(
        self,
        metric: str = "bridge_score",
        entity_type: str | None = None,
        k: int = 10,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        rows: list[tuple[float, dict[str, Any]]] = []
        for entity_id, row in self._entity_metrics.items():
            if entity_type and row.get("entity_type", "").strip() != entity_type:
                continue
            rows.append((to_float(row.get(metric)), row))
        rows.sort(key=lambda pair: pair[0], reverse=descending)
        output: list[dict[str, Any]] = []
        for value, row in rows[:k]:
            output.append(
                {
                    "entity_id": row["entity_id"],
                    "name": row.get("name", "").strip(),
                    "entity_type": row.get("entity_type", "").strip(),
                    "metric": metric,
                    "value": value,
                    "degree": to_int(row.get("degree")),
                    "pagerank": to_float(row.get("pagerank")),
                    "betweenness": to_float(row.get("betweenness")),
                    "bridge_score": to_float(row.get("bridge_score")),
                    "bridge_rank": to_int(row.get("bridge_rank")),
                }
            )
        return output

    # ------------------------------------------------------------------ 概览
    def overview(self) -> dict[str, int]:
        stable = [r for r in self._relations if r["layer"] == STABLE_LAYER]
        return {
            "entities": len(self._entities),
            "entities_in_stable_graph": sum(
                1 for e in self._entities.values() if e["in_relation_graph"]
            ),
            "relation_types": len(self._relation_types),
            "stable_relations": len(stable),
            "stable_evidence": sum(len(v) for v in self._evidence_by_relation.values()),
            "claims": len(self._claims),
            "claim_relations": len(self._claim_relations),
            "entity_metrics": len(self._entity_metrics),
        }
