"""图结构与工作流测试：快乐路径 + LLM 全面宕机的兜底路径。"""

from __future__ import annotations

from app.graph.builder import build_graph, route_after_extract
from app.graph.nodes.parse_node import split_sections
from app.llm.fakes import FakeGateway, FailingGateway

DOC = (
    "## 交付条款\n本项目将在三个月内完成交付。\n\n"
    "## 违约条款\n违约金为合同总额的百分之五十。\n\n"
    "## 运维条款\n乙方负责全部运维工作。"
)


def test_happy_path_with_fake_gateway():
    graph = build_graph(FakeGateway())
    result = graph.invoke({"document": DOC, "trace_id": "t1"})

    assert result["extract_ok"] is True
    assert len(result["parsed_sections"]) == 3  # 确定性解析按标题切分
    # 词法 Fake 按风险词表命中：DOC 含「交付」「违约」两个风险词
    assert len(result["findings"]) == 2
    assert all("潜在风险" in f["issue"] for f in result["findings"])
    assert len(result["reviewed_findings"]) == 2  # 复核保留 index 0/1
    assert "审阅完成" in result["summary"]
    assert result.get("errors") is None or result["errors"] == []


def test_llm_total_outage_degrades_gracefully():
    """网关彻底不可用时：重试一次、记录错误、空发现继续、summary 仍有值。"""
    graph = build_graph(FailingGateway())
    result = graph.invoke({"document": DOC, "trace_id": "t2"})

    assert result["extract_attempts"] == 2  # 条件边按设计重试了一次
    assert result["extract_ok"] is True  # 第二次失败后按约定放弃提取
    assert result["reviewed_findings"] == []
    assert result["errors"]  # 错误被收集而不是抛给调用方
    assert result["summary"]  # summary 永远非空（确定性兜底）


def test_route_after_extract_rules():
    assert route_after_extract({"extract_ok": True}) == "review"
    assert route_after_extract({"extract_ok": False, "extract_attempts": 1}) == "extract"
    assert route_after_extract({"extract_ok": False, "extract_attempts": 2}) == "review"


def test_split_sections_with_and_without_headings():
    with_headings = split_sections("## A\ncontent-a\n\n## B\ncontent-b")
    assert [s["heading"] for s in with_headings] == ["A", "B"]

    no_headings = split_sections("para one.\n\npara two.\n\npara three.", target_chars=10)
    assert len(no_headings) >= 2  # 无标题时按段落打包
    assert all(s["text"] for s in no_headings)

    assert split_sections("   \n  ") == []
