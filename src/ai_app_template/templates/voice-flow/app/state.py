"""分层 State 定义（voice-flow 版）。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SharedState(TypedDict, total=False):
    trace_id: str
    errors: Annotated[list[str], operator.add]


class MeetingState(SharedState, total=False):
    transcript: str  # ASR 转写文本（由外部语音服务提供，模板不绑定供应商）
    cleaned: str  # ingest 输出：去除时间戳/说话人标签后的干净文本
    summary: str
    topics: list[str]
    todos: Annotated[list[dict], operator.add]  # extract_todos 输出：[{action, owner, due}]
    finalized_todos: list[dict]  # finalize 输出：去重排序后的待办
    noise_removed: int  # ingest 清理掉的噪音片段数（可观测）
