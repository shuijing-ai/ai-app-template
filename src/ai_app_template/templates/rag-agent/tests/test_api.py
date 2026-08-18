"""API 层测试（rag-agent 版）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.graph.builder import build_graph
from app.llm.fakes import FakeGateway
from app.retrieval.store import load_kb


def client_with_fake_graph(monkeypatch) -> TestClient:
    graph = build_graph(FakeGateway(), store=load_kb(Path("data/sample_kb.md")))
    monkeypatch.setattr(main, "get_graph", lambda: graph)
    return TestClient(main.app)


def test_health():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["kb_docs"] >= 1


def test_answer_endpoint(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post(
        "/v1/answers", json={"query": "退货政策是什么？运费谁承担？"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["citation_valid"] is True
    assert body["citations"][0]["doc_id"] == "退货政策"
    assert "退货政策" in body["retrieved_doc_ids"]


def test_answer_endpoint_validates_short_query(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/answers", json={"query": "退"})
    assert response.status_code == 422
