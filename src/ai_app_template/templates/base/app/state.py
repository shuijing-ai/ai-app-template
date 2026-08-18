"""分层 State 定义。

LangGraph 的 State 是整个工作流唯一的数据总线，分层的好处：
- ``SharedState``：所有模板共享的通用字段（trace、错误收集）；
- 业务 State 继承它，只声明自己的字段；
- 用 ``Annotated[list, operator.add]`` 声明「追加式」字段，
  重试/多轮节点写入时自动合并而不是互相覆盖。
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SharedState(TypedDict, total=False):
    """跨模板通用字段。"""

    trace_id: str
    errors: Annotated[list[str], operator.add]


class ReviewState(SharedState, total=False):
    """review-flow 业务字段。

    total=False：每个字段都可缺席，节点只返回自己写过的键，
    LangGraph 按 reducer 规则合并进全局 State。
    """

    document: str
    parsed_sections: list[dict]  # parse 节点输出：[{heading, text}]
    findings: Annotated[list[dict], operator.add]  # extract 节点输出
    extract_attempts: int
    extract_ok: bool
    reviewed_findings: list[dict]  # review 节点输出
    summary: str  # summary 节点输出
