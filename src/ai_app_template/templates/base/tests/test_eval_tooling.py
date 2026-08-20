"""auto-eval 工具链测试：生成校验/去重、套件加载、基线对比与回退判定。全离线。"""

from __future__ import annotations

import json

import pytest

from app.eval.compare import compare, load_baseline, save_baseline, suite_scores, total_score
from app.eval.gen_cases import (
    COUNT_FIELD,
    INPUT_FIELD,
    GeneratedCase,
    generate_tier,
    validate_case,
)
from app.eval.run_eval import load_suite, main
from app.eval.test_cases import SAMPLE_CASES
from app.llm.fakes import FakeGateway


# ---------- 生成侧：确定性校验 ----------

def make_case(**overrides) -> GeneratedCase:
    params = dict(
        tier="happy",
        sub_kind="typical",
        input="乙方应在三个月内完成交付，违约金为合同总额的百分之五十。",
        expect_keywords=["交付", "违约金"],
        expect_min_count=2,
        notes="典型合同风险",
    )
    params.update(overrides)
    return GeneratedCase.model_validate(params)


def test_validate_case_accepts_well_formed():
    ok, reason = validate_case(make_case(), seen_inputs=set())
    assert ok, reason


def test_validate_case_rejects幻觉指标():
    bad = make_case(expect_keywords=["完全不在输入里的关键词"])
    ok, reason = validate_case(bad, seen_inputs=set())
    assert not ok and "未出现在输入中" in reason


def test_validate_case_rejects_sub_kind_violations():
    # empty_risk 必须期望 0 发现
    ok, reason = validate_case(
        make_case(tier="boundary", sub_kind="empty_risk", expect_keywords=[], expect_min_count=1),
        seen_inputs=set(),
    )
    assert not ok and "empty_risk" in reason

    # min_length 输入必须真的短
    ok, reason = validate_case(
        make_case(
            tier="boundary",
            sub_kind="min_length",
            expect_keywords=[],
            input="这是一段远远超过一百二十个字符上限的长输入。" * 10,
        ),
        seen_inputs=set(),
    )
    assert not ok and "超长" in reason

    # anomaly 必须无关键词断言
    ok, reason = validate_case(
        make_case(tier="anomaly", sub_kind="kb_miss", expect_keywords=["拒答"], expect_min_count=0),
        seen_inputs=set(),
    )
    assert not ok and "anomaly" in reason


def test_validate_case_rejects_duplicates():
    seen = {"".join(make_case().input.split())}
    ok, reason = validate_case(make_case(notes="重复输入"), seen_inputs=seen)
    assert not ok and "重复" in reason


# ---------- 生成侧：走 FakeGateway 的整层生成 ----------

def _case_set_json(cases: list[dict]) -> str:
    return json.dumps({"cases": cases}, ensure_ascii=False)


def test_generate_tier_validates_and_dedups():
    good = make_case().model_dump()
    good2 = make_case(
        input="保密期限为两年，违约需赔偿全部损失。", expect_keywords=["保密"], expect_min_count=1
    ).model_dump()
    hallucinated = make_case(
        input="验收标准尚未约定。",
        expect_keywords=["根本不存在的词"],
        sub_kind="typical",
    ).model_dump()
    duplicate = make_case(notes="与 good 完全相同的输入").model_dump()

    gateway = FakeGateway(scripted={"gen_cases": _case_set_json([good, good2, hallucinated, duplicate])})
    identity = {
        "identity": {"name": "测试助手", "description": "测试用身份卡"},
        "generation": {"per_taxonomy": 4},
    }
    kept, rejected = generate_tier("happy", identity, gateway)

    assert len(kept) == 2
    assert len(rejected) == 2
    assert kept[0][INPUT_FIELD] == good["input"]
    assert kept[0][COUNT_FIELD] == 2
    assert kept[0]["id"] == "happy-typical-001"
    assert kept[1]["id"] == "happy-typical-002"  # 序号只数保留下来的


# ---------- 套件加载 ----------

def test_load_suite_seed_and_generated(tmp_path):
    seed_only = load_suite("seed", generated_dir=tmp_path)
    assert len(seed_only) == len(SAMPLE_CASES)
    assert all(c.tier == "seed" for c in seed_only)

    (tmp_path / "boundary.json").write_text(
        json.dumps(
            {
                "tier": "boundary",
                "cases": [
                    {
                        "id": "boundary-charset-001",
                        "tier": "boundary",
                        "document": "包含 emoji 😀 与全角符号的输入",
                        "expect_keywords": [],
                        "expect_min_findings": 0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    boundary = load_suite("boundary", generated_dir=tmp_path)
    assert [c.id for c in boundary] == ["boundary-charset-001"]
    assert boundary[0].document.startswith("包含 emoji")

    everything = load_suite("all", generated_dir=tmp_path)
    assert len(everything) == len(SAMPLE_CASES) + 1


def test_load_suite_missing_tier_raises(tmp_path):
    with pytest.raises(SystemExit, match="gen_cases"):
        load_suite("adversarial", generated_dir=tmp_path)


# ---------- 基线对比与回退判定 ----------

def rows_of(tier: str, passed: list[bool], hit: float = 1.0) -> list[dict]:
    return [
        {"tier": tier, "passed": p, "keyword_hit": hit, "case_id": f"{tier}-{i}"} for i, p in enumerate(passed)
    ]


def _baseline_from(rows: list[dict]) -> dict:
    scores = suite_scores(rows)
    return {"scores": scores, "total": total_score(scores)}


def test_compare_no_baseline():
    verdict, detail = compare(rows_of("happy", [True, True]), None)
    assert verdict.action == "no-baseline"
    assert detail["total"] == 1.0


def test_compare_rollback_on_total_drop():
    baseline = _baseline_from(rows_of("happy", [True] * 10))
    current = rows_of("happy", [False] * 6 + [True] * 4)  # 通过率跌 60pp
    verdict, _ = compare(current, baseline)
    assert verdict.action == "rollback"
    assert any("总分" in r for r in verdict.reasons)


def test_compare_rollback_on_single_suite_collapse():
    # anomaly 是非焦点套件：跌 36pp 触发 10pp 回退线
    base_rows = rows_of("happy", [True] * 5) + rows_of("anomaly", [True] * 5)
    baseline = _baseline_from(base_rows)
    current = rows_of("happy", [True] * 5) + rows_of("anomaly", [False] * 3 + [True] * 2)
    verdict, _ = compare(current, baseline)
    assert verdict.action == "rollback"
    assert any("anomaly" in r for r in verdict.reasons)


def test_compare_warn_on_focus_tier_drop():
    # adversarial 是焦点套件：跌 20pp 只警告不回退；happy 权重足够大使总分跌幅 < 5pp
    base_rows = rows_of("happy", [True] * 40) + rows_of("adversarial", [True] * 10)
    baseline = _baseline_from(base_rows)
    current = rows_of("happy", [True] * 40) + rows_of("adversarial", [True] * 10, hit=0.5)
    verdict, _ = compare(current, baseline)
    assert verdict.action == "warn"
    assert any("adversarial" in r for r in verdict.reasons)


def test_compare_improve_and_pass():
    baseline = _baseline_from(rows_of("happy", [False] * 5 + [True] * 5))
    improved = compare(rows_of("happy", [True] * 10), baseline)[0]
    assert improved.action == "improve"

    stable = compare(rows_of("happy", [False] * 5 + [True] * 5), baseline)[0]
    assert stable.action == "pass"


def test_baseline_roundtrip(tmp_path):
    rows = rows_of("happy", [True, False])
    scores = suite_scores(rows)
    save_baseline(tmp_path / "baseline.json", scores, total_score(scores))
    loaded = load_baseline(tmp_path / "baseline.json")
    assert loaded["scores"]["happy"]["cases"] == 2
    assert loaded["total"] == pytest.approx(0.6 * 0.5 + 0.4 * 1.0)


# ---------- CLI 集成（mock，离线） ----------

def test_run_eval_suite_seed_mock(tmp_path):
    code = main(["--mock", "--suite", "seed", "--out", str(tmp_path)])
    assert code == 0


def test_run_eval_rejects_mock_set_baseline(tmp_path):
    code = main(["--mock", "--suite", "seed", "--set-baseline", "--out", str(tmp_path)])
    assert code == 2
