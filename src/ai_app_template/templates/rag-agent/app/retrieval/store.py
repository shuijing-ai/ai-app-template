"""内置检索：纯 Python TF-IDF 倒排打分。

为什么不用向量库起手？RAG 工作流的价值在校验链路（检索->引用->验证），
而不是某个具体存储。先用零依赖实现跑通全链路、写好测试，
生产化时把 ``InMemoryStore`` 换成 Milvus/Qdrant（实现相同的 add/search 接口）即可。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

# 英文/数字整词 + 中文逐字（对中文而言「字」就是最小检索单元，粗糙但有效）
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")

HEADING_RE = re.compile(r"^##\s+(.+)$", re.M)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def chunk_text(text: str, target_chars: int = 500) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buffer, size = [], [], 0
    for para in paragraphs:
        buffer.append(para)
        size += len(para)
        if size >= target_chars:
            chunks.append("\n".join(buffer))
            buffer, size = [], 0
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks


class InMemoryStore:
    """add(doc_id, text) / search(query, k) —— 对齐向量库的常见接口形态。"""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def add(self, doc_id: str, text: str) -> None:
        self._docs[doc_id] = {"text": text, "chunks": chunk_text(text)}

    def doc_ids(self) -> list[str]:
        return list(self._docs)

    def get_text(self, doc_id: str) -> str | None:
        doc = self._docs.get(doc_id)
        return doc["text"] if doc else None

    def search(self, query: str, k: int = 4) -> list[dict]:
        flat: list[tuple[str, str]] = [
            (doc_id, chunk) for doc_id, doc in self._docs.items() for chunk in doc["chunks"]
        ]
        if not flat:
            return []
        query_terms = set(tokenize(query))

        chunk_terms = [set(tokenize(text)) for _, text in flat]
        df: Counter = Counter()
        for terms in chunk_terms:
            df.update(terms)

        n = len(flat)
        scored: list[dict] = []
        for i, (doc_id, text) in enumerate(flat):
            overlap = query_terms & chunk_terms[i]
            if not overlap:
                continue
            tf = Counter(tokenize(text))
            score = sum(
                (math.log((n + 1) / (df[t] + 1)) + 1.0) * (1 + math.log(tf[t])) for t in overlap
            )
            scored.append({"doc_id": doc_id, "text": text, "score": round(score, 4)})

        scored.sort(key=lambda item: item["score"], reverse=True)
        best: dict[str, dict] = {}
        for item in scored:  # 同文档多 chunk 命中时只保留最高分
            best.setdefault(item["doc_id"], item)
        return list(best.values())[:k]


def load_kb(path: Path) -> InMemoryStore:
    """按二级标题切分 Markdown 知识库，每个 ## 标题是一个文档。"""
    store = InMemoryStore()
    content = path.read_text(encoding="utf-8")
    matches = list(HEADING_RE.finditer(content))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        store.add(match.group(1).strip(), content[match.end() : end].strip())
    return store
