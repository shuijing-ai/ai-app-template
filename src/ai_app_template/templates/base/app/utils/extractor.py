"""通用安全解包：把「任何形态的 LLM 输出」变成 list[dict]。

真实世界的模型输出千奇百怪：包了一层 markdown 代码围栏、外面多套了个
键、直接给了裸列表、或者干脆不是合法 JSON。所有节点统一通过
``safe_extract_items`` 解包 —— 它永不抛异常，最差返回空列表，
调用方据此走重试或兜底路径，而不是让整个工作流崩掉。
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _load_json_text(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 容错：截取第一个 { 到最后一个 } 之间的内容再试一次
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _from_dict(payload: dict, key_hints: tuple[str, ...]) -> list[dict]:
    for key in key_hints:
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    # 没有命中提示键：取第一个值恰为列表的键（模型经常自作主张改键名）
    for value in payload.values():
        if isinstance(value, list) and all(isinstance(v, dict) for v in value):
            return value
    return []


def safe_extract_items(payload: Any, key_hints: tuple[str, ...] = ("items", "findings", "decisions")) -> list[dict]:
    """把任意形态的结构化输出解包成 list[dict]，永不抛异常。"""
    if isinstance(payload, BaseModel):
        return safe_extract_items(payload.model_dump(), key_hints)
    if isinstance(payload, str):
        fenced = _FENCE_RE.search(payload)
        payload = _load_json_text(fenced.group(1) if fenced else payload)
    if isinstance(payload, str):  # 还是字符串 → 解不出来
        return []
    if isinstance(payload, list):
        return [v for v in payload if isinstance(v, dict)]
    if isinstance(payload, dict):
        return _from_dict(payload, key_hints)
    return []
