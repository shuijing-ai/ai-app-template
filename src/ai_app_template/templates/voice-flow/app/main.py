"""FastAPI 入口（voice-flow 版）。

接口：
- GET  /health       —— 健康检查 + 网关统计
- POST /v1/meetings  —— 提交会议转写，返回摘要 + 待办
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


class MeetingRequest(BaseModel):
    transcript: str = Field(min_length=20, description="ASR 转写文本（模板不绑定语音供应商）")
    trace_id: str | None = None


class MeetingResponse(BaseModel):
    trace_id: str
    summary: str
    topics: list[str]
    todos: list[dict]
    noise_removed: int
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


@app.post("/v1/meetings", response_model=MeetingResponse)
def run_meeting(payload: MeetingRequest) -> MeetingResponse:
    from app.llm.gateway import get_gateway

    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    result = get_graph().invoke({"transcript": payload.transcript, "trace_id": trace_id})
    return MeetingResponse(
        trace_id=trace_id,
        summary=result.get("summary", ""),
        topics=result.get("topics") or [],
        todos=result.get("finalized_todos") or [],
        noise_removed=result.get("noise_removed", 0),
        errors=result.get("errors") or [],
        gateway_stats=get_gateway().stats.summary(),
    )
