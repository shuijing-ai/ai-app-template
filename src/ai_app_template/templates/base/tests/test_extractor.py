"""safe_extract_items：各种奇葩输出的统一解包。

注意：这里故意不用业务包装类（FindingSet 等），只用本地定义的模型 ——
该测试属于通用层，任何模板变体（schema 不同）都必须能原样跑通。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.utils.extractor import safe_extract_items

ITEMS = [{"quote": "q", "issue": "i", "category": "logic", "severity": 3}]


class _DemoSet(BaseModel):
    findings: list[dict]


def test_plain_dict_with_hint_key():
    assert safe_extract_items({"items": ITEMS}) == ITEMS


def test_pydantic_model_input():
    model = _DemoSet.model_validate({"findings": ITEMS})
    out = safe_extract_items(model, key_hints=("findings",))
    assert out == ITEMS


def test_markdown_fenced_json():
    payload = '```json\n{"findings": %s}\n```' % str(ITEMS).replace("'", '"')
    assert safe_extract_items(payload) == ITEMS


def test_bare_json_string_with_surrounding_noise():
    payload = '好的，提取结果如下：{"findings": []} 以上。'
    assert safe_extract_items(payload) == []


def test_bare_list_string():
    import json

    assert safe_extract_items(json.dumps(ITEMS)) == ITEMS


def test_invalid_input_never_raises():
    assert safe_extract_items("完全不是 JSON") == []
    assert safe_extract_items(None) == []
    assert safe_extract_items(12345) == []
    assert safe_extract_items({"unexpected": "shape"}) == []
