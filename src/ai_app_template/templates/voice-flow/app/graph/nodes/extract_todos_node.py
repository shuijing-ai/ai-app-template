"""待办抽取节点：LLM 从转写中抽取待办（TodoSet）。

兜底：LLM 不可用或输出不合法时返回空待办并记录错误——
宁可少报待办（用户可回看原文），不可编造待办（用户会照着假待办干活）。
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import TodoSet, strict_json_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是会议待办抽取专家。只抽取转写中明确提到的行动项（谁、做什么、何时），"
    "严格按 schema 输出；没有行动项就返回空列表，绝不编造。"
)


def extract_todos_node(gateway):
    def node(state: dict) -> dict:
        cleaned = state.get("cleaned") or ""
        if not cleaned:
            return {"todos": []}

        request = LLMRequest(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"会议转写：\n{cleaned}"},
            ],
            task="extract",
            structured=True,
            response_format=strict_json_schema(TodoSet),
            metadata={"node": "extract_todos", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("extract_todos 空结果兜底: %s", exc)
            return {"todos": [], "errors": [f"extract_todos 兜底: {exc}"]}

        try:
            parsed = TodoSet.model_validate_json(response.content)
            return {"todos": [todo.model_dump() for todo in parsed.todos]}
        except ValidationError:
            logger.warning("extract_todos 输出无法解析，返回空")
            return {"todos": [], "errors": ["extract_todos 输出无法解析为 TodoSet"]}

    return node
