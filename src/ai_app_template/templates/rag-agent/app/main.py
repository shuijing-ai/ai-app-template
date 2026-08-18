"""FastAPI 入口（rag-agent 版）。

接口：
- GET  /health      —— 健康检查 + 网关统计 + 知识库文档数
- POST /v1/answers  —— 知识库问答（带引用校验）
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


class AnswerRequest(BaseModel):
    query: str = Field(min_length=2, description="用户问题")
    top_k: int = Field(4, ge=1, le=10, description="检索返回的文档块数量")
    trace_id: str | None = None


class AnswerResponse(BaseModel):
    trace_id: str
    answer: str
    citations: list[dict]
    citation_valid: bool
    retrieved_doc_ids: list[str]
    errors: list[str]
    gateway_stats: dict


@app.get("/health")
def health() -> dict:
    from app.config import get_settings
    from app.graph.builder import load_default_kb
    from app.llm.gateway import get_gateway

    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "kb_docs": len(load_default_kb().doc_ids()),
        "models": list(settings.models),
        "breakers": {alias: b.state for alias, b in get_gateway().breakers.items()},
        "gateway_stats": get_gateway().stats.summary(),
    }


@app.post("/v1/answers", response_model=AnswerResponse)
def answer(payload: AnswerRequest) -> AnswerResponse:
    from app.llm.gateway import get_gateway

    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    result = get_graph().invoke(
        {"query": payload.query, "top_k": payload.top_k, "trace_id": trace_id}
    )
    return AnswerResponse(
        trace_id=trace_id,
        answer=result.get("answer", ""),
        citations=result.get("citations") or [],
        citation_valid=bool(result.get("citation_valid")),
        retrieved_doc_ids=[r.get("doc_id", "") for r in result.get("retrieved") or []],
        errors=result.get("errors") or [],
        gateway_stats=get_gateway().stats.summary(),
    )
