from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "data_paths.json"
SCHEMA_PATH = PROJECT_ROOT / "config" / "data_schema.json"
PACKAGE_ROOT = PROJECT_ROOT / "data" / "package"

ARTICLE_PATTERN = re.compile(r"artcle(\d+)", re.IGNORECASE)
PARAGRAPH_PATTERN = re.compile(r"artcle(\d+)_p(\d+)", re.IGNORECASE)
SENTENCE_PATTERN = re.compile(r"artcle(\d+)_p(\d+)_s(\d+)", re.IGNORECASE)
SOURCE_ID_PATTERN = re.compile(r"(?:^|[^a-z0-9])(s\d+|stage\d+)", re.IGNORECASE)
HEADER_PREFIXES = ("标题：", "URL：", "分类：", "书目：", "路径：")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class BuildError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def resolve(path_value: str) -> Path:
    return (PROJECT_ROOT / path_value).resolve()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table_columns(schema: dict[str, Any], table_name: str) -> list[str]:
    return [field["name"] for field in schema["tables"][table_name]["fields"]]


def table_path(schema: dict[str, Any], table_name: str) -> Path:
    return PACKAGE_ROOT / schema["tables"][table_name]["path"]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
    temporary.replace(path)


def runtime_id(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def create_id_map(prefix: str, source_ids: Iterable[str]) -> dict[str, str]:
    mapping = {source_id: runtime_id(prefix, source_id) for source_id in source_ids}
    if "" in mapping:
        raise BuildError(f"{prefix} source identifiers contain a blank value")
    reverse: dict[str, str] = {}
    for source_id, clean_id in mapping.items():
        if clean_id in reverse and reverse[clean_id] != source_id:
            raise BuildError(f"runtime ID collision: {source_id} and {reverse[clean_id]}")
        reverse[clean_id] = source_id
    return mapping


def as_int(value: Any, default: int = 0) -> int:
    text = str(value or "").strip()
    return default if not text else int(float(text))


def bool_text(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return "true"
    if text in {"false", "0", "no", "n", ""}:
        return "false"
    raise BuildError(f"invalid boolean value: {value!r}")


def normalize_direction(value: str) -> str:
    text = value.strip().lower()
    if text in {"yes", "directed", "directional"}:
        return "directed"
    if text in {"no", "undirected", "bidirectional"}:
        return "undirected"
    return text


def normalize_policy(value: str) -> str:
    replacements = {
        "eligible_after_stage261b_gate": "eligible_after_quality_gate",
        "excluded_after_stage261b_gate": "excluded_after_quality_gate",
    }
    return replacements.get(value, value)


def article_number(*values: Any) -> int | None:
    for value in values:
        match = ARTICLE_PATTERN.search(str(value or ""))
        if match:
            return int(match.group(1))
    return None


def document_id(*values: Any) -> str:
    number = article_number(*values)
    return "" if number is None else f"doc_{number:08d}"


def book_id(value: Any) -> str:
    return f"book_{as_int(value):03d}"


def paragraph_id(value: Any) -> str:
    match = PARAGRAPH_PATTERN.search(str(value or ""))
    if not match:
        return ""
    return f"par_{int(match.group(1)):08d}_{int(match.group(2)):04d}"


def sentence_ids(value: Any) -> str:
    output: list[str] = []
    seen: set[str] = set()
    for article, paragraph, sentence in SENTENCE_PATTERN.findall(str(value or "")):
        clean_id = f"sent_{int(article):08d}_{int(paragraph):04d}_{int(sentence):03d}"
        if clean_id not in seen:
            seen.add(clean_id)
            output.append(clean_id)
    return ";".join(output)


def clean_body(raw_text: str) -> str:
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    positions: list[int] = []
    cursor = 0
    for prefix in HEADER_PREFIXES:
        position = next(
            (index for index in range(cursor, min(len(lines), 20)) if lines[index].startswith(prefix)),
            -1,
        )
        if position < 0:
            positions = []
            break
        positions.append(position)
        cursor = position + 1
    if positions:
        lines = lines[positions[-1] + 1 :]
        while lines and lines[0].strip():
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    cleaned: list[str] = []
    previous_blank = False
    for line in lines:
        line = line.rstrip()
        is_blank = not line
        if is_blank and previous_blank:
            continue
        cleaned.append(line)
        previous_blank = is_blank
    return "\n".join(cleaned).strip()


def map_required(mapping: dict[str, str], source_id: str, label: str) -> str:
    try:
        return mapping[source_id]
    except KeyError as exc:
        raise BuildError(f"unmapped {label}: {source_id}") from exc


def map_reference_list(value: str, mapping: dict[str, str], label: str) -> str:
    if not value.strip():
        return ""
    tokens = re.findall(r"[A-Za-z0-9_]+", value)
    mapped = [mapping[token] for token in tokens if token in mapping]
    if not mapped:
        raise BuildError(f"unmapped {label}: {value}")
    return ";".join(dict.fromkeys(mapped))


def build_corpus(config: dict[str, Any], schema: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = resolve(config["corpus"]["manifest"])
    text_base = resolve(config["corpus"]["manifest_text_file_base"])
    manifests: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    manifests.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise BuildError(f"invalid corpus manifest line {line_number}: {exc}") from exc

    documents: list[dict[str, Any]] = []
    id_rows: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    article_dir = PACKAGE_ROOT / "corpus" / "articles"
    article_dir.mkdir(parents=True, exist_ok=True)

    manifests.sort(key=lambda row: article_number(row.get("article_id")) or 0)
    for index, row in enumerate(manifests, start=1):
        clean_document_id = document_id(row.get("article_id"), row.get("url"))
        if not clean_document_id:
            raise BuildError(f"cannot derive document ID from {row.get('article_id')!r}")
        if clean_document_id in seen_documents:
            raise BuildError(f"duplicate runtime document ID: {clean_document_id}")
        seen_documents.add(clean_document_id)

        relative_source = Path(str(row["text_file"]).replace("\\", "/"))
        source_path = text_base / relative_source
        if not source_path.exists():
            raise BuildError(f"missing source text: {source_path}")
        body = clean_body(source_path.read_text(encoding="utf-8-sig", errors="strict"))
        target_path = article_dir / f"{clean_document_id}.txt"
        target_text = body + "\n"
        if not target_path.exists() or target_path.read_text(encoding="utf-8") != target_text:
            target_path.write_text(target_text, encoding="utf-8", newline="\n")

        documents.append(
            {
                "document_id": clean_document_id,
                "title": str(row["title"]).strip(),
                "category": str(row["category"]).strip(),
                "book_id": book_id(row["book_id"]),
                "book_title": str(row["book_title"]).strip(),
                "breadcrumbs": [str(item).strip() for item in row.get("breadcrumbs", [])],
                "char_count": len(body),
                "source_url": str(row["url"]).strip(),
                "text_path": target_path.relative_to(PACKAGE_ROOT).as_posix(),
            }
        )
        id_rows.append(
            {
                "source_id": str(row["article_id"]).strip(),
                "runtime_id": clean_document_id,
                "source_url": str(row["url"]).strip(),
            }
        )
        if index % 5000 == 0:
            print(f"COPIED corpus articles: {index}/{len(manifests)}")

    write_jsonl(table_path(schema, "documents"), documents)

    grouped: dict[str, dict[str, Any]] = {}
    for row in documents:
        group = grouped.setdefault(
            row["book_id"],
            {
                "book_id": row["book_id"],
                "title": row["book_title"],
                "categories": set(),
                "document_count": 0,
                "char_count": 0,
            },
        )
        group["categories"].add(row["category"])
        group["document_count"] += 1
        group["char_count"] += row["char_count"]
    books = [
        {
            "book_id": row["book_id"],
            "title": row["title"],
            "category": ";".join(sorted(row["categories"])),
            "document_count": row["document_count"],
            "char_count": row["char_count"],
        }
        for row in grouped.values()
    ]
    books.sort(key=lambda row: row["book_id"])
    write_csv(table_path(schema, "books"), table_columns(schema, "books"), books)
    write_csv(
        PACKAGE_ROOT / "metadata" / "id_map_documents.csv",
        ["source_id", "runtime_id", "source_url"],
        id_rows,
    )
    return documents, books


def build_graph(
    config: dict[str, Any],
    schema: dict[str, Any],
    documents: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, str]]]:
    graph = config["knowledge_graph"]
    source_entities = read_csv(resolve(graph["entity_registry"]))
    source_aliases = read_csv(resolve(graph["entity_alias_registry"]))
    source_relation_types = read_csv(resolve(graph["relation_registry"]))
    source_relations = read_csv(resolve(graph["stable_relations"]))
    source_relation_evidence = read_csv(resolve(graph["stable_evidence"]))
    source_claims = read_csv(resolve(graph["claim_nodes"]))
    source_claim_relations = read_csv(resolve(graph["claim_relations"]))
    source_claim_evidence = read_csv(resolve(graph["claim_evidence"]))

    entity_map = create_id_map("ent", (row["entity_id"] for row in source_entities))
    relation_map = create_id_map("rel", (row["edge_uid"] for row in source_relations))
    claim_map = create_id_map("claim", (row["claim_id"] for row in source_claims))
    claim_relation_map = create_id_map("crel", (row["edge_uid"] for row in source_claim_relations))
    relation_evidence_map = create_id_map("ev", (row["evidence_uid"] for row in source_relation_evidence))
    claim_evidence_map = create_id_map("cev", (row["evidence_uid"] for row in source_claim_evidence))
    document_categories = {row["document_id"]: row["category"] for row in documents}

    def category_for(raw_category: str, clean_document_id: str) -> str:
        return raw_category.strip() or document_categories.get(clean_document_id, "")

    entities = [
        {
            "entity_id": entity_map[row["entity_id"]],
            "name": row["preferred_label"].strip(),
            "entity_type": row["entity_type"].strip(),
            "node_class": row["node_class"].strip(),
            "mention_count": as_int(row["corpus_mention_count"]),
            "document_count": as_int(row["corpus_article_count"]),
            "in_relation_graph": bool_text(row["active_in_stable_graph"]),
            "in_claim_graph": bool_text(row["active_in_claim_graph"]),
            "analytics_enabled": bool_text(row["centrality_eligible"]),
        }
        for row in source_entities
    ]
    aliases = [
        {
            "alias": row["alias"].strip(),
            "normalized_alias": row["normalized_alias"].strip(),
            "entity_id": map_required(entity_map, row["entity_id"], "alias entity"),
            "ambiguity_count": as_int(row["normalized_alias_entity_count"]),
            "resolution_status": row["alias_resolution_status"].strip(),
        }
        for row in source_aliases
    ]
    relation_types = [
        {
            "relation_type": row["relation_key"].strip(),
            "label": row["relation_label_cn"].strip(),
            "definition": row["semantic_definition"].strip(),
            "source_types": row["source_contract"].strip(),
            "target_types": row["target_contract"].strip(),
            "direction": normalize_direction(row["directionality"]),
            "projection": row["graph_projection"].strip(),
            "analytics_policy": normalize_policy(row["centrality_policy"].strip()),
            "status": row["registration_status"].strip(),
        }
        for row in source_relation_types
    ]
    relations = [
        {
            "relation_id": relation_map[row["edge_uid"]],
            "source_id": map_required(entity_map, row["source_entity_id"], "relation source"),
            "source_name": row["source_text"].strip(),
            "source_type": row["source_type"].strip(),
            "relation_type": row["relation_key"].strip(),
            "relation_label": row["relation_label_cn"].strip(),
            "target_id": map_required(entity_map, row["target_entity_id"], "relation target"),
            "target_name": row["target_text"].strip(),
            "target_type": row["target_type"].strip(),
            "direction": normalize_direction(row["directionality"]),
            "usage": row["usage_permission"].strip(),
            "layer": row["graph_layer"].strip(),
            "analytics_enabled": bool_text(row["centrality_eligible"]),
            "mention_count": as_int(row["occurrence_count"]),
            "document_count": as_int(row["article_count"]),
            "paragraph_count": as_int(row["paragraph_count"]),
            "category_count": as_int(row["category_count"]),
            "evidence_count": as_int(row["evidence_record_count"]),
            "evidence_strength": row["evidence_strength"].strip(),
            "example_text": row["example_evidence_text"].strip(),
            "example_url": row["example_url"].strip(),
        }
        for row in source_relations
    ]
    relation_evidence = []
    for row in source_relation_evidence:
        clean_document_id = document_id(row["article_uid"], row["url"])
        relation_evidence.append({
            "evidence_id": relation_evidence_map[row["evidence_uid"]],
            "relation_id": map_required(relation_map, row["edge_uid"], "evidence relation"),
            "document_id": clean_document_id,
            "paragraph_id": paragraph_id(row["paragraph_uid"]),
            "sentence_ids": sentence_ids(row["sentence_uid"]),
            "category": category_for(row["category"], clean_document_id),
            "source_url": row["url"].strip(),
            "text": row["evidence_text"].strip(),
            "support_count": as_int(row["support_occurrence_count"], default=1),
            "review_status": row["review_decision"].strip() or "accepted_release",
        })
    claims = []
    for row in source_claims:
        clean_document_id = document_id(row["article_uid"], row["first_url"])
        claims.append({
            "claim_id": claim_map[row["claim_id"]],
            "text": row["claim_text"].strip(),
            "claim_type": row["claim_type"].strip(),
            "node_class": row["node_class"].strip(),
            "semantic_role": row["semantic_role"].strip(),
            "document_id": clean_document_id,
            "paragraph_id": paragraph_id(row["first_paragraph_uid"]),
            "sentence_ids": sentence_ids(row["first_sentence_uid"]),
            "category": category_for(row["category"], clean_document_id),
            "source_url": row["first_url"].strip(),
            "evidence_count": as_int(row["evidence_occurrence_count"], default=1),
        })

    endpoint_map = {**entity_map, **claim_map}
    claim_relations = [
        {
            "claim_relation_id": claim_relation_map[row["edge_uid"]],
            "source_id": map_required(endpoint_map, row["source_entity_id"], "claim relation source"),
            "source_name": row["source_text"].strip(),
            "source_type": row["source_type"].strip(),
            "relation_type": row["relation_key"].strip(),
            "relation_label": row["relation_label_cn"].strip(),
            "target_id": map_required(endpoint_map, row["target_entity_id"], "claim relation target"),
            "target_name": row["target_text"].strip(),
            "target_type": row["target_type"].strip(),
            "usage": row["usage_permission"].strip(),
            "layer": row["graph_layer"].strip(),
            "mention_count": as_int(row["occurrence_count"]),
            "document_count": as_int(row["article_count"]),
            "paragraph_count": as_int(row["paragraph_count"]),
            "sentence_count": as_int(row["sentence_count"]),
            "category_count": as_int(row["category_count"]),
            "evidence_count": as_int(row["evidence_record_count"]),
            "example_text": row["example_evidence_text"].strip(),
            "example_url": row["example_url"].strip(),
        }
        for row in source_claim_relations
    ]
    claim_evidence = []
    for row in source_claim_evidence:
        clean_document_id = document_id(row["article_uid"], row["url"])
        claim_evidence.append({
            "claim_evidence_id": claim_evidence_map[row["evidence_uid"]],
            "claim_id": map_required(claim_map, row["claim_id"], "claim evidence claim"),
            "claim_relation_ids": map_reference_list(
                row["claim_edge_uids"], claim_relation_map, "claim evidence relations"
            ),
            "document_id": clean_document_id,
            "paragraph_id": paragraph_id(row["paragraph_uid"]),
            "sentence_ids": sentence_ids(row["sentence_uid"]),
            "category": category_for(row["category"], clean_document_id),
            "source_url": row["url"].strip(),
            "text": row["evidence_text"].strip(),
            "support_count": as_int(row["support_occurrence_count"], default=1),
        })

    tables = {
        "entities": entities,
        "aliases": aliases,
        "relation_types": relation_types,
        "relations": relations,
        "relation_evidence": relation_evidence,
        "claims": claims,
        "claim_relations": claim_relations,
        "claim_evidence": claim_evidence,
    }
    for name, rows in tables.items():
        write_csv(table_path(schema, name), table_columns(schema, name), rows)

    metadata = PACKAGE_ROOT / "metadata"
    write_csv(
        metadata / "id_map_entities.csv",
        ["source_id", "runtime_id"],
        ({"source_id": key, "runtime_id": value} for key, value in sorted(entity_map.items())),
    )
    write_csv(
        metadata / "id_map_relations.csv",
        ["source_id", "runtime_id"],
        ({"source_id": key, "runtime_id": value} for key, value in sorted(relation_map.items())),
    )
    write_csv(
        metadata / "id_map_claims.csv",
        ["source_id", "runtime_id"],
        ({"source_id": key, "runtime_id": value} for key, value in sorted(claim_map.items())),
    )
    write_csv(
        metadata / "id_map_claim_relations.csv",
        ["source_id", "runtime_id"],
        ({"source_id": key, "runtime_id": value} for key, value in sorted(claim_relation_map.items())),
    )
    evidence_map_rows = [
        {"record_type": "relation_evidence", "source_id": key, "runtime_id": value}
        for key, value in sorted(relation_evidence_map.items())
    ] + [
        {"record_type": "claim_evidence", "source_id": key, "runtime_id": value}
        for key, value in sorted(claim_evidence_map.items())
    ]
    write_csv(
        metadata / "id_map_evidence.csv",
        ["record_type", "source_id", "runtime_id"],
        evidence_map_rows,
    )

    maps = {
        "entities": entity_map,
        "relations": relation_map,
        "claims": claim_map,
        "claim_relations": claim_relation_map,
        "relation_evidence": relation_evidence_map,
        "claim_evidence": claim_evidence_map,
    }
    return tables, maps


def graph_metric_row(source: dict[str, str], id_field: str, id_value: str) -> dict[str, Any]:
    return {
        id_field: id_value,
        "relation_count": as_int(source["relation_records"]),
        "node_count": as_int(source["nodes"]),
        "directed_pair_count": as_int(source["directed_pairs"]),
        "undirected_pair_count": as_int(source["undirected_pairs"]),
        "self_loop_count": as_int(source["self_loops"]),
        "component_count": as_int(source["connected_components"]),
        "largest_component_nodes": as_int(source["largest_component_nodes"]),
        "largest_component_share": source["largest_component_share"].strip(),
        "density": source["density_undirected"].strip(),
        "mean_degree": source["mean_degree"].strip(),
        "reciprocity": source["reciprocity"].strip(),
        "transitivity": source["transitivity"].strip(),
        "average_clustering": source["average_clustering"].strip(),
        "degree_assortativity": source["degree_assortativity"].strip(),
        "community_count": as_int(source["communities"]),
        "modularity": source["modularity"].strip(),
        "max_core_number": as_int(source["max_core_number"]),
        "estimated_diameter": as_int(source["approx_lcc_diameter"]),
        "estimated_mean_shortest_path": source["sampled_lcc_mean_shortest_path"].strip(),
    }


def build_analytics(
    config: dict[str, Any],
    schema: dict[str, Any],
    entity_map: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    source_global = read_csv(resolve(config["analysis"]["global_metrics"]))
    source_entities = read_csv(resolve(config["analysis"]["node_metrics"]))
    source_views = read_csv(resolve(config["analysis"]["view_metrics"]))

    graph_metrics = [graph_metric_row(row, "graph_id", "stable_graph") for row in source_global]
    entity_metrics = [
        {
            "entity_id": map_required(entity_map, row["entity_id"], "entity metric"),
            "name": row["preferred_label"].strip(),
            "entity_type": row["entity_type"].strip(),
            "mention_count": as_int(row["corpus_mention_count"]),
            "document_count": as_int(row["corpus_article_count"]),
            "out_degree": as_int(row["out_degree"]),
            "in_degree": as_int(row["in_degree"]),
            "degree": as_int(row["undirected_degree"]),
            "relation_count": as_int(row["relation_record_degree"]),
            "weighted_degree": row["weighted_degree_article_support"].strip(),
            "evidence_count": as_int(row["incident_evidence_records"]),
            "pagerank": row["pagerank"].strip(),
            "betweenness": row["betweenness"].strip(),
            "harmonic_centrality": row["harmonic_centrality"].strip(),
            "core_number": as_int(row["core_number"]),
            "community_id": as_int(row["community_id"]),
            "community_size": as_int(row["community_size"]),
            "participation_coefficient": row["participation_coefficient"].strip(),
            "relation_family_count": as_int(row["relation_family_count"]),
            "view_count": as_int(row["view_count"]),
            "views": row["views"].strip(),
            "neighbor_type_entropy": row["neighbor_type_entropy"].strip(),
            "relation_rate": row["relation_per_100_mentions"].strip(),
            "pagerank_percentile": row["pagerank_percentile"].strip(),
            "betweenness_percentile": row["betweenness_percentile"].strip(),
            "participation_percentile": row["participation_coefficient_percentile"].strip(),
            "bridge_score": row["bridge_score"].strip(),
            "degree_rank": as_int(row["degree_rank"]),
            "pagerank_rank": as_int(row["pagerank_rank"]),
            "betweenness_rank": as_int(row["betweenness_rank"]),
            "bridge_rank": as_int(row["bridge_rank"]),
        }
        for row in source_entities
    ]
    view_metrics = []
    for row in source_views:
        output = graph_metric_row(row, "view_id", row["graph_name"].strip())
        output = {"view_id": output.pop("view_id"), "view_label": row["view_label_cn"].strip(), **output}
        view_metrics.append(output)

    tables = {
        "graph_metrics": graph_metrics,
        "entity_metrics": entity_metrics,
        "view_metrics": view_metrics,
    }
    for name, rows in tables.items():
        write_csv(table_path(schema, name), table_columns(schema, name), rows)
    return tables


def replace_stage_wording(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: replace_stage_wording(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_stage_wording(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"Stage265", "当前关系类型表", value, flags=re.IGNORECASE)
    return value


def build_quality(config: dict[str, Any]) -> dict[str, Any]:
    manual = load_json(resolve(config["evaluation"]["precision_summary"]))
    recall = load_json(resolve(config["evaluation"]["recall_metrics"]))
    coreference = load_json(resolve(config["evaluation"]["coreference_summary"]))
    quality_gate = load_json(resolve(config["knowledge_graph"]["quality_gate"]))
    quality = {
        "relation_precision": manual["stable_relation"],
        "claim_faithfulness": manual["claim_faithfulness"],
        "recall": replace_stage_wording(recall),
        "coreference_sensitivity": coreference,
        "release_gate": {
            "passed": quality_gate["hard_gate_pass"],
            "check_count": quality_gate["check_count"],
            "passed_check_count": quality_gate["passed_check_count"],
            "errors": quality_gate["errors"],
            "warnings": quality_gate["warnings"],
        },
    }
    write_json(PACKAGE_ROOT / "quality" / "quality_metrics.json", quality)
    return quality


def validate_table_rows(
    schema: dict[str, Any],
    table_name: str,
    rows: list[dict[str, Any]],
    errors: list[str],
) -> None:
    spec = schema["tables"][table_name]
    columns = table_columns(schema, table_name)
    missing_counts: dict[str, int] = defaultdict(int)
    for index, row in enumerate(rows, start=1):
        if list(row.keys()) != columns:
            errors.append(f"{table_name} row {index} has noncanonical fields")
            break
        for field in spec["fields"]:
            value = row.get(field["name"])
            if field["required"] and (value is None or value == ""):
                missing_counts[field["name"]] += 1
    for field_name, count in missing_counts.items():
        errors.append(f"{table_name}.{field_name} is blank in {count} rows")

    primary_key = spec.get("primary_key", [])
    if primary_key:
        keys = [tuple(row.get(field) for field in primary_key) for row in rows]
        if len(keys) != len(set(keys)):
            errors.append(f"{table_name} has duplicate primary keys")


def validate_runtime_ids(schema: dict[str, Any], tables: dict[str, list[dict[str, Any]]], errors: list[str]) -> None:
    patterns = {
        key: re.compile(value) for key, value in schema["naming"]["runtime_id_patterns"].items()
    }
    field_to_pattern = {
        "document_id": "document_id",
        "book_id": "book_id",
        "entity_id": "entity_id",
        "relation_id": "relation_id",
        "evidence_id": "evidence_id",
        "claim_id": "claim_id",
        "claim_relation_id": "claim_relation_id",
        "claim_evidence_id": "claim_evidence_id",
        "paragraph_id": "paragraph_id",
    }
    for table_name, rows in tables.items():
        for row_number, row in enumerate(rows, start=1):
            for field, pattern_name in field_to_pattern.items():
                value = row.get(field)
                if value and not patterns[pattern_name].fullmatch(str(value)):
                    errors.append(f"{table_name} row {row_number} invalid {field}: {value}")
                    return
            for field in ("sentence_ids",):
                for value in str(row.get(field, "")).split(";"):
                    if value and not patterns["sentence_id"].fullmatch(value):
                        errors.append(f"{table_name} row {row_number} invalid sentence ID: {value}")
                        return


def validate_foreign_keys(tables: dict[str, list[dict[str, Any]]], errors: list[str]) -> None:
    documents = {row["document_id"] for row in tables["documents"]}
    entities = {row["entity_id"] for row in tables["entities"]}
    relation_types = {row["relation_type"] for row in tables["relation_types"]}
    relations = {row["relation_id"] for row in tables["relations"]}
    claims = {row["claim_id"] for row in tables["claims"]}
    claim_relations = {row["claim_relation_id"] for row in tables["claim_relations"]}

    checks = [
        ("aliases.entity_id", {row["entity_id"] for row in tables["aliases"]}, entities),
        ("relations.source_id", {row["source_id"] for row in tables["relations"]}, entities),
        ("relations.target_id", {row["target_id"] for row in tables["relations"]}, entities),
        ("relations.relation_type", {row["relation_type"] for row in tables["relations"]}, relation_types),
        ("relation_evidence.relation_id", {row["relation_id"] for row in tables["relation_evidence"]}, relations),
        ("relation_evidence.document_id", {row["document_id"] for row in tables["relation_evidence"]}, documents),
        ("claims.document_id", {row["document_id"] for row in tables["claims"]}, documents),
        ("claim_evidence.claim_id", {row["claim_id"] for row in tables["claim_evidence"]}, claims),
        ("claim_evidence.document_id", {row["document_id"] for row in tables["claim_evidence"]}, documents),
        ("entity_metrics.entity_id", {row["entity_id"] for row in tables["entity_metrics"]}, entities),
    ]
    for label, actual, allowed in checks:
        missing = actual - allowed
        if missing:
            errors.append(f"{label} has {len(missing)} unresolved references")

    endpoint_ids = entities | claims
    for field in ("source_id", "target_id"):
        missing = {row[field] for row in tables["claim_relations"]} - endpoint_ids
        if missing:
            errors.append(f"claim_relations.{field} has {len(missing)} unresolved references")
    referenced_claim_relations = {
        value
        for row in tables["claim_evidence"]
        for value in row["claim_relation_ids"].split(";")
        if value
    }
    missing = referenced_claim_relations - claim_relations
    if missing:
        errors.append(f"claim_evidence.claim_relation_ids has {len(missing)} unresolved references")


def validate_written_package(schema: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = schema or load_json(SCHEMA_PATH)
    errors: list[str] = []
    rows_by_table: dict[str, list[dict[str, Any]]] = {}

    for table_name, spec in schema["tables"].items():
        path = PACKAGE_ROOT / spec["path"]
        if not path.exists():
            errors.append(f"missing table file: {spec['path']}")
            continue
        if spec["format"] == "csv":
            rows = read_csv(path)
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream))
            if header != table_columns(schema, table_name):
                errors.append(f"{table_name} CSV header does not match schema")
        else:
            rows = []
            with path.open("r", encoding="utf-8-sig") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError as exc:
                            errors.append(f"{table_name} line {line_number} invalid JSON: {exc}")
        rows_by_table[table_name] = rows
        validate_table_rows(schema, table_name, rows, errors)

    if all(name in rows_by_table for name in schema["tables"]):
        validate_runtime_ids(schema, rows_by_table, errors)
        validate_foreign_keys(rows_by_table, errors)

    document_rows = rows_by_table.get("documents", [])
    article_dir = PACKAGE_ROOT / "corpus" / "articles"
    text_files = list(article_dir.glob("doc_*.txt")) if article_dir.exists() else []
    if len(text_files) != len(document_rows):
        errors.append(f"article file count {len(text_files)} != document rows {len(document_rows)}")
    for path in text_files:
        with path.open("r", encoding="utf-8") as stream:
            first_line = stream.readline()
        if first_line.startswith(HEADER_PREFIXES):
            errors.append(f"metadata header remains in {path.name}")
            break

    runtime_files = [
        path
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and "metadata" not in path.relative_to(PACKAGE_ROOT).parts
    ]
    forbidden_filenames = [path.name for path in runtime_files if SOURCE_ID_PATTERN.search(path.name)]
    if forbidden_filenames:
        errors.append(f"runtime filenames contain source-stage labels: {forbidden_filenames[:3]}")

    if errors:
        raise BuildError("portable package validation failed:\n- " + "\n- ".join(errors))

    return {
        "passed": True,
        "table_rows": {name: len(rows) for name, rows in rows_by_table.items()},
        "article_files": len(text_files),
        "runtime_file_count": len(runtime_files),
    }


def build_dataset_metadata(
    tables: dict[str, list[dict[str, Any]]],
    validation: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        "dataset_id": "huidu_xingyun_portable",
        "version": "1.0.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_name": "慧读星云：基于AI知识图谱的《星云大师全集》人间佛教智能研析与知识服务平台",
        "purpose": "竞赛演示、离线部署与LangChain运行的规范化只读数据包",
        "source_baselines": {
            "corpus": "hsingyun_texts_2026-06-12",
            "knowledge_graph": "final_reproducibility_release_2026-07-29",
            "quality": "manual_precision_recall_and_coreference_evaluation_2026",
        },
        "policies": {
            "runtime_tables_are_read_only": True,
            "source_identifiers_are_metadata_only": True,
            "article_files_contain_body_only": True,
            "combined_book_files_are_not_duplicated": True,
            "generated_indexes_and_chunks_belong_in_data_derived": True,
        },
        "schema": "../../config/data_schema.json",
        "counts": {name: len(rows) for name, rows in tables.items()},
        "validation": validation,
    }
    write_json(PACKAGE_ROOT / "metadata" / "dataset.json", metadata)
    return metadata


def build() -> None:
    config = load_json(CONFIG_PATH)
    schema = load_json(SCHEMA_PATH)
    print("BUILD portable corpus")
    documents, books = build_corpus(config, schema)
    print("BUILD portable graph")
    graph_tables, maps = build_graph(config, schema, documents)
    print("BUILD portable analytics")
    analytics_tables = build_analytics(config, schema, maps["entities"])
    print("BUILD quality metrics")
    build_quality(config)

    tables = {
        "documents": documents,
        "books": books,
        **graph_tables,
        **analytics_tables,
    }
    print("VALIDATE portable package")
    validation = validate_written_package(schema)
    build_dataset_metadata(tables, validation)
    write_json(
        PACKAGE_ROOT / "metadata" / "build_report.json",
        {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "passed": True,
            "counts": validation["table_rows"],
            "article_files": validation["article_files"],
            "notes": [
                "The build copies source data and never changes the source files.",
                "Runtime identifiers are deterministic hashes; source identifiers remain in metadata maps.",
                "Article filenames contain only document IDs and article files contain body text only.",
            ],
        },
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate the portable runtime data package.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the current package without rebuilding it.",
    )
    args = parser.parse_args()
    try:
        if args.validate_only:
            print(json.dumps(validate_written_package(), ensure_ascii=False, indent=2))
        else:
            build()
    except (BuildError, KeyError, ValueError) as exc:
        print(f"ERROR {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
