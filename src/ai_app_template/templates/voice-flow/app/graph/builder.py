"""LangGraph 图组装（voice-flow 版）。

图结构（全线性 + 每节点兜底）：
    START -> ingest(确定性清洗) -> summarize(LLM) -> extract_todos(LLM) -> finalize(确定性归并) -> END

ASR（语音转文字）由外部服务完成，本模板的输入就是转写文本——
不绑定任何语音供应商；接入 Whisper 等服务只需在调用方先完成转写。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.state import MeetingState


def build_graph(gateway: Any | None = None, settings: Any | None = None):
    from app.graph.nodes.extract_todos_node import extract_todos_node
    from app.graph.nodes.finalize_node import finalize_node
    from app.graph.nodes.ingest_node import ingest_node
    from app.graph.nodes.summarize_node import summarize_node

    settings = settings or get_settings()
    if gateway is None:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()

    graph = StateGraph(MeetingState)
    graph.add_node("ingest", ingest_node(gateway))
    graph.add_node("summarize", summarize_node(gateway))
    graph.add_node("extract_todos", extract_todos_node(gateway))
    graph.add_node("finalize", finalize_node(gateway))

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "summarize")
    graph.add_edge("summarize", "extract_todos")
    graph.add_edge("extract_todos", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
