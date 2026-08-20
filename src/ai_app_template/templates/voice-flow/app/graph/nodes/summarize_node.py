"""摘要节点：LLM 生成会议摘要与议题（SummarySet）。

兜底：LLM 不可用时退化为确定性摘要（清洗文本的前 200 字）+ 空议题，
接口永远有非空 summary。
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import SummarySet, strict_json_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "你是会议纪要专家。基于转写文本生成摘要与关键议题，严格按 schema 输出，不要编造未提及的内容。"

FALLBACK_MAX_CHARS = 200


def deterministic_summary(cleaned: str) -> str:
    head = cleaned[:FALLBACK_MAX_CHARS].strip()
    return f"（LLM 摘要暂不可用，确定性节选）{head}"


def summarize_node(gateway):
    def node(state: dict) -> dict:
        cleaned = state.get("cleaned") or ""
        if not cleaned:
            return {"summary": "转写内容为空，无摘要。", "topics": []}

        request = LLMRequest(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"会议转写：\n{cleaned}"},
            ],
            task="general",
            structured=True,
            response_format=strict_json_schema(SummarySet),
            metadata={"node": "summarize", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("summarize 兜底: %s", exc)
            return {
                "summary": deterministic_summary(cleaned),
                "topics": [],
                "errors": [f"summarize 兜底: {exc}"],
            }

        try:
            parsed = SummarySet.model_validate_json(response.content)
            return {"summary": parsed.summary, "topics": parsed.topics}
        except ValidationError:
            logger.warning("summarize 输出无法解析，退化为纯文本摘要")
            return {"summary": response.content.strip() or deterministic_summary(cleaned), "topics": []}

    return node
