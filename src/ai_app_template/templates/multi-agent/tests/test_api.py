"""API 层测试（multi-agent 版）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main
from app.graph.builder import build_graph
from app.llm.fakes import DRAFT_TEXT, FakeGateway

TASK = "为 ai-app-template 写一段 100 字以内的产品介绍。"


def client_with_fake_graph(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "get_graph", lambda: build_graph(FakeGateway()))
    return TestClient(main.app)


def test_health():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_task_endpoint(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/tasks", json={"task": TASK})
    assert response.status_code == 200
    body = response.json()
    assert body["final"] == DRAFT_TEXT
    assert body["rounds"] == 4
    assert len(body["research_notes"]) == 2


def test_task_endpoint_validates_short_task(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/tasks", json={"task": "太短"})
    assert response.status_code == 422
