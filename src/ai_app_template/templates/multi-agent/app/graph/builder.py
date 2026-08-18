"""LangGraph 图组装（multi-agent 版）。

图结构（Supervisor 模式）：

    START -> supervisor ->(动态路由) researcher | writer | critic | END
                 ^                  |
                 +------------------+  工人执行完回到 supervisor

supervisor 每轮根据进展决定下一个工人；轮次预算与 critic 的 pass
共同保证流程必然终止 —— 「会结束的多智能体」才是能上线的多智能体。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.state import TeamState


def route_supervisor(state: dict) -> str:
    next_worker = state.get("next_worker", "__end__")
    return next_worker if next_worker in {"researcher", "writer", "critic"} else "__end__"


def build_graph(gateway: Any | None = None, settings: Any | None = None, max_rounds: int = 4):
    from app.graph.nodes.critic_node import critic_node
    from app.graph.nodes.researcher_node import researcher_node
    from app.graph.nodes.supervisor_node import supervisor_node
    from app.graph.nodes.writer_node import writer_node

    settings = settings or get_settings()
    if gateway is None:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()

    graph = StateGraph(TeamState)
    graph.add_node("supervisor", supervisor_node(gateway, max_rounds=max_rounds))
    graph.add_node("researcher", researcher_node(gateway))
    graph.add_node("writer", writer_node(gateway))
    graph.add_node("critic", critic_node(gateway))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {"researcher": "researcher", "writer": "writer", "critic": "critic", "__end__": END},
    )
    for worker in ("researcher", "writer", "critic"):
        graph.add_edge(worker, "supervisor")
    return graph.compile()
