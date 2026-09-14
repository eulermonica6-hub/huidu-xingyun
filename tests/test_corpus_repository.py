"""全文语料仓储测试。"""

from __future__ import annotations

from huidu_xingyun.repositories.corpus import CorpusRepository, content_terms


def test_corpus_size_matches_frozen(corpus_repo: CorpusRepository) -> None:
    assert corpus_repo.size == 20020


def test_search_metadata_finds_docs(corpus_repo: CorpusRepository) -> None:
    results = corpus_repo.search_metadata("六祖壇經", k=5)
    assert results
    assert all("document_id" in doc for doc in results)


def test_get_text_returns_body(corpus_repo: CorpusRepository) -> None:
    first = corpus_repo._documents[0]
    text = corpus_repo.get_text(first["document_id"])
    assert text


def test_content_terms_extracts_keywords() -> None:
    terms = content_terms("星云大师在哪些文章中谈到共生")
    assert "共生" in terms
    assert "哪些" not in terms
    assert "谈到" not in terms
