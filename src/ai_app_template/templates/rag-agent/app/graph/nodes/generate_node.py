"""生成节点：基于检索资料生成带引用的回答（AnswerSet）。

失败策略：
- 检索为空：直接返回「知识库无相关资料」，不浪费一次 LLM 调用；
- LLM 不可用：返回固定提示文案，错误入 state.errors，流程继续；
- 输出不合法：退化为纯文本回答（无引用），由 verify 触发重试。
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.llm.gateway import GatewayExhaustedError, LLMRequest
from app.schema.wrappers import AnswerSet, strict_json_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是严谨的知识库问答助手。只依据给定资料回答，每条关键论断都要给出来自资料的引用"
    "（doc_id + 逐字摘抄的原文）。资料里没有的信息就直说不知道，绝不编造。"
)


def generate_node(gateway, settings=None):
    settings = settings  # 保留统一签名；本节点暂不需要额外配置

    def node(state: dict) -> dict:
        attempt = state.get("attempt", 0) + 1
        retrieved = state.get("retrieved") or []
        if not retrieved:
            return {
                "answer": "知识库中没有找到与该问题相关的资料，无法回答。",
                "citations": [],
                "citation_valid": True,
                "attempt": attempt,
            }

        context = "\n\n".join(f"[doc_id: {r['doc_id']}]\n{r['text']}" for r in retrieved)
        feedback = state.get("verify_feedback") or ""
        user_content = f"资料：\n{context}\n\n问题：{state['query']}"
        if feedback:
            user_content += f"\n\n（系统提示：{feedback}）"

        request = LLMRequest(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            task="extract",
            structured=True,
            response_format=strict_json_schema(AnswerSet),
            metadata={"node": "generate", "trace_id": state.get("trace_id", ""), "attempt": attempt},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            logger.warning("generate 第 %s 次失败: %s", attempt, exc)
            return {
                "answer": "模型服务暂时不可用，请稍后重试。",
                "citations": [],
                "citation_valid": False,
                "attempt": attempt,
                "errors": [f"generate 尝试 {attempt} 失败: {exc}"],
            }

        try:
            parsed = AnswerSet.model_validate_json(response.content)
            citations = [c.model_dump() for c in parsed.citations]
            answer = parsed.answer
        except ValidationError:
            logger.warning("generate 输出无法解析为 AnswerSet，退化为纯文本")
            answer, citations = response.content.strip(), []

        return {"answer": answer, "citations": citations, "citation_valid": False, "attempt": attempt}

    return node
