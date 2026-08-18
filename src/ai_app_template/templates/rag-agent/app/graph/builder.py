"""LangGraph 图组装（rag-agent 版）。

图结构：
    START -> retrieve -> generate ->(条件边) generate(引用修正重试) / END

store 是依赖注入点：测试注入内存构造的小知识库，
生产由 ``load_kb(data/xxx.md)`` 或向量库实现提供。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.retrieval.store import InMemoryStore
from app.state import RagState

DEFAULT_KB_PATH = Path("data/sample_kb.md")


def route_after_verify(state: dict) -> str:
    if state.get("citation_valid"):
        return "__end__"
    if state.get("attempt", 0) >= 2:
        return "__end__"
    return "generate"


def load_default_kb() -> InMemoryStore:
    if DEFAULT_KB_PATH.is_file():
        from app.retrieval.store import load_kb

        return load_kb(DEFAULT_KB_PATH)
    return InMemoryStore()  # 空库：检索为空时流程优雅降级


def build_graph(gateway: Any | None = None, settings: Any | None = None, store: InMemoryStore | None = None):
    from app.graph.nodes.generate_node import generate_node
    from app.graph.nodes.retrieve_node import retrieve_node
    from app.graph.nodes.verify_node import verify_node

    settings = settings or get_settings()
    if gateway is None:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()
    store = store or load_default_kb()

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve_node(store))
    graph.add_node("generate", generate_node(gateway, settings))
    graph.add_node("verify", verify_node())

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"generate": "generate", "__end__": END},
    )
    return graph.compile()
