"""复核节点：LLM 逐条判断候选问题是否保留（ReviewSet）。

兜底策略：宁可多报，不可漏报 —— LLM 不可用时全量保留候选问题，
错误记录进 state.errors，由上层决定如何呈现。
"""

from __future__ import annotations

import json
import logging

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import ReviewSet, strict_json_schema
from app.utils.extractor import safe_extract_items

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是审阅质量把关人。逐条评估候选问题是否真实成立："
    "quote 是否真的支持 issue、category 是否恰当、是否过度挑剔。"
    "严格按 schema 输出决策列表。"
)


def review_node(gateway):
    def node(state: dict) -> dict:
        findings = state.get("findings") or []
        if not findings:
            return {"reviewed_findings": []}

        candidates = [
            {"index": i, **{k: f.get(k) for k in ("quote", "issue", "category", "severity")}}
            for i, f in enumerate(findings)
        ]
        request = LLMRequest(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"候选问题列表：\n{json.dumps(candidates, ensure_ascii=False)}"},
            ],
            task="review",
            structured=True,
            response_format=strict_json_schema(ReviewSet),
            metadata={"node": "review", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("review 失败，全量保留候选: %s", exc)
            return {"reviewed_findings": findings, "errors": [f"review 失败，全量保留: {exc}"]}

        decisions = safe_extract_items(response.content, key_hints=("decisions", "items"))
        keep_indexes = {
            d["index"] for d in decisions if d.get("keep") is True and isinstance(d.get("index"), int)
        }
        reviewed = [f for i, f in enumerate(findings) if i in keep_indexes]
        if not reviewed and decisions:
            reviewed = findings  # 模型全否决视为异常，兜底全保留
        logger.info("review 完成：%s/%s 条保留", len(reviewed), len(findings))
        return {"reviewed_findings": reviewed}

    return node
