"""API 层请求/响应契约。

版本化 API：当前为 ``/api/v1``；未来新增功能在本包内新增同前缀路由即可，
不破坏既有客户端。响应直接复用领域层 :class:`~huidu_xingyun.schemas.response.FinalResponse`，
前端据此渲染答案、关系路径、证据卡与覆盖/防御说明。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..schemas.response import FinalResponse


class AskRequest(BaseModel):
    query: str = Field(min_length=1, description="用户自然语言问题")
    history: list[dict[str, Any]] = Field(default_factory=list, description="多轮上下文")


class ExportRequest(AskRequest):
    pass


class ExportResponse(BaseModel):
    path: str = Field(description="导出的 Markdown 证据包路径")
    final_response: FinalResponse


class HealthResponse(BaseModel):
    status: str
    llm_ready: bool
    corpus_size: int
    graph: dict[str, Any]
    vector_index: bool
    models: dict[str, str]
    version: str