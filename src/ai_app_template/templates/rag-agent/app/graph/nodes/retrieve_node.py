"""检索节点：查询 -> top-k 相关文档块（纯确定性，不调用 LLM）。"""

from __future__ import annotations

from app.retrieval.store import InMemoryStore


def retrieve_node(store: InMemoryStore, default_k: int = 4):
    def node(state: dict) -> dict:
        k = state.get("top_k") or default_k
        hits = store.search(state["query"], k=k)
        return {"retrieved": hits}

    return node
