"""FastAPI API 层测试（离线上下文，不调 LLM）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import huidu_xingyun.server.app as app_module
from huidu_xingyun.server.app import app


def test_health_endpoint(ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "build_context", lambda use_llm=True: ctx)
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["corpus_size"] == 20020
        assert isinstance(data["vector_index"], bool)  # 值取决于本机是否已构建索引


def test_ask_endpoint(ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "build_context", lambda use_llm=True: ctx)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/ask",
            json={"query": "慈悲与教育是什么关系", "history": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] == "graph_direct"
        assert data["answer"]
        assert data["evidence_cards"]


def test_export_endpoint(ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "build_context", lambda use_llm=True: ctx)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/export",
            json={"query": "慈悲与教育是什么关系", "history": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"].endswith(".md")
        assert data["final_response"]["route"] == "graph_direct"


def test_frontend_served(ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "build_context", lambda use_llm=True: ctx)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "慧读星云" in resp.text
        assert "/api/v1/ask" in resp.text