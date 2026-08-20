"""一键评测脚本：套件化跑分 + 基线对比 + 回退结论。

用法：
    python -m app.eval.run_eval --mock             # 离线冒烟（CI），只验管道，不做回退判定
    python -m app.eval.run_eval --suite all        # 真实模式：手写种子 + 全部生成集
    python -m app.eval.run_eval --suite boundary   # 只跑某一套件（happy/boundary/anomaly/adversarial）
    python -m app.eval.run_eval --suite seed       # 只跑手写种子用例
    python -m app.eval.run_eval --set-baseline     # 签字认可当前质量线（写入 app/eval/baseline.json）

产出（--out 目录，默认 eval_results/）：results.json + report.md（含回退结论）。
退出码：建议回退 -> 1（可直接当 CI 质量门禁）；mock 模式有用例未过 -> 1。
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
    from app.eval.test_cases import SAMPLE_CASES, EvalCase
    from app.graph.builder import build_graph
    from app.schema.wrappers import FindingSet
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
                    document=row.get("document", ""),
                    expect_keywords=row.get("expect_keywords", []),
                    expect_min_findings=row.get("expect_min_findings", 0),
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
    result = graph.invoke({"document": case.document, "trace_id": f"eval-{case.id}"})
    latency_s = time.perf_counter() - started

    findings = result.get("reviewed_findings") or []
    summary = result.get("summary", "")
    text = json.dumps(findings, ensure_ascii=False) + summary

    keywords = case.expect_keywords
    hit_rate = (sum(1 for kw in keywords if kw in text) / len(keywords)) if keywords else 1.0
    try:
        FindingSet.model_validate({"findings": findings})
        schema_valid = True
    except Exception:
        schema_valid = False

    if mock:
        # mock 模式只验证「管道连通性」：流程完整走完、输出能解析成合法 schema。
        # 关键词命中率与数量门槛只在真实模式下生效 —— 替身不假装有质量。
        passed = schema_valid
    else:
        passed = (
            hit_rate >= threshold
            and schema_valid
            and len(findings) >= case.expect_min_findings
        )
    return {
        "case_id": case.id,
        "tier": case.tier,
        "passed": passed,
        "keyword_hit": round(hit_rate, 3),
        "keywords": keywords,
        "findings_count": len(findings),
        "expect_min_findings": case.expect_min_findings,
        "schema_valid": schema_valid,
        "latency_s": round(latency_s, 3),
        "errors": result.get("errors") or [],
        "notes": case.notes,
    }


def _print_table(rows: list[dict]) -> None:
    header = f"{'用例':<24}{'层级':<13}{'结果':<6}{'关键词命中':<10}{'发现数':<8}{'耗时(s)':<8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id']:<24}{r['tier']:<13}{mark:<6}{r['keyword_hit']:<10}"
            f"{r['findings_count']:<8}{r['latency_s']:<8}"
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
        "# 评测报告",
        "",
        f"- 模式：{'离线 mock' if mock else '真实调用'}",
        f"- 通过：{sum(1 for r in rows if r['passed'])}/{len(rows)}",
        "",
        "| 用例 | 层级 | 结果 | 关键词命中 | 发现数 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case_id']} | {r['tier']} | {'✅' if r['passed'] else '❌'} | {r['keyword_hit']} "
            f"| {r['findings_count']} | {r['latency_s']} |"
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
    parser = argparse.ArgumentParser(description="ai-app-template 模板项目自动化评测")
    parser.add_argument("--mock", action="store_true", help="离线模式：使用 FakeGateway，不调用真实模型")
    parser.add_argument("--suite", choices=SUITES, default="all", help="跑哪个套件（默认 all）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条用例")
    parser.add_argument("--threshold", type=float, default=None, help="关键词命中率阈值（默认取配置）")
    parser.add_argument("--out", type=str, default="eval_results", help="结果输出目录")
    parser.add_argument(
        "--set-baseline", action="store_true",
        help="把本次（真实模式）跑分固化为基线；此后的每次跑分自动对比并给出回退结论",
    )
    args = parser.parse_args(argv)

    if args.mock and args.set_baseline:
        print("--set-baseline 仅用于真实模式（mock 没有质量语义）", file=sys.stderr)
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
    rows = [run_case(graph, case, threshold, mock=args.mock) for case in cases]

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
