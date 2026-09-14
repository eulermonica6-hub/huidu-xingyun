"""构建全文语义向量索引。

为 ``data/package/corpus/documents.jsonl`` 的 20,020 篇文献各建一条向量
（标题＋分类＋书目＋正文首段），归一化后写入
``data/derived/vector_metadata/document_embeddings.npy``，并写构建报告。

构建过程以内存映射文件增量写入 + 进度文件支持断点续跑（网络抖动不丢已嵌入结果）。

用法（在项目根目录）：:

    PYTHONPATH=src python scripts/build_vector_index.py
    PYTHONPATH=src python scripts/build_vector_index.py --local-bge
    PYTHONPATH=src python scripts/build_vector_index.py --validate-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from huidu_xingyun.config import SecretLoader, get_runtime_paths, get_settings  # noqa: E402
from huidu_xingyun.repositories.corpus import CorpusRepository  # noqa: E402
from huidu_xingyun.repositories.embeddings import (  # noqa: E402
    DashScopeEmbeddings,
    LocalBgeEmbeddings,
)

BODY_CHARS = 800
BATCH_SIZE = 10
CHECKPOINT_EVERY = 500


def embedding_text(doc: dict, body: str) -> str:
    head = body[:BODY_CHARS].strip() if body else ""
    return "。".join(
        part for part in (doc["title"], doc["category"], doc["book_title"], head) if part
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_backend(loader: SecretLoader, use_local_bge: bool):
    if use_local_bge:
        return LocalBgeEmbeddings()
    api_key = loader.first_key("ali")
    if not api_key:
        print("未找到 ali 密钥，回退本地 BGE 模型（首次需下载权重）。")
        return LocalBgeEmbeddings()
    return DashScopeEmbeddings(api_key)


def build_vector_index(use_local_bge: bool = False) -> dict:
    settings = get_settings()
    paths = get_runtime_paths()
    loader = SecretLoader(settings.secret_path)
    loader.load()

    backend = _load_backend(loader, use_local_bge)
    corpus = CorpusRepository(paths).load()
    documents = corpus._documents
    total = len(documents)

    out_dir = paths.derived_root / "vector_metadata"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_path = out_dir / "document_embeddings.build.npy"
    progress_path = out_dir / "build_progress.json"
    final_path = out_dir / "document_embeddings.npy"

    print(f"后端：{backend.name}/{backend.model}，文献数：{total}")
    texts = [embedding_text(doc, corpus.get_text(doc["document_id"])) for doc in documents]

    # 探明维度（嵌入第一条文本）。
    sample = backend.embed_documents([texts[0]])
    dim = len(sample[0])

    # 断点续跑。
    cursor = 0
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            compatible = (
                progress.get("backend") == backend.name
                and progress.get("model") == backend.model
                and progress.get("dim") == dim
                and progress.get("total") == total
            )
            if compatible and 0 < progress.get("completed", 0) < total:
                cursor = int(progress["completed"])
                print(f"恢复进度：已完成 {cursor}/{total}")
        except (json.JSONDecodeError, KeyError, OSError):
            cursor = 0

    mode = "r+" if (build_path.exists() and cursor > 0) else "w+"
    mmap = np.lib.format.open_memmap(build_path, mode=mode, dtype="float32", shape=(total, dim))

    def flush_progress(done: int) -> None:
        progress_path.write_text(
            json.dumps(
                {
                    "backend": backend.name,
                    "model": backend.model,
                    "dim": dim,
                    "total": total,
                    "completed": done,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    start_time = time.perf_counter()
    offset = cursor
    try:
        while offset < total:
            batch = texts[offset : offset + BATCH_SIZE]
            vectors = np.asarray(backend.embed_documents(batch), dtype=np.float32)
            end = offset + len(vectors)
            mmap[offset:end] = vectors
            offset = end
            if offset % CHECKPOINT_EVERY < BATCH_SIZE or offset == total:
                mmap.flush()
                flush_progress(offset)
                print(
                    f"  已嵌入 {offset}/{total}（{time.perf_counter() - start_time:.0f}s）",
                    flush=True,
                )
    except Exception:
        mmap.flush()
        flush_progress(offset)
        raise

    mmap.flush()

    # 归一化后写最终文件。
    matrix = np.asarray(mmap, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    matrix = matrix / norms
    np.save(final_path, matrix)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "backend": backend.name,
        "model": backend.model,
        "count": int(matrix.shape[0]),
        "dim": int(matrix.shape[1]),
        "body_chars": BODY_CHARS,
        "source": "data/package/corpus/documents.jsonl",
        "npy_file": str(final_path.relative_to(PROJECT_ROOT)),
        "npy_sha256": sha256_file(final_path),
        "normalized": True,
    }
    (out_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 关掉内存映射再清理中间产物（Windows 上文件句柄占用会阻止删除）。
    try:
        mmap._mmap.close()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    del mmap
    build_path.unlink(missing_ok=True)
    progress_path.unlink(missing_ok=True)
    print(
        f"完成：{matrix.shape[0]} × {matrix.shape[1]}，写入 {final_path}"
        f"（{final_path.stat().st_size / 1e6:.1f} MB）"
    )
    return report


def validate_index() -> dict:
    paths = get_runtime_paths()
    corpus = CorpusRepository(paths).load()
    npy_path = paths.derived_root / "vector_metadata" / "document_embeddings.npy"
    if not npy_path.exists():
        raise RuntimeError(f"索引不存在：{npy_path}")
    matrix = np.load(npy_path, mmap_mode="r")
    errors = []
    if matrix.ndim != 2:
        errors.append(f"矩阵应为 2 维，实际 {matrix.ndim}")
    if matrix.shape[0] != corpus.size:
        errors.append(f"向量数 {matrix.shape[0]} != 文献数 {corpus.size}")
    norms = np.linalg.norm(matrix[:100], axis=1) if matrix.shape[0] else np.array([])
    if norms.size and not np.allclose(norms, 1.0, atol=1e-3):
        errors.append("前 100 行未归一化")
    if errors:
        raise RuntimeError("索引校验失败：" + "；".join(errors))
    return {"count": int(matrix.shape[0]), "dim": int(matrix.shape[1]), "ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="构建或校验语义向量索引。")
    parser.add_argument("--local-bge", action="store_true", help="用本地 BGE 模型而非 DashScope API")
    parser.add_argument("--validate-only", action="store_true", help="只冷读校验不重建")
    args = parser.parse_args()

    if args.validate_only:
        print(json.dumps(validate_index(), ensure_ascii=False, indent=2))
        return 0

    report = build_vector_index(use_local_bge=args.local_bge)
    print(json.dumps(validate_index(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())