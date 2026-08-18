"""分层 State 定义（multi-agent 版）。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SharedState(TypedDict, total=False):
    trace_id: str
    errors: Annotated[list[str], operator.add]


class TeamState(SharedState, total=False):
    task: str
    max_rounds: int  # 轮次预算：supervisor 超出后强制收尾
    round: int
    next_worker: str  # researcher | writer | critic | __end__
    verdict: str  # critic 结论：pass | revise

    research_notes: Annotated[list[str], operator.add]
    drafts: Annotated[list[str], operator.add]
    critiques: Annotated[list[str], operator.add]
    messages: Annotated[list[dict], operator.add]  # 全过程留痕（可观测）

    final: str
