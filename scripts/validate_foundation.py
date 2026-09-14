from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "data_paths.json"
SECRET_PATH = PROJECT_ROOT.parent / "LLM api key.txt"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def resolve(path_value: str) -> Path:
    return (PROJECT_ROOT / path_value).resolve()


def check_path(label: str, path: Path, errors: list[str]) -> None:
    if path.exists():
        print(f"PASS path {label}: {path}")
    else:
        errors.append(f"missing path {label}: {path}")


def read_csv_header(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        return set(next(reader))


def validate_csv_contract(
    label: str,
    path: Path,
    required_columns: set[str],
    errors: list[str],
) -> None:
    actual = read_csv_header(path)
    missing = sorted(required_columns - actual)
    if missing:
        errors.append(f"{label} missing columns: {missing}")
    else:
        print(f"PASS schema {label}: {len(actual)} columns")


def validate_corpus(config: dict[str, Any], errors: list[str]) -> None:
    corpus = config["corpus"]
    expected = corpus["expected"]
    manifest_path = resolve(corpus["manifest"])
    text_base = resolve(corpus["manifest_text_file_base"])

    rows: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"manifest line {line_number} is invalid JSON: {exc}")

    ids = [row.get("article_id") for row in rows]
    categories = {row.get("category") for row in rows}
    books = {row.get("book_id") for row in rows}
    missing_files = []
    for row in rows:
        relative = Path(str(row.get("text_file", "")).replace("\\", "/"))
        if not (text_base / relative).exists():
            missing_files.append(str(relative))

    actual = {
        "manifest_rows": len(rows),
        "unique_article_ids": len(set(ids)),
        "article_text_files": sum(
            1 for path in resolve(corpus["article_text_root"]).rglob("*") if path.is_file()
        ),
        "combined_book_files": sum(
            1 for path in resolve(corpus["combined_book_root"]).rglob("*") if path.is_file()
        ),
        "categories": len(categories),
        "books": len(books),
    }

    for key, expected_value in expected.items():
        actual_value = actual[key]
        if actual_value != expected_value:
            errors.append(
                f"corpus count {key}: expected {expected_value}, actual {actual_value}"
            )
        else:
            print(f"PASS corpus {key}: {actual_value}")

    if missing_files:
        errors.append(f"manifest references {len(missing_files)} missing text files")
    else:
        print("PASS corpus manifest paths: 0 missing text files")


def validate_secrets(errors: list[str]) -> None:
    if not SECRET_PATH.exists():
        errors.append(f"missing external secret file: {SECRET_PATH}")
        return

    accepted = {"deepseek", "groq", "nvapi", "agnes"}
    labels: set[str] = set()
    unlabeled = 0
    pattern = re.compile(r"^([^:=：]+)\s*[:=：]\s*(.+)$")
    for raw_line in SECRET_PATH.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        text = raw_line.strip()
        if not text:
            continue
        match = pattern.match(text)
        if not match:
            unlabeled += 1
            continue
        label = match.group(1).strip().lower()
        if label in accepted:
            labels.add(label)

    print(f"PASS secret file exists: {SECRET_PATH}")
    print(f"PASS named secret labels: {', '.join(sorted(labels)) or 'none'}")
    print(f"INFO ignored unlabeled secret lines: {unlabeled}")
    if not {"deepseek", "groq", "nvapi"}.issubset(labels):
        errors.append("required named providers are not all present")


def main() -> int:
    errors: list[str] = []
    config = load_json(CONFIG_PATH)

    check_path("workspace_root", resolve(config["workspace_root"]), errors)
    check_path("corpus_manifest", resolve(config["corpus"]["manifest"]), errors)
    check_path("article_text_root", resolve(config["corpus"]["article_text_root"]), errors)
    check_path("combined_book_root", resolve(config["corpus"]["combined_book_root"]), errors)

    graph = config["knowledge_graph"]
    for key in (
        "entity_registry",
        "entity_alias_registry",
        "relation_registry",
        "stable_relations",
        "stable_evidence",
        "claim_nodes",
        "claim_relations",
        "claim_evidence",
        "release_summary",
        "quality_gate",
    ):
        check_path(f"knowledge_graph.{key}", resolve(graph[key]), errors)

    for section_name in ("analysis", "evaluation"):
        for key, value in config[section_name].items():
            check_path(f"{section_name}.{key}", resolve(value), errors)

    if not errors:
        validate_corpus(config, errors)
        validate_csv_contract(
            "entity_registry",
            resolve(graph["entity_registry"]),
            {"entity_id", "preferred_label", "entity_type", "active_in_stable_graph"},
            errors,
        )
        validate_csv_contract(
            "alias_registry",
            resolve(graph["entity_alias_registry"]),
            {"alias", "normalized_alias", "entity_id", "alias_resolution_status"},
            errors,
        )
        validate_csv_contract(
            "stable_relations",
            resolve(graph["stable_relations"]),
            {"edge_uid", "source_entity_id", "relation_key", "target_entity_id", "graph_layer"},
            errors,
        )
        validate_csv_contract(
            "stable_evidence",
            resolve(graph["stable_evidence"]),
            {"evidence_uid", "edge_uid", "article_uid", "paragraph_uid", "evidence_text"},
            errors,
        )
        validate_csv_contract(
            "claim_relations",
            resolve(graph["claim_relations"]),
            {"edge_uid", "source_entity_id", "relation_key", "target_entity_id", "graph_layer"},
            errors,
        )

    validate_secrets(errors)

    if errors:
        print("\nFOUNDATION VALIDATION FAILED")
        for error in errors:
            print(f"ERROR {error}")
        return 1

    print("\nFOUNDATION VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
