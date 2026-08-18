"""API 层测试：TestClient + monkeypatch 注入 FakeGateway，全程离线。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main
from app.graph.builder import build_graph
from app.llm.fakes import FakeGateway

DOC = (
    "## 交付条款\n本项目将在三个月内完成交付。\n\n"
    "## 违约条款\n违约金为合同总额的百分之五十。\n\n"
    "## 运维条款\n乙方负责全部运维工作。"
)


def client_with_fake_graph(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "get_graph", lambda: build_graph(FakeGateway()))
    return TestClient(main.app)


def test_health():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "flash" in body["models"]
    assert "gateway_stats" in body


def test_review_endpoint(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/reviews", json={"document": DOC})
    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert len(body["findings"]) == 2
    assert "审阅完成" in body["summary"]


def test_review_endpoint_validates_short_document(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/reviews", json={"document": "太短"})
    assert response.status_code == 422
