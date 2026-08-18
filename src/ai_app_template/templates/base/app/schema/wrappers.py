"""结构化输出包装类与 strict schema 构建。

本项目的核心约定：**每个 LLM 结构化输出都定义成 ``XxxSet`` 包装类**，
集合字段名固定、条目是强类型 pydantic 模型。收益：
1. ``response_format`` 直接由 pydantic 生成（strict 模式，模型端保证合法 JSON）；
2. ``safe_extract_items`` 可以用统一方式解包任何输出（见 utils/extractor.py）；
3. 评测脚本可以只凭「能否解析成 XxxSet」给 schema_validity 打分。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- 审阅域的结构化输出 ----


class FindingItem(BaseModel):
    quote: str = Field(description="原文引用，必须逐字摘抄")
    issue: str = Field(description="问题说明：为什么这条内容有风险")
    category: Literal["logic", "evidence", "style", "compliance"] = Field(description="问题类别")
    severity: int = Field(ge=1, le=5, description="严重程度 1-5")


class FindingSet(BaseModel):
    findings: list[FindingItem] = Field(description="提取到的问题列表，可为空")


class ReviewDecision(BaseModel):
    index: int = Field(ge=0, description="对应候选问题的下标")
    keep: bool = Field(description="是否保留该问题")
    reason: str = Field(description="保留/剔除理由")


class ReviewSet(BaseModel):
    decisions: list[ReviewDecision]


# ---- OpenAI structured outputs 适配 ----


def _make_strict(node):
    """递归处理 schema：对象节点补 additionalProperties=false 并要求全字段。"""
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
    """pydantic 模型 -> OpenAI ``response_format``（strict json_schema）。"""
    schema = _make_strict(model_cls.model_json_schema())
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model_cls.__name__,
            "strict": True,
            "schema": schema,
        },
    }
