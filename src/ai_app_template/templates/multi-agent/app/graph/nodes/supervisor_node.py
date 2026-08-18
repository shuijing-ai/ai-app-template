"""Supervisor 节点：多智能体的调度中枢。

调度规则（确定性优先，LLM 只做需要判断的部分）：
1. 第 1 轮固定派 researcher（任务总是先调研）；
2. critic 给出 pass -> 立即收尾；
3. 超出轮次预算 -> 强制收尾（防止 agent 循环失控烧钱）;
4. 其余情况由 LLM 决定下一个工人。

兜底：LLM 不可用时直接收尾并返回已有最佳产出，绝不让循环空转。
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import NextAction, strict_json_schema

logger = logging.getLogger(__name__)

WORKERS = ("researcher", "writer", "critic")

SUPERVISOR_PROMPT = (
    "你是团队调度主管。根据当前任务进展决定下一个执行的工人："
    "researcher（调研）/ writer（撰写/修改）/ critic（评审）/ FINISH（完成）。"
    "原则上：未调研先调研；有新调研就写稿；有新稿就评审；评审 revise 则重写。"
)


def _finish_message(state: dict, budget_exceeded: bool = False) -> str:
    drafts = state.get("drafts") or []
    base = drafts[-1] if drafts else "任务未能产出结果（无可用草稿）。"
    if budget_exceeded:
        base += "\n\n（已达轮次预算，强制收尾）"
    return base


def supervisor_node(gateway, max_rounds: int = 4):
    def node(state: dict) -> dict:
        round_no = state.get("round", 0) + 1

        if round_no == 1:
            return {"round": round_no, "next_worker": "researcher"}

        if state.get("verdict") == "pass":
            return {"round": round_no, "next_worker": "__end__", "final": _finish_message(state)}

        if round_no > max_rounds:
            logger.warning("轮次预算耗尽（%s > %s），强制收尾", round_no, max_rounds)
            return {"round": round_no, "next_worker": "__end__", "final": _finish_message(state, True)}

        progress = (
            f"任务：{state['task']}\n"
            f"调研要点 {len(state.get('research_notes') or [])} 条；"
            f"草稿 {len(state.get('drafts') or [])} 版；"
            f"最近评审：{(state.get('critiques') or ['无'])[-1]}"
        )
        request = LLMRequest(
            messages=[
                {"role": "system", "content": SUPERVISOR_PROMPT},
                {"role": "user", "content": progress},
            ],
            task="planning",
            structured=True,
            response_format=strict_json_schema(NextAction),
            metadata={"node": "supervisor", "trace_id": state.get("trace_id", ""), "round": round_no},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("supervisor 决策失败，兜底收尾: %s", exc)
            return {
                "round": round_no,
                "next_worker": "__end__",
                "final": _finish_message(state),
                "errors": [f"supervisor 兜底收尾: {exc}"],
            }

        try:
            action = NextAction.model_validate_json(response.content)
            next_worker = action.next if action.next in WORKERS else "__end__"
        except ValidationError:
            logger.warning("supervisor 输出无法解析，兜底收尾")
            next_worker = "__end__"

        return {"round": round_no, "next_worker": next_worker}

    return node
