"""一键评测脚本。

用法：
    python -m app.eval.run_eval --mock          # 离线（FakeGateway），CI 可跑
    python -m app.eval.run_eval                 # 真实调用（需配置 API Key）
    python -m app.eval.run_eval --limit 3       # 只跑前 3 条

产出（写入 --out 目录，默认 eval_results/）：
    results.json  —— 逐用例明细，供趋势对比
    report.md     —— 可提交到 PR 的报告

退出码：任一用例低于阈值 -> 1，可直接当 CI 质量门禁。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.eval.test_cases import SAMPLE_CASES, EvalCase
from app.graph.builder import build_graph
from app.schema.wrappers import FindingSet


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
    header = f"{'用例':<18}{'结果':<6}{'关键词命中':<10}{'发现数':<8}{'schema':<8}{'耗时(s)':<8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id']:<18}{mark:<6}{r['keyword_hit']:<10}{r['findings_count']:<8}"
            f"{('ok' if r['schema_valid'] else 'BAD'):<8}{r['latency_s']:<8}"
        )
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    print("-" * len(header))
    print(f"合计: {passed}/{total} 通过，平均耗时 {sum(r['latency_s'] for r in rows) / total:.3f}s\n")


def _write_report(rows: list[dict], out_dir: Path, mock: bool) -> None:
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
        "| 用例 | 结果 | 关键词命中 | 发现数 | schema | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case_id']} | {'✅' if r['passed'] else '❌'} | {r['keyword_hit']} "
            f"| {r['findings_count']} | {'ok' if r['schema_valid'] else 'BAD'} | {r['latency_s']} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ai-app-template 模板项目自动化评测")
    parser.add_argument("--mock", action="store_true", help="离线模式：使用 FakeGateway，不调用真实模型")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条用例")
    parser.add_argument("--threshold", type=float, default=None, help="关键词命中率阈值（默认取配置）")
    parser.add_argument("--out", type=str, default="eval_results", help="结果输出目录")
    args = parser.parse_args(argv)

    settings = get_settings()
    threshold = args.threshold if args.threshold is not None else settings.eval_min_keyword_hit

    if args.mock:
        from app.llm.fakes import FakeGateway

        gateway = FakeGateway()
    else:
        from app.llm.gateway import get_gateway

        gateway = get_gateway()

    cases = SAMPLE_CASES[: args.limit] if args.limit else SAMPLE_CASES
    graph = build_graph(gateway, settings)
    rows = [run_case(graph, case, threshold, mock=args.mock) for case in cases]

    _print_table(rows)
    _write_report(rows, Path(args.out), args.mock)
    if args.mock:
        print("（mock 模式：仅验证管道连通性；关键词/数量门槛在真实模式生效）")

    failed = [r["case_id"] for r in rows if not r["passed"]]
    if failed:
        print(f"未达标用例（阈值 {threshold}）: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"全部通过（阈值 {threshold}）。报告见 {args.out}/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
