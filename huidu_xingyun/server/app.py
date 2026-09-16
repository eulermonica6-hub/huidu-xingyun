"""FastAPI 应用：把 ``run_agent`` 薄封装为 HTTP 接口。

设计要点：

1. **AgentContext 单例复用** —— 启动期在 lifespan 里构建一次，存 ``app.state.ctx``，
   全部请求复用，避免每请求重载 25k 实体 + 20k 文档 + 向量索引。
2. **同步端点** —— ``run_agent`` 是阻塞调用（含 LLM 推理），用 ``def`` 端点让 FastAPI
   在线程池执行，不阻塞事件循环。
3. **版本化前缀 /api/v1** —— 后续新增功能（前端图谱子图、馆员反馈、流式回答等）在本包
   新增同名前缀路由即可，不破坏 v1 客户端。

运行：``python -m huidu_xingyun.server`` 或
``uvicorn huidu_xingyun.server.app:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .. import __version__
from ..agent import export_evidence_package, run_agent
from ..bootstrap import build_context
from .schemas import AskRequest, ExportRequest, ExportResponse, FinalResponse, HealthResponse

logger = logging.getLogger("huidu_xingyun.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动期构建一次，全部请求复用；构建失败（如无密钥）时降级为离线规则模式。
    app.state.ctx = build_context(use_llm=True)
    logger.info("AgentContext 已就绪")
    yield
    # 预留关闭钩子：未来可在此释放 mmap / 连接池。


app = FastAPI(title="慧读星云 API", version=__version__, lifespan=lifespan)

# 预留前端接入：本地演示放开跨域；生产按域名收紧。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/api/v1/ask", response_model=FinalResponse, tags=["问答"])
def ask(request: AskRequest, http: Request) -> FinalResponse:
    """单次问答：返回结构化结果（答案 / 关系路径 / 证据卡 / 覆盖与防御说明）。"""
    ctx = http.app.state.ctx
    return run_agent(ctx, request.query, conversation_context=request.history)


@app.post("/api/v1/export", response_model=ExportResponse, tags=["导出"])
def export(request: ExportRequest, http: Request) -> ExportResponse:
    """问答并导出 Markdown 研究证据包。"""
    ctx = http.app.state.ctx
    final = run_agent(ctx, request.query, conversation_context=request.history)
    path = export_evidence_package(final, ctx.paths)
    return ExportResponse(path=str(path), final_response=final)


@app.get("/api/v1/health", response_model=HealthResponse, tags=["运维"])
def health(http: Request) -> HealthResponse:
    """健康检查：模型就绪 / 语料规模 / 图谱概览 / 向量索引存在性。"""
    ctx = http.app.state.ctx
    settings = ctx.settings
    vector_index = (ctx.paths.derived_root / "vector_metadata" / "document_embeddings.npy").exists()
    return HealthResponse(
        status="ok",
        llm_ready=ctx.bundle.router is not None and ctx.bundle.reasoner is not None,
        corpus_size=ctx.corpus.size,
        graph=ctx.graph.overview(),
        vector_index=vector_index,
        models={
            "router": f"{settings.router_provider}/{settings.router_model}",
            "reasoner": f"{settings.reasoner_provider}/{settings.reasoner_model}",
            "verifier": f"{settings.verifier_provider}/{settings.verifier_model}",
            "fallback": f"{settings.fallback_provider}/{settings.fallback_model}",
        },
        version=__version__,
    )


@app.get("/api/v1/exports/{filename}", tags=["导出"])
def download_export(filename: str, http: Request) -> FileResponse:
    """下载已导出的证据包（文件名来自 /api/v1/export 的 path）。"""
    ctx = http.app.state.ctx
    path = Path(ctx.paths.outputs) / Path(filename).name  # 防目录穿越
    if not path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="证据包不存在")
    return FileResponse(path, media_type="text/markdown", filename=path.name)


# 预留扩展入口：未来按同样模式新增，例如
#   POST /api/v1/feedback        馆员关系纠错（写入 runtime/logs/feedback.jsonl）
#   GET  /api/v1/entities/{id}/neighborhood  前端「展开子图」
#   POST /api/v1/ask/stream      流式回答（SSE）