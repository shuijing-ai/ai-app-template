"""转写清洗节点：ASR 文本 -> 干净文本（纯确定性，不调用 LLM）。

ASR 输出常带三类噪音：时间戳（[00:12:34] / 00:12）、说话人标签（张三：/【张三】）、
口头填充与重复空白。本节点用正则一次清掉，并统计清理量供观测。
工程判断：确定性清洗比「让 LLM 顺便清理」便宜两个数量级且完全可测试。
"""

from __future__ import annotations

import re

TIMESTAMP_RE = re.compile(r"\[?\b\d{1,2}:\d{2}(?::\d{2})?\b\]?")
# 行首允许空白：时间戳移除后常留下前导空格，说话人标签在其之后
SPEAKER_RE = re.compile(r"^\s*[【\[]?[\w\u4e00-\u9fff]{1,12}[】\]]?\s*[：:]\s*", re.M)
# 连同其后的逗号/空白一并清掉，避免留下「，，」
FILLER_RE = re.compile(r"\b(嗯+|啊+|呃+|就是说|对对对|那个这个)\b[，,]?\s*")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def clean_transcript(transcript: str) -> tuple[str, int]:
    """返回 (干净文本, 清理掉的噪音片段数)。"""
    noise = 0

    def _count_sub(pattern: re.Pattern, repl: str, text: str) -> str:
        nonlocal noise
        new_text, n = pattern.subn(repl, text)
        noise += n
        return new_text

    text = _count_sub(TIMESTAMP_RE, "", transcript)
    text = _count_sub(SPEAKER_RE, "", text)
    text = _count_sub(FILLER_RE, "", text)
    text = MULTI_SPACE_RE.sub(" ", text)

    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line), noise


def ingest_node(gateway):
    """节点工厂。gateway 参数保持统一签名（ingest 不用模型，便于教学对照）。"""

    def node(state: dict) -> dict:
        cleaned, noise = clean_transcript(state["transcript"])
        return {"cleaned": cleaned, "noise_removed": noise}

    return node
