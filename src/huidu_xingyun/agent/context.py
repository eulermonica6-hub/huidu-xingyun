"""编排上下文：把模型、仓储与配置收敛为一个对象。"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import RuntimePaths, Settings
from ..models.factory import ModelBundle
from ..repositories.corpus import CorpusRepository
from ..repositories.graph import GraphRepository


@dataclass
class AgentContext:
    bundle: ModelBundle
    graph: GraphRepository
    corpus: CorpusRepository
    settings: Settings
    paths: RuntimePaths
