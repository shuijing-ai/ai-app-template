"""图结构与工作流测试（voice-flow 版）。"""

from __future__ import annotations

from app.graph.builder import build_graph
from app.graph.nodes.finalize_node import finalize_todos
from app.graph.nodes.ingest_node import clean_transcript
from app.llm.fakes import FakeGateway, FailingGateway

TRANSCRIPT = (
    "[00:00] 张三：本次迭代还剩登录模块，预计周四提测。\n"
    "[00:21] 李四：测试环境今天恢复，嗯，大家下午可以自测。\n"
    "[00:45] 王五：文档我来更新，周五前发出来。"
)


def test_clean_transcript_removes_noise():
    cleaned, noise = clean_transcript(TRANSCRIPT)
    assert "[00:" not in cleaned and "张三：" not in cleaned
    assert "嗯，" not in cleaned
    assert "提测" in cleaned  # 正文保留
    assert noise >= 5  # 3 个时间戳 + 3 个说话人标签 + 1 个填充词


def test_finalize_todos_dedupes_and_ranks():
    todos = [
        {"action": "补充验收标准", "owner": "张三", "due": "周五"},
        {"action": "补充验收标准", "owner": "张三", "due": "周五"},  # 重复
        {"action": "同步排期风险", "owner": "李四", "due": ""},
        {"action": "更新文档", "owner": "", "due": ""},
    ]
    finalized = finalize_todos(todos)
    assert len(finalized) == 3  # 去重
    assert finalized[0]["action"] == "补充验收标准"  # 有 due 优先
    assert finalized[-1]["action"] == "更新文档"  # 无 due 无 owner 垫底


def test_happy_path_with_fake_gateway():
    graph = build_graph(FakeGateway())
    result = graph.invoke({"transcript": TRANSCRIPT, "trace_id": "t1"})

    assert "[00:" not in result["cleaned"]
    assert result["noise_removed"] > 0
    assert "发布计划" in result["summary"]
    assert len(result["topics"]) == 3
    # 预置 3 条待办含 1 条重复 -> finalize 去重为 2
    assert len(result["todos"]) == 3
    assert len(result["finalized_todos"]) == 2
    assert result["finalized_todos"][0]["due"] == "周五"
    assert result.get("errors") is None or result["errors"] == []


def test_llm_outage_degrades_gracefully():
    graph = build_graph(FailingGateway())
    result = graph.invoke({"transcript": TRANSCRIPT, "trace_id": "t2"})

    assert "LLM 摘要暂不可用" in result["summary"]  # 确定性摘要兜底
    assert result["finalized_todos"] == []  # 待办宁缺毋滥
    assert result["errors"]


def test_empty_transcript_after_cleaning():
    graph = build_graph(FakeGateway())
    result = graph.invoke({"transcript": "[00:01] [00:02]", "trace_id": "t3"})
    assert result["summary"] == "转写内容为空，无摘要。"
    assert result["finalized_todos"] == []
