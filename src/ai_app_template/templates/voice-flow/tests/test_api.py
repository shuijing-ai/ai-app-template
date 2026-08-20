"""API 层测试（voice-flow 版）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main
from app.graph.builder import build_graph
from app.llm.fakes import FakeGateway

TRANSCRIPT = (
    "[00:00] 张三：本次迭代还剩登录模块，预计周四提测。\n"
    "[00:21] 李四：测试环境今天恢复，大家下午可以自测。\n"
    "[00:45] 王五：文档我来更新，周五前发出来。"
)


def client_with_fake_graph(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "get_graph", lambda: build_graph(FakeGateway()))
    return TestClient(main.app)


def test_health():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_meeting_endpoint(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post(
        "/v1/meetings", json={"transcript": TRANSCRIPT}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert "发布计划" in body["summary"]
    assert len(body["todos"]) == 2  # 预置 3 条含 1 重复，finalize 后 2 条
    assert body["noise_removed"] > 0


def test_meeting_endpoint_validates_short_transcript(monkeypatch):
    response = client_with_fake_graph(monkeypatch).post("/v1/meetings", json={"transcript": "太短"})
    assert response.status_code == 422
