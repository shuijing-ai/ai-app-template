"""图结构与工作流测试（rag-agent 版）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.graph.builder import build_graph, route_after_verify
from app.llm.fakes import FakeGateway, FailingGateway
from app.retrieval.store import load_kb

KB = Path("data/sample_kb.md")
QUERY = "退货政策是什么？运费谁承担？"


def make_store():
    return load_kb(KB)


def test_happy_path_with_valid_citation():
    graph = build_graph(FakeGateway(), store=make_store())
    result = graph.invoke({"query": QUERY, "trace_id": "t1"})

    assert result["citation_valid"] is True
    assert "7 天" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["doc_id"] == "退货政策"
    assert result["retrieved"][0]["doc_id"] == "退货政策"  # TF-IDF 检索命中正确文档
    assert result.get("errors") is None or result["errors"] == []


def test_forged_citation_is_stripped_and_retried():
    forged = json.dumps(
        {
            "answer": "随便编的答案。",
            "citations": [{"doc_id": "根本不存在的文档", "quote": "伪造的原文"}],
        },
        ensure_ascii=False,
    )
    graph = build_graph(FakeGateway(scripted={"generate": forged}), store=make_store())
    result = graph.invoke({"query": QUERY, "trace_id": "t2"})

    assert result["citation_valid"] is False
    assert result["citations"] == []  # 伪造引用被确定性剔除
    assert result["attempt"] == 2  # 校验失败触发了一次重试
    assert result["verify_feedback"]  # 失败原因回传给了生成节点


def test_kb_miss_returns_honest_answer():
    # 注意选词：与示例知识库任何字都不重叠（字级 TF-IDF 的匹配粒度就是这么粗）
    graph = build_graph(FakeGateway(), store=make_store())
    result = graph.invoke({"query": "你们董事长今年多少岁？", "trace_id": "t3"})
    assert "没有找到" in result["answer"]
    assert result["citation_valid"] is True  # 无引用 + 无伪造 = 合法


def test_llm_outage_degrades_gracefully():
    graph = build_graph(FailingGateway(), store=make_store())
    result = graph.invoke({"query": QUERY, "trace_id": "t4"})
    assert "不可用" in result["answer"]
    assert result["errors"]


def test_route_after_verify_rules():
    assert route_after_verify({"citation_valid": True}) == "__end__"
    assert route_after_verify({"citation_valid": False, "attempt": 1}) == "generate"
    assert route_after_verify({"citation_valid": False, "attempt": 2}) == "__end__"
