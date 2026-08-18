"""Researcher 工人：把任务拆成调研要点（ResearchSet）。"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import ResearchSet, strict_json_schema

logger = logging.getLogger(__name__)


def researcher_node(gateway):
    def node(state: dict) -> dict:
        request = LLMRequest(
            messages=[
                {"role": "system", "content": "你是调研专员。把任务拆解为 2-4 条执行要点，严格按 schema 输出。"},
                {"role": "user", "content": f"任务：{state['task']}"},
            ],
            task="extract",
            structured=True,
            response_format=strict_json_schema(ResearchSet),
            metadata={"node": "researcher", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            return {"errors": [f"researcher 失败: {exc}"]}

        try:
            parsed = ResearchSet.model_validate_json(response.content)
            points = [p.point for p in parsed.points]
        except ValidationError:
            points = [response.content.strip()]  # 退化为单条要点

        return {
            "research_notes": points,
            "messages": [{"role": "assistant", "content": f"[researcher] 调研要点：{'；'.join(points)}"}],
        }

    return node
