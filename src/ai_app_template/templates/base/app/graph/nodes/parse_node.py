"""解析节点：原始文档 -> 结构化分节（纯确定性，不调用 LLM）。

工程判断：能用正则/规则解决的事就不要喂给模型 —— 更快、更便宜、
完全可测试。这个节点同时是「工作流里确定性工序」的教学样本。
"""

from __future__ import annotations

import re

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.M)


def split_sections(document: str, target_chars: int = 1200) -> list[dict]:
    """按 Markdown 标题切分；没有标题则按空行分段打包成约 target_chars 的块。"""
    doc = document.strip()
    if not doc:
        return []

    matches = list(HEADING_RE.finditer(doc))
    if matches:
        sections = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
            text = doc[match.end() : end].strip()
            sections.append({"heading": match.group(2).strip(), "text": text})
        return sections

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", doc) if p.strip()]
    sections: list[dict] = []
    buffer: list[str] = []
    size = 0
    for para in paragraphs:
        buffer.append(para)
        size += len(para)
        if size >= target_chars:
            sections.append({"heading": f"chunk-{len(sections) + 1}", "text": "\n\n".join(buffer)})
            buffer, size = [], 0
    if buffer:
        sections.append({"heading": f"chunk-{len(sections) + 1}", "text": "\n\n".join(buffer)})
    return sections


def parse_node(gateway):
    """节点工厂。gateway 参数保持统一签名（parse 不用模型，但便于教学对照）。"""

    def node(state: dict) -> dict:
        sections = split_sections(state["document"])
        return {"parsed_sections": sections}

    return node
