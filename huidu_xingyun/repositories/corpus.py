"""全文语料仓储：只读 ``data/package/corpus``。

第一版用关键词匹配标题/分类/书目 + 正文子串扫描，向量语义检索留待
``data/derived/vector_metadata`` 建立后再接入（见 `ADR-007` / `07` 规范）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config.settings import RuntimePaths
from .base import load_jsonl


class CorpusRepository:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._documents: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._semantic: Any = None  # VectorStore | None
        self._embedder: Any = None  # EmbeddingBackend | None

    def load(self) -> "CorpusRepository":
        self._documents = load_jsonl(self.paths.documents)
        self._by_id = {doc["document_id"]: doc for doc in self._documents}
        return self

    def attach_semantic(self, vector_store: Any, embedder: Any) -> None:
        """挂接语义检索后端；未挂接时 ``search_semantic`` 返回 None，调用方回退关键词。"""
        self._semantic = vector_store
        self._embedder = embedder

    @property
    def size(self) -> int:
        return len(self._documents)

    def get(self, document_id: str) -> dict[str, Any] | None:
        return self._by_id.get(document_id)

    def get_text(self, document_id: str) -> str:
        doc = self._by_id.get(document_id)
        if doc is None:
            return ""
        text_path = self.paths.article_text_root / Path(doc["text_path"]).name
        if text_path.exists():
            return text_path.read_text(encoding="utf-8")
        return ""

    def _match_score(self, doc: dict[str, Any], terms: list[str]) -> int:
        haystack = (
            f"{doc.get('title', '')} {doc.get('category', '')} "
            f"{doc.get('book_title', '')} {doc.get('book_id', '')}"
        )
        return sum(1 for term in terms if term in haystack)

    def search_metadata(self, query: str, k: int = 30) -> list[dict[str, Any]]:
        """按标题/分类/书目做子串匹配，速度快但不覆盖正文。"""
        terms = _terms(query)
        if not terms:
            return self._documents[:k]
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for index, doc in enumerate(self._documents):
            score = self._match_score(doc, terms)
            if score:
                scored.append((-score, index, doc))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [doc for _, _, doc in scored[:k]]

    def search_full_text(self, query: str, k: int = 8, window: int = 90) -> list[dict[str, Any]]:
        """扫描正文，返回命中片段。第一版逐篇读取，后续替换为倒排/向量索引。"""
        terms = _terms(query)
        if not terms:
            return []
        results: list[dict[str, Any]] = []
        for doc in self._documents:
            text = self.get_text(doc["document_id"])
            if not text:
                continue
            quote = _snippet(text, terms, window)
            if quote is None:
                continue
            results.append({**doc, "quote": quote})
            if len(results) >= k:
                break
        return results

    def search(self, query: str, k: int = 10, full_text: bool = True) -> list[dict[str, Any]]:
        """元数据优先，必要时补充正文检索。"""
        metadata = self.search_metadata(query, k=k)
        if full_text and len(metadata) < max(2, k // 2):
            merged = metadata + self.search_full_text(query, k=k)
            # 去重，按 document_id 稳定排序。
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for doc in merged:
                if doc["document_id"] in seen:
                    continue
                seen.add(doc["document_id"])
                unique.append(doc)
            return unique[:k]
        return metadata[:k]

    def search_semantic(self, query: str, k: int = 8) -> list[dict[str, Any]] | None:
        """语义召回（文章级向量）＋ 篇内关键词精排，回填 ``quote``。

        未挂接语义后端、索引缺失或后端失败时返回 ``None``，调用方回退关键词检索。
        """
        if self._semantic is None or self._embedder is None:
            return None
        try:
            query_vector = self._embedder.embed_query(query)
        except Exception:  # noqa: BLE001 - 语义后端失败回退
            return None
        try:
            hits = self._semantic.cosine_topk(query_vector, k=max(k * 3, 20))
        except Exception:  # noqa: BLE001
            return None
        results: list[dict[str, Any]] = []
        for index, score in hits:
            if index >= len(self._documents):
                continue
            doc = self._documents[index]
            text = self.get_text(doc["document_id"])
            quote = _snippet(text, content_terms(query), window=90) if text else ""
            if not quote and text:
                quote = text[:120].strip() + "…"
            results.append({**doc, "quote": quote, "score": round(score, 4)})
        return results[:k] if results else None


def _terms(query: str) -> list[str]:
    """把查询切分为关键词：中文查询通常整串即一个词，英文按空白切分。"""
    text = query.strip().strip("《》「」『』“”\"'")
    return [part for part in text.split() if part] or ([text] if text else [])


_STOPWORDS = (
    "在 是 的 了 与 和 有 中 把 被 为 对 从 到 及 以及 关于 请 我 你 他 她 它 "
    "我们 你们 他们 如何 什么 哪些 哪 哪篇 篇 文章 文中 谈到 提到 说出 请问 一下 "
    "有没有 是不是 怎么 为什么 哪个 哪本 哪一".split()
)


def content_terms(query: str) -> list[str]:
    """粗粒度抽取中文内容词：去标点与停用词后切分，供全文检索使用。

    第一版无分词器，属于工程近似；后续接入实体别名扩展与向量检索后替换。
    """
    text = re.sub(r"[^一-鿿A-Za-z0-9]+", " ", query)
    ordered_stopwords = sorted(_STOPWORDS, key=len, reverse=True)
    tokens: list[str] = []
    for token in text.split():
        for word in ordered_stopwords:
            token = token.replace(word, " ")
        for sub in token.split():
            if len(sub) >= 2:
                tokens.append(sub)
    return tokens


def _snippet(text: str, terms: list[str], window: int) -> str | None:
    best_index = -1
    for term in terms:
        index = text.find(term)
        if index >= 0:
            best_index = index
            break
    if best_index < 0:
        return None
    start = max(0, best_index - window)
    end = min(len(text), best_index + len(terms[0]) + window)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix
