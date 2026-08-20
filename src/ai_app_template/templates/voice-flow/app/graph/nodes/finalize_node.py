"""归并节点：待办去重与排序（纯确定性，不调用 LLM）。

ASR/LLM 都可能产出重复或近似重复的待办；有负责人/有截止时间的行动项
比裸行动项更「实」。确定性归并保证输出稳定可测。
"""

from __future__ import annotations

import re

MAX_TODOS = 10


def _norm(action: str) -> str:
    return re.sub(r"\s+", "", action).lower()


def finalize_todos(todos: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for todo in todos:
        key = _norm(str(todo.get("action", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(todo)

    def rank(todo: dict) -> tuple[int, int]:
        # 有截止时间 > 有负责人 > 其余；同组保持原序（用索引稳定排序）
        return (0 if todo.get("due") else 1, 0 if todo.get("owner") else 1)

    ranked = sorted(enumerate(deduped), key=lambda pair: (rank(pair[1]), pair[0]))
    return [todo for _, todo in ranked][:MAX_TODOS]


def finalize_node(gateway):
    """节点工厂。gateway 参数保持统一签名（finalize 不用模型）。"""

    def node(state: dict) -> dict:
        todos = state.get("todos") or []
        return {"finalized_todos": finalize_todos(todos)}

    return node
