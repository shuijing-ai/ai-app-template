"""基线对比与回退判定（纯确定性代码，无 LLM）。

判定规则（live 模式跑分后由 run_eval 自动执行；mock 模式不判定——替身不假装有质量）：
- 总分较基线跌幅 > 5pp                 -> rollback（建议回退）
- 非焦点套件跌幅 > 10pp                -> rollback（局部雪崩）
- boundary/adversarial 跌幅 > 15pp     -> warn（人工确认是否接受）
- 总分升幅 > 5pp                        -> improve（提示 --set-baseline 固化新基线）
- 其余                                  -> pass

焦点套件（boundary/adversarial）单独适用更宽的 15pp 警告线而非 10pp 回退线：
这两类天然最不稳定（边界输入、对抗输入），轻微退化先警告人工确认，不直接判死刑。

阈值即文档（docs/designs/auto-eval-design.md §7.3），改这里要同步改文档。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

TOLERANCE_PP = 5.0
SUITE_DROP_PP = 10.0
FOCUS_DROP_PP = 15.0
FOCUS_TIERS = ("boundary", "adversarial")

PASS_WEIGHT = 0.6  # 套件分 = 通过率 * 0.6 + 平均关键词命中率 * 0.4
HIT_WEIGHT = 0.4


def suite_scores(rows: list[dict]) -> dict[str, dict]:
    """按 tier 聚合单次跑分结果。"""
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row.get("tier", "seed"), []).append(row)
    scores: dict[str, dict] = {}
    for tier, items in sorted(buckets.items()):
        pass_rate = sum(1 for r in items if r["passed"]) / len(items)
        hit_avg = sum(r["keyword_hit"] for r in items) / len(items)
        scores[tier] = {
            "cases": len(items),
            "pass_rate": round(pass_rate, 4),
            "keyword_hit_avg": round(hit_avg, 4),
            "score": round(PASS_WEIGHT * pass_rate + HIT_WEIGHT * hit_avg, 4),
        }
    return scores


def total_score(scores: dict[str, dict]) -> float:
    """总分 = 各套件按用例数加权平均。"""
    n = sum(s["cases"] for s in scores.values())
    if not n:
        return 0.0
    return round(sum(s["score"] * s["cases"] for s in scores.values()) / n, 4)


@dataclass
class Verdict:
    action: str  # pass | rollback | warn | improve | no-baseline
    summary: str
    reasons: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.action == "rollback" else 0


def compare(current_rows: list[dict], baseline: dict | None) -> tuple[Verdict, dict]:
    """当前跑分 vs 基线 -> 回退结论。返回 (verdict, 明细)。"""
    scores = suite_scores(current_rows)
    total = total_score(scores)
    detail = {"scores": scores, "total": total}

    if not baseline:
        return Verdict(
            "no-baseline", "尚无基线：用 --set-baseline 固化本次结果作为质量线"
        ), detail

    base_total = baseline.get("total", 0.0)
    delta_pp = (total - base_total) * 100
    reasons: list[str] = []

    rollback = delta_pp < -TOLERANCE_PP
    if rollback:
        reasons.append(
            f"总分 {total:.3f} 较基线 {base_total:.3f} 跌 {abs(delta_pp):.1f}pp"
            f"（容差 {TOLERANCE_PP}pp）"
        )

    warn_reasons: list[str] = []
    for tier, s in scores.items():
        base_s = (baseline.get("scores") or {}).get(tier)
        if not base_s:
            continue
        drop_pp = (s["score"] - base_s["score"]) * 100
        if drop_pp >= 0:
            continue
        if tier in FOCUS_TIERS:
            if drop_pp < -FOCUS_DROP_PP:
                warn_reasons.append(
                    f"{tier} 套件跌 {abs(drop_pp):.1f}pp（焦点套件警告线 {FOCUS_DROP_PP}pp）"
                )
        elif drop_pp < -SUITE_DROP_PP:
            rollback = True
            reasons.append(f"{tier} 套件跌 {abs(drop_pp):.1f}pp（阈值 {SUITE_DROP_PP}pp）")

    if rollback:
        return Verdict("rollback", "建议回退本次改动", reasons), detail
    if warn_reasons:
        return Verdict("warn", "通过，但边界/对抗套件明显劣化，请人工确认", warn_reasons), detail

    if delta_pp > TOLERANCE_PP:
        return Verdict(
            "improve", f"总分较基线升 {delta_pp:.1f}pp，可用 --set-baseline 固化新基线"
        ), detail

    return Verdict("pass", f"通过（Δ {delta_pp:+.1f}pp，容差内）"), detail


def load_baseline(path: Path) -> dict | None:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_baseline(path: Path, scores: dict[str, dict], total: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "scores": scores,
                "total": total,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
