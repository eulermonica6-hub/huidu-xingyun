"""测试夹具：会话级加载只读数据包，注入空模型包以离线运行。"""

from __future__ import annotations

import pytest

from huidu_xingyun.agent import AgentContext
from huidu_xingyun.config import get_runtime_paths, get_settings
from huidu_xingyun.models.factory import ModelBundle
from huidu_xingyun.repositories import CorpusRepository, GraphRepository


@pytest.fixture(scope="session")
def paths():
    return get_runtime_paths()


@pytest.fixture(scope="session")
def graph_repo(paths):
    return GraphRepository(paths).load()


@pytest.fixture(scope="session")
def corpus_repo(paths):
    return CorpusRepository(paths).load()


@pytest.fixture()
def ctx(graph_repo, corpus_repo, paths):
    return AgentContext(
        bundle=ModelBundle(),
        graph=graph_repo,
        corpus=corpus_repo,
        settings=get_settings(),
        paths=paths,
    )
