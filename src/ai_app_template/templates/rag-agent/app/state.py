"""分层 State 定义（rag-agent 版）。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SharedState(TypedDict, total=False):
    trace_id: str
    errors: Annotated[list[str], operator.add]


class RagState(SharedState, total=False):
    query: str
    top_k: int
    retrieved: list[dict]  # retrieve 输出：[{doc_id, text, score}]
    answer: str
    citations: list[dict]  # generate 输出：[{doc_id, quote}]，verify 会清洗
    citation_valid: bool
    attempt: int
    verify_feedback: str  # 上一次校验失败原因，回传给 generate 纠正
