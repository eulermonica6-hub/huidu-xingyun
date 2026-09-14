"""受控工具层：把仓储能力包装为 LangChain 工具。

主编排图当前直接调用仓储以获得结构化结果；这些工具供未来 ReAct 流程
或外部集成使用，也可在测试中复用。工具只暴露只读能力，不接触数据库密码。
"""

from .corpus_tools import build_corpus_tools
from .entity_tools import build_entity_tools
from .evidence_tools import build_evidence_tools
from .graph_tools import build_graph_tools

__all__ = [
    "build_corpus_tools",
    "build_entity_tools",
    "build_evidence_tools",
    "build_graph_tools",
]
