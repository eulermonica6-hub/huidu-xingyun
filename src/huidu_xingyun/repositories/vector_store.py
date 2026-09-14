"""向量索引存储：加载 ``document_embeddings.npy``（mmap）并做余弦 top-k 检索。

索引内向量已按行归一化为单位向量（构建脚本负责），故点积即余弦相似度。
只读，不修改 ``data/package``；索引存放在 ``data/derived/vector_metadata``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class VectorStore:
    def __init__(self, embeddings_path: Path) -> None:
        self.path = embeddings_path
        self._vectors = np.load(embeddings_path, mmap_mode="r")
        if self._vectors.ndim != 2:
            raise ValueError(f"embedding matrix must be 2-D, got {self._vectors.ndim}")

    @property
    def count(self) -> int:
        return int(self._vectors.shape[0])

    @property
    def dim(self) -> int:
        return int(self._vectors.shape[1])

    def cosine_topk(self, query_vector: list[float], k: int = 30) -> list[tuple[int, float]]:
        query = np.asarray(query_vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm == 0.0:
            return []
        query = query / norm
        scores = self._vectors @ query  # [N]，索引向量已归一化
        k = min(k, scores.shape[0])
        if k <= 0:
            return []
        # argpartition 取 top-k，再按分数降序排列。
        if k < scores.shape[0]:
            indices = np.argpartition(-scores, k)[:k]
        else:
            indices = np.arange(scores.shape[0])
        ranked = sorted(
            indices.tolist(), key=lambda i: float(scores[i]), reverse=True
        )[:k]
        return [(int(i), float(scores[i])) for i in ranked]