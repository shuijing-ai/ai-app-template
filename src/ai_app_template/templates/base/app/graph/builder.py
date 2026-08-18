"""LangGraph 图组装入口。

图结构：
    START -> parse -> extract ->(条件边) extract(重试) / review -> summary -> END

条件边 ``route_after_extract`` 是本模板的教学重点：
提取失败时重试一次（LLM 输出不稳定是常态，重试是第一道防线），
连续失败则带着空结果继续 —— 用「降级继续」替代「整个请求 500」。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.state import ReviewState


def route_after_extract(state: dict) -> str:
    if state.get("extract_ok"):
        return "review"
    if state.get("extract_attempts", 0) >= 2:
        return "review"
    return "extract"


def build_graph(gateway: Any | None = None, settings: Any | None = None):
    """编译图。gateway 参数是依赖注入点：测试传 FakeGateway/FailingGateway。"""
    from app.graph.nodes.extract_node import extract_node
    from app.graph.nodes.parse_node import parse_node
    from app.graph.nodes.review_node import review_node
    from app.graph.nodes.summary_node import summary_node

    settings = settings or get_settings()
    if gateway is None:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()

    graph = StateGraph(ReviewState)
    graph.add_node("parse", parse_node(gateway))
    graph.add_node("extract", extract_node(gateway, settings))
    graph.add_node("review", review_node(gateway))
    graph.add_node("summary", summary_node(gateway))

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "extract")
    graph.add_conditional_edges(
        "extract",
        route_after_extract,
        {"extract": "extract", "review": "review"},
    )
    graph.add_edge("review", "summary")
    graph.add_edge("summary", END)
    return graph.compile()
