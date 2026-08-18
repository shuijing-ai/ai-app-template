"""汇总节点：生成人类可读的审阅结论。

兜底策略：LLM 不可用时退化为「确定性模板拼接」——
按类别和严重度排序输出要点，保证接口永远有非空 summary。
这是「LLM 增强而非 LLM 依赖」设计哲学的直接体现。
"""

from __future__ import annotations

import logging

from app.llm.gateway import GatewayExhaustedError, LLMRequest

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "你是技术写作专家。把审阅发现汇总成 200 字以内的中文结论，突出高风险项与行动建议。"


def deterministic_summary(findings: list[dict]) -> str:
    ranked = sorted(findings, key=lambda f: f.get("severity", 0), reverse=True)
    lines = [f"- [{f.get('category', 'other')}|P{f.get('severity', '?')}] {f.get('issue', '')}" for f in ranked[:10]]
    head = f"共 {len(findings)} 条待处理问题（确定性汇总，LLM 暂不可用）："
    return head + "\n" + "\n".join(lines)


def summary_node(gateway):
    def node(state: dict) -> dict:
        findings = state.get("reviewed_findings") or []
        if not findings:
            return {"summary": "未发现需要关注的问题。"}

        request = LLMRequest(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"审阅发现：\n{findings!r}"},
            ],
            task="general",
            metadata={"node": "summary", "trace_id": state.get("trace_id", "")},
        )
        try:
            response = gateway.complete(request)
            return {"summary": response.content.strip() or deterministic_summary(findings)}
        except GatewayExhaustedError as exc:
            logger.warning("summary 兜底: %s", exc)
            return {"summary": deterministic_summary(findings), "errors": [f"summary 兜底: {exc}"]}

    return node
