"""结构化输出包装类（multi-agent 版）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResearchPoint(BaseModel):
    point: str = Field(description="一条调研要点")


class ResearchSet(BaseModel):
    points: list[ResearchPoint]


class NextAction(BaseModel):
    next: Literal["researcher", "writer", "critic", "FINISH"] = Field(description="下一个执行的工人")
    reason: str = Field(description="调度理由")


class CritiqueItem(BaseModel):
    issue: str = Field(description="一处需要修改的问题")


class CritiqueSet(BaseModel):
    verdict: Literal["pass", "revise"] = Field(description="终审结论")
    issues: list[CritiqueItem] = Field(description="revise 时的问题清单，pass 时为空")


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
