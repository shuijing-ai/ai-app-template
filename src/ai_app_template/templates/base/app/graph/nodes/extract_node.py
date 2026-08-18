"""提取节点：LLM 结构化提取候选问题（FindingSet）。

失败策略（面试高频考点）：
- LLM 彻底不可用：记录错误、extract_ok=False，由条件边决定重试；
- 输出无法解包：findings 为空，同样交给条件边重试一次；
- 连续 2 次仍失败：放弃提取，工作流带着空 findings 继续 —— 降级不宕机。
"""

from __future__ import annotations

import json
import logging

from app.config import Settings, get_settings
from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import FindingSet, strict_json_schema
from app.utils.extractor import safe_extract_items

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是资深文档审阅专家。从给定文本中提取所有值得关注的风险点，"
    "逐字引用原文，严格按 schema 输出；没有风险点就返回空列表，不要编造。"
)

REQUIRED_KEYS = {"quote", "issue", "category", "severity"}


def extract_node(gateway, settings: Settings | None = None):
    settings = settings or get_settings()

    def node(state: dict) -> dict:
        sections = state.get("parsed_sections") or []
        corpus = "\n\n".join(f"[{s['heading']}]\n{s['text']}" for s in sections)
        corpus = corpus[: settings.extract_max_input_chars]
        attempts = state.get("extract_attempts", 0) + 1

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"待审文本：\n{corpus}"},
        ]
        request = LLMRequest(
            messages=messages,
            task="extract",
            structured=True,
            response_format=strict_json_schema(FindingSet),
            metadata={"node": "extract", "trace_id": state.get("trace_id", ""), "attempt": attempts},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("extract 第 %s 次失败：%s", attempts, exc)
            return {
                "errors": [f"extract 尝试 {attempts} 失败: {exc}"],
                "extract_attempts": attempts,
                "extract_ok": attempts >= 2,  # 两次都失败就放弃，交给下游兜底
            }

        items = safe_extract_items(response.content)
        findings = [item for item in items if REQUIRED_KEYS.issubset(item)]
        logger.info(
            "extract 第 %s 次完成：%s 条候选", attempts, len(findings),
            extra={"ctx": {"node": "extract", "attempt": attempts}},
        )
        return {
            "findings": findings,
            "extract_attempts": attempts,
            "extract_ok": bool(findings) or attempts >= 2,
        }

    return node
