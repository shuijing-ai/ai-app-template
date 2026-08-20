"""一键评测脚本（voice-flow 版）：套件化跑分 + 基线对比 + 回退结论。

用法：
    python -m app.eval.run_eval --mock             # 离线冒烟（CI），只验管道
    python -m app.eval.run_eval --suite all        # 真实模式：种子 + 全部生成集
    python -m app.eval.run_eval --set-baseline     # 签字认可当前质量线
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from app.config import get_settings
    from app.eval.compare import (
        Verdict,
        compare,
        load_baseline,
        save_baseline,
        suite_scores,
        total_score,
    )
    from app.eval.suggest import changed_files, median_rows, print_suggestions
    from app.eval.test_cases import SAMPLE_CASES, EvalCase
    from app.graph.builder import build_graph
    from app.schema.wrappers import TodoSet
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"\n[依赖缺失] 未安装 {exc.name}。请先在项目根目录执行：\n"
        '    pip install -e ".[dev]"\n'
        "（国内网络不畅可加：-i https://pypi.tuna.tsinghua.edu.cn/simple）\n"
    ) from None

GENERATED_DIR = Path("app/eval/generated")
BASELINE_PATH = Path("app/eval/baseline.json")
SUITES = ["all", "seed", "happy", "boundary", "anomaly", "adversarial"]


def load_suite(suite: str, generated_dir: Path = GENERATED_DIR) -> list[EvalCase]:
    """seed=手写种子；层级名=读固化生成集；all=全部。同 id 去重。"""
    cases: list[EvalCase] = []
    if suite in ("all", "seed"):
        cases.extend(SAMPLE_CASES)

    if suite == "all":
        paths = sorted(generated_dir.glob("*.json"))
    elif suite != "seed":
        path = generated_dir / f"{suite}.json"
        if not path.is_file():
            raise SystemExit(
                f"套件 {suite!r} 不存在：先运行 python -m app.eval.gen_cases --tier {suite} 生成并固化"
            )
        paths = [path]
    else:
        paths = []

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("cases", []):
            cases.append(
                EvalCase(
                    id=row.get("id", f"{path.stem}-{len(cases):03d}"),
                    transcript=row.get("transcript", ""),
                    expect_keywords=row.get("expect_keywords", []),
                    expect_min_todos=row.get("expect_min_todos", 0),
                    tier=row.get("tier", path.stem),
                    notes=row.get("notes", ""),
                )
            )

    seen: set[str] = set()
    deduped: list[EvalCase] = []
    for case in cases:
        if case.id not in seen:
            seen.add(case.id)
            deduped.append(case)
    return deduped


def run_case(graph, case: EvalCase, threshold: float, mock: bool = False) -> dict:
    started = time.perf_counter()
    result = graph.invoke({"transcript": case.transcript, "trace_id": f"eval-{case.id}"})
    latency_s = time.perf_counter() - started

    summary = result.get("summary", "")
    topics = result.get("topics") or []
    todos = result.get("finalized_todos") or []
    text = summary + "".join(topics) + json.dumps(todos, ensure_ascii=False)

    keywords = case.expect_keywords
    hit_rate = (sum(1 for kw in keywords if kw in text) / len(keywords)) if keywords else 1.0
    try:
        TodoSet.model_validate({"todos": todos})
        schema_valid = True
    except Exception:
        schema_valid = False

    if mock:
        # mock 模式只验证管道连通性：流程完整走完、输出能解析成合法 schema
        passed = schema_valid
    else:
        passed = hit_rate >= threshold and schema_valid and len(todos) >= case.expect_min_todos
    return {
        "case_id": case.id,
        "tier": case.tier,
        "passed": passed,
        "keyword_hit": round(hit_rate, 3),
        "keywords": keywords,
        "todos_count": len(todos),
        "expect_min_todos": case.expect_min_todos,
        "schema_valid": schema_valid,
        "noise_removed": result.get("noise_removed", 0),
        "latency_s": round(latency_s, 3),
        "errors": result.get("errors") or [],
        "notes": case.notes,
    }


def _print_table(rows: list[dict]) -> None:
    header = f"{'用例':<20}{'层级':<13}{'结果':<6}{'关键词命中':<10}{'待办数':<8}{'噪音清理':<8}{'耗时(s)':<8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id']:<20}{r['tier']:<13}{mark:<6}{r['keyword_hit']:<10}{r['todos_count']:<8}"
            f"{r['noise_removed']:<8}{r['latency_s']:<8}"
        )
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    print("-" * len(header))
    print(f"合计: {passed}/{total} 通过，平均耗时 {sum(r['latency_s'] for r in rows) / total:.3f}s")


def _write_report(rows: list[dict], out_dir: Path, mock: bool, verdict: Verdict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps({"mode": "mock" if mock else "live", "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 评测报告（voice-flow）",
        "",
        f"- 模式：{'离线 mock' if mock else '真实调用'}",
        f"- 通过：{sum(1 for r in rows if r['passed'])}/{len(rows)}",
        "",
        "| 用例 | 层级 | 结果 | 关键词命中 | 待办数 | 噪音清理 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case_id']} | {r['tier']} | {'✅' if r['passed'] else '❌'} | {r['keyword_hit']} "
            f"| {r['todos_count']} | {r['noise_removed']} | {r['latency_s']} |"
        )
    if verdict:
        lines += [
            "",
            f"## 质量门禁结论：{verdict.action}",
            "",
            verdict.summary,
            "",
            *(f"- {reason}" for reason in verdict.reasons),
        ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_verdict(scores: dict, total: float, baseline: dict | None, verdict: Verdict) -> None:
    print("\n===== 质量门禁（live） =====")
    for tier, s in scores.items():
        base_s = (baseline or {}).get("scores", {}).get(tier)
        delta = f" Δ{(s['score'] - base_s['score']) * 100:+.1f}pp" if base_s else ""
        print(
            f"  {tier:<14} score={s['score']:.3f} pass={s['pass_rate']:.0%} "
            f"hit={s['keyword_hit_avg']:.2f}{delta}"
        )
    print(f"  {'total':<14} score={total:.3f}")
    print(f"\n结论 [{verdict.action}] {verdict.summary}")
    for reason in verdict.reasons:
        print(f"  - {reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="voice-flow 模板自动化评测")
    parser.add_argument("--mock", action="store_true", help="离线模式：使用 FakeGateway")
    parser.add_argument("--suite", choices=SUITES, default="all", help="跑哪个套件（默认 all）")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--out", type=str, default="eval_results")
    parser.add_argument("--set-baseline", action="store_true", help="把本次跑分固化为基线（仅真实模式）")
    parser.add_argument("--runs", type=int, default=1, help="连跑 N 次取多数决/中位数后判定（仅真实模式）")
    parser.add_argument("--suggest", action="store_true", help="不跑分：读 git 变更，打印该跑哪个套件的建议")
    args = parser.parse_args(argv)

    if args.suggest:
        print_suggestions(changed_files())
        return 0
    if args.mock and args.set_baseline:
        print("--set-baseline 仅用于真实模式（mock 没有质量语义）", file=sys.stderr)
        return 2
    if args.mock and args.runs > 1:
        print("--runs 仅用于真实模式（mock 结果是确定性的，多次采样无意义）", file=sys.stderr)
        return 2

    settings = get_settings()
    threshold = args.threshold if args.threshold is not None else settings.eval_min_keyword_hit

    if args.mock:
        from app.llm.fakes import FakeGateway

        gateway = FakeGateway()
    else:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()

    cases = load_suite(args.suite)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print(f"套件 {args.suite!r} 为空：先运行 python -m app.eval.gen_cases 生成用例", file=sys.stderr)
        return 2

    graph = build_graph(gateway, settings)
    runs = [
        [run_case(graph, case, threshold, mock=args.mock) for case in cases]
        for _ in range(max(1, args.runs))
    ]
    rows = median_rows(runs)
    if args.runs > 1:
        print(f"（--runs {args.runs}：逐用例多数决 + 命中率中位数后进入判定）")

    _print_table(rows)

    if args.mock:
        _write_report(rows, Path(args.out), mock=True)
        print("（mock 模式：仅验证管道连通性；关键词/数量门槛与回退判定在真实模式生效）")
        failed = [r["case_id"] for r in rows if not r["passed"]]
        return 1 if failed else 0

    scores = suite_scores(rows)
    total = total_score(scores)

    if args.set_baseline:
        save_baseline(BASELINE_PATH, scores, total)
        _write_report(rows, Path(args.out), mock=False)
        print(f"\n基线已固化到 {BASELINE_PATH}（total={total:.3f}）。之后每次跑分将自动对比并给出回退结论。")
        return 0

    baseline = load_baseline(BASELINE_PATH)
    verdict, _detail = compare(rows, baseline)
    _write_report(rows, Path(args.out), mock=False, verdict=verdict)
    _print_verdict(scores, total, baseline, verdict)
    return verdict.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
