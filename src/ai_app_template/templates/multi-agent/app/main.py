"""FastAPI 入口（multi-agent 版）。

接口：
- GET  /health   —— 健康检查 + 网关统计
- POST /v1/tasks —— 提交任务，多智能体协作完成后返回最终产出
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
    from app.graph.builder import build_graph
    from app.llm.gateway import get_gateway

    return build_graph(get_gateway())


class TaskRequest(BaseModel):
    task: str = Field(min_length=5, description="要完成的任务描述")
    max_rounds: int = Field(4, ge=1, le=10, description="轮次预算")
    trace_id: str | None = None


class TaskResponse(BaseModel):
    trace_id: str
    final: str
    rounds: int
    research_notes: list[str]
    drafts: list[str]
    critiques: list[str]
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
        "breakers": {alias: b.state for alias, b in gateway.breakers.items()},
        "gateway_stats": gateway.stats.summary(),
    }


@app.post("/v1/tasks", response_model=TaskResponse)
def run_task(payload: TaskRequest) -> TaskResponse:
    from app.llm.gateway import get_gateway

    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    graph = get_graph()
    result = graph.invoke(
        {"task": payload.task, "max_rounds": payload.max_rounds, "trace_id": trace_id}
    )
    return TaskResponse(
        trace_id=trace_id,
        final=result.get("final", ""),
        rounds=result.get("round", 0),
        research_notes=result.get("research_notes") or [],
        drafts=result.get("drafts") or [],
        critiques=result.get("critiques") or [],
        errors=result.get("errors") or [],
        gateway_stats=get_gateway().stats.summary(),
    )
