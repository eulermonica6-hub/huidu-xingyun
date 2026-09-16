"""应用上下文装配：构建一次、多处复用的入口（CLI 与 API 服务共用）。

把密钥加载、数据仓储、语义检索与模型装配收敛到 :func:`build_context`，
返回 :class:`~huidu_xingyun.agent.context.AgentContext`。服务端在启动期构建一次
并持单例，避免每请求重载 25k 实体 + 20k 文档 + 向量索引。
"""

from __future__ import annotations

import logging

from .agent import AgentContext
from .config import SecretLoader, get_runtime_paths, get_settings
from .models.cache import LLMCache
from .models.factory import ModelBundle, ModelFactory
from .repositories import CorpusRepository, GraphRepository
from .repositories.vector_store import VectorStore

logger = logging.getLogger("huidu_xingyun.bootstrap")


def _attach_semantic(corpus: CorpusRepository, paths, loader: SecretLoader) -> None:
    """如果向量索引存在，挂接语义检索；任何失败都静默降级为关键词检索。"""
    index_path = paths.derived_root / "vector_metadata" / "document_embeddings.npy"
    if not index_path.exists():
        return
    try:
        from .repositories.embeddings import DashScopeEmbeddings, LocalBgeEmbeddings

        api_key = loader.first_key("ali")
        embedder = DashScopeEmbeddings(api_key) if api_key else LocalBgeEmbeddings()
        store = VectorStore(index_path)
        if store.count != corpus.size:
            return
        corpus.attach_semantic(store, embedder)
    except Exception:  # noqa: BLE001 - 语义后端可选，失败无感降级
        logger.warning("语义检索后端不可用，回退关键词检索", exc_info=True)


def build_context(use_llm: bool = True) -> AgentContext:
    settings = get_settings()
    paths = get_runtime_paths()

    loader = SecretLoader(settings.secret_path)
    loader.load()

    graph = GraphRepository(paths).load()
    corpus = CorpusRepository(paths).load()
    _attach_semantic(corpus, paths, loader)

    bundle = ModelBundle()
    if use_llm:
        try:
            cache = LLMCache(paths.cache / "llm_cache.jsonl")
            bundle = ModelFactory(settings, loader).build_bundle(cache=cache)
        except Exception as exc:  # noqa: BLE001 - 降级为离线规则模式
            logger.warning(f"模型初始化失败：{type(exc).__name__}，将以离线规则模式运行")

    return AgentContext(bundle=bundle, graph=graph, corpus=corpus, settings=settings, paths=paths)