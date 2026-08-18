"""Critic 工人：评审最新草稿（CritiqueSet）。

兜底：LLM 不可用或输出不合法时给出 revise —— 严格的质量把关姿态，
宁可多改一轮，不可放行未审内容。
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import CritiqueSet, strict_json_schema

logger = logging.getLogger(__name__)


def critic_node(gateway):
    def node(state: dict) -> dict:
        drafts = state.get("drafts") or []
        if not drafts:
            return {"verdict": "revise", "critiques": ["无草稿可评审，要求 writer 先产出。"]}

        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": "你是严格的评审。草稿完全满足任务要求给 pass，否则给 revise 并列出具体问题。",
                },
                {"role": "user", "content": f"任务：{state['task']}\n\n草稿：\n{drafts[-1]}"},
            ],
            task="review",
            structured=True,
            response_format=strict_json_schema(CritiqueSet),
            metadata={"node": "critic", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            return {"verdict": "revise", "critiques": [f"评审服务不可用，保守要求重写: {exc}"], "errors": [f"critic 失败: {exc}"]}

        try:
            parsed = CritiqueSet.model_validate_json(response.content)
            verdict = parsed.verdict
            issues = [i.issue for i in parsed.issues]
        except ValidationError:
            verdict, issues = "revise", ["评审输出无法解析，保守要求重写"]

        summary = f"verdict={verdict}；问题：{'；'.join(issues) if issues else '无'}"
        return {"verdict": verdict, "critiques": [summary], "messages": [{"role": "assistant", "content": f"[critic] {summary}"}]}

    return node
