"""校验节点：确定性 grounding check（不调用 LLM）。

逐条验证引用：doc_id 必须在本次检索结果中，quote 必须真的出现在该文档里
（忽略空白差异，取前 40 字做包含判断以容忍模型截断）。
伪造引用是 RAG 落地最大的坑，这道工序用 30 行确定性代码解决。
"""

from __future__ import annotations

import json
import re

QUOTE_PREFIX_CHARS = 40


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def verify_citations(retrieved: list[dict], citations: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (有效引用, 伪造引用)。"""
    texts = {str(r["doc_id"]): _normalize(r.get("text", "")) for r in retrieved}
    valid, forged = [], []
    for citation in citations:
        doc_id = str(citation.get("doc_id", ""))
        quote = _normalize(str(citation.get("quote", "")))
        body = texts.get(doc_id, "")
        if body and quote and quote[:QUOTE_PREFIX_CHARS] in body:
            valid.append(citation)
        else:
            forged.append(citation)
    return valid, forged


def verify_node():
    def node(state: dict) -> dict:
        retrieved = state.get("retrieved") or []
        valid, forged = verify_citations(retrieved, state.get("citations") or [])
        # 语义约定：citation_valid 只校验「引用真伪」（无伪造即合法）；
        # 引用完整性（该不该有引用、够不够）由评测的 min_citations 门槛负责。
        result = {"citations": valid, "citation_valid": not forged}
        if forged:
            result["verify_feedback"] = (
                "以下引用未通过系统校验（doc_id 不存在或原文不匹配），已被剔除："
                + json.dumps(forged, ensure_ascii=False)
                + "。请只引用资料中真实存在且逐字准确的原文。"
            )
        else:
            result["verify_feedback"] = ""
        return result

    return node
