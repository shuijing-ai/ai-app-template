"""结构化输出包装类（voice-flow 版）：会议摘要与待办。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SummarySet(BaseModel):
    summary: str = Field(description="200 字以内的会议摘要")
    topics: list[str] = Field(description="3-5 个关键议题，每个不超过 10 字")


class TodoItem(BaseModel):
    action: str = Field(description="待办事项，动词开头，一句话")
    owner: str = Field(description="负责人；未指明则填空字符串")
    due: str = Field(description="截止时间；未提及则填空字符串")


class TodoSet(BaseModel):
    todos: list[TodoItem] = Field(description="全部待办，可为空列表")


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
