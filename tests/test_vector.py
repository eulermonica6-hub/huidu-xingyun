"""向量存储与语义检索回退离线测试。"""

from __future__ import annotations

import numpy as np

from huidu_xingyun.repositories.vector_store import VectorStore


def _write_vectors(path, matrix: np.ndarray) -> None:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    np.save(path, matrix / norms)


def test_vector_store_cosine_topk(tmp_path) -> None:
    # 三个正交方向的单位向量，检索向量向方向 1 倾斜。
    matrix = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32
    )
    path = tmp_path / "doc_embeddings.npy"
    _write_vectors(path, matrix)

    store = VectorStore(path)
    assert store.count == 3
    assert store.dim == 3

    hits = store.cosine_topk([0.1, 0.99, 0.1], k=2)
    indices = [i for i, _ in hits]
    assert indices[0] == 1  # 最相似的是第二行
    assert len(hits) == 2


def test_corpus_semantic_none_without_attach(corpus_repo) -> None:
    # 未挂接语义后端时返回 None，供调用方回退关键词检索。
    assert corpus_repo.search_semantic("星云大师谈共生", k=3) is None


def test_corpus_semantic_graceful_on_embedder_failure(corpus_repo, tmp_path) -> None:
    # 嵌入后端抛错时 search_semantic 静默返回 None，而非向上抛异常。
    matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    path = tmp_path / "doc_embeddings.npy"
    _write_vectors(path, matrix)
    store = VectorStore(path)

    class _BrokenEmbedder:
        def embed_query(self, text: str):
            raise RuntimeError("embedding unavailable")

    corpus_repo.attach_semantic(store, _BrokenEmbedder())
    assert corpus_repo.search_semantic("测试", k=2) is None