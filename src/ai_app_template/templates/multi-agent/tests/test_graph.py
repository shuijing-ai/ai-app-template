"""图结构与工作流测试（multi-agent 版）。"""

from __future__ import annotations

from app.graph.builder import build_graph, route_supervisor
from app.llm.fakes import DRAFT_TEXT, FakeGateway, FailingGateway

TASK = "为 ai-app-template 写一段 100 字以内的产品介绍。"


def test_happy_path_research_write_review_finish():
    graph = build_graph(FakeGateway(), max_rounds=4)
    result = graph.invoke({"task": TASK, "trace_id": "t1"})

    assert result["final"] == DRAFT_TEXT
    assert result["round"] == 4  # research -> writer -> critic -> pass 收尾
    assert len(result["research_notes"]) == 2
    assert len(result["drafts"]) == 1
    assert result["verdict"] == "pass"
    assert result.get("errors") is None or result["errors"] == []
    # 全过程留痕：researcher/writer/critic 各自追加了消息
    roles = [m["content"].split("]")[0] + "]" for m in result.get("messages") or []]
    assert "[researcher]" in roles and "[writer]" in roles and "[critic]" in roles


def test_round_budget_forces_finish_on_endless_revision():
    scripted = {
        "supervisor": [
            '{"next": "writer", "reason": "调研已齐"}',
            '{"next": "critic", "reason": "评审初稿"}',
            '{"next": "writer", "reason": "按意见重写"}',
        ],
        "researcher": FakeGateway().scripted["researcher"],
        "writer": ["第一版草稿。", "第二版草稿。"],
        "critic": ['{"verdict": "revise", "issues": [{"issue": "还不够好"}]}'],
    }
    graph = build_graph(FakeGateway(scripted), max_rounds=4)
    result = graph.invoke({"task": TASK, "trace_id": "t2"})

    assert result["round"] == 5  # 预算 4 轮耗尽后第 5 轮强制收尾
    assert len(result["drafts"]) == 2
    assert "轮次预算" in result["final"]
    assert result["final"].startswith("第二版草稿。")


def test_llm_outage_still_terminates_with_message():
    graph = build_graph(FailingGateway(), max_rounds=4)
    result = graph.invoke({"task": TASK, "trace_id": "t3"})

    assert result["final"]  # 永远有产出说明
    assert "任务未能产出结果" in result["final"]
    assert result["errors"]
    assert result["round"] == 2  # 调研失败 -> supervisor 决策失败 -> 收尾


def test_route_supervisor_rules():
    assert route_supervisor({"next_worker": "writer"}) == "writer"
    assert route_supervisor({"next_worker": "__end__"}) == "__end__"
    assert route_supervisor({}) == "__end__"
    assert route_supervisor({"next_worker": "hacker"}) == "__end__"
