"""结构化输出包装类（rag-agent 版）：带引用的回答。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc_id: str = Field(description="引用来源的文档 ID，必须是资料中给出的 doc_id")
    quote: str = Field(description="支撑该论断的原文，必须逐字摘抄")


class AnswerSet(BaseModel):
    answer: str = Field(description="基于资料的回答；资料中没有就明确说不知道")
    citations: list[Citation] = Field(description="论断对应的引用列表，可为空")


def _make_strict(node):
    if isinstance(node, dict):
        if "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _make_strict(value)
    elif isinstance(node, list):
        for value in node:
            _make_strict(value)
    return node


def strict_json_schema(model_cls: type[BaseModel]) -> dict:
    schema = _make_strict(model_cls.model_json_schema())
    return {
        "type": "json_schema",
        "json_schema": {"name": model_cls.__name__, "strict": True, "schema": schema},
    }
