"""FastAPI 入口：把 LangGraph 工作流暴露为 HTTP 服务。

接口：
- GET  /health      —— 健康检查 + 网关统计 + 熔断器状态（可观测性出口）
- POST /v1/reviews  —— 提交文档，返回审阅结论（findings + summary + errors）

启动：uvicorn app.main:app --reload
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.config import get_settings
    from app.utils.logger import setup_logging

    settings = get_settings()
    setup_logging(settings.debug)
    yield


app = FastAPI(
    title="{{ project_name }}",
    version="0.1.0",
    description="{{ description }}",
    lifespan=lifespan,
)


@lru_cache(maxsize=1)
def get_graph():
    """进程内单例图。测试用 monkeypatch 替换本函数即可注入 FakeGateway。"""
    from app.graph.builder import build_graph
    from app.llm.gateway import get_gateway

    return build_graph(get_gateway())


class ReviewRequest(BaseModel):
    document: str = Field(min_length=20, description="待审文档全文（Markdown/纯文本）")
    trace_id: str | None = Field(None, description="调用方指定的链路 ID，缺省自动生成")


class ReviewResponse(BaseModel):
    trace_id: str
    findings: list[dict]
    summary: str
    errors: list[str]
    gateway_stats: dict


@app.get("/health")
def health() -> dict:
    from app.config import get_settings
    from app.llm.gateway import get_gateway

    settings = get_settings()
    gateway = get_gateway()
    return {
        "status": "ok",
        "app": settings.app_name,
        "models": list(settings.models),
        "tier_chains": settings.tier_chains,
        "breakers": {alias: b.state for alias, b in gateway.breakers.items()},
        "gateway_stats": gateway.stats.summary(),
    }


@app.post("/v1/reviews", response_model=ReviewResponse)
def run_review(payload: ReviewRequest) -> ReviewResponse:
    from app.llm.gateway import get_gateway

    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    graph = get_graph()
    result = graph.invoke({"document": payload.document, "trace_id": trace_id})
    return ReviewResponse(
        trace_id=trace_id,
        findings=result.get("reviewed_findings") or [],
        summary=result.get("summary", ""),
        errors=result.get("errors") or [],
        gateway_stats=get_gateway().stats.summary(),
    )
