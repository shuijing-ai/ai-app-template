"""Writer 工人：依据调研要点（与最新评审意见）产出/修改草稿。"""

from __future__ import annotations

import logging

from app.llm.gateway import GatewayExhaustedError, LLMRequest

logger = logging.getLogger(__name__)


def writer_node(gateway):
    def node(state: dict) -> dict:
        notes = state.get("research_notes") or []
        drafts = state.get("drafts") or []
        critiques = state.get("critiques") or []

        user_content = f"任务：{state['task']}\n调研要点：\n" + "\n".join(f"- {n}" for n in notes)
        if drafts:
            user_content += f"\n\n当前草稿：\n{drafts[-1]}"
        if critiques:
            user_content += f"\n\n最新评审意见（必须逐条处理）：\n{critiques[-1]}"

        request = LLMRequest(
            messages=[
                {"role": "system", "content": "你是写手。直接输出正文，不要任何前缀或解释。"},
                {"role": "user", "content": user_content},
            ],
            task="rewrite",
            metadata={"node": "writer", "trace_id": state.get("trace_id", ""), "version": len(drafts) + 1},
        )
        try:
            response = gateway.complete(request)
        except GatewayExhaustedError as exc:
            return {"errors": [f"writer 失败（保留第 {len(drafts)} 版）: {exc}"]}

        draft = response.content.strip()
        return {"drafts": [draft], "messages": [{"role": "assistant", "content": f"[writer] 产出第 {len(drafts) + 1} 版草稿"}]}

    return node
