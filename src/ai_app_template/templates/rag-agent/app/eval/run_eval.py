"""一键评测脚本（rag-agent 版）。

用法与产出同 base 版；评分维度换成 RAG 语义：
关键词命中率 / 引用数量 / 引用合法性 / 延迟。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from app.config import get_settings
    from app.eval.test_cases import SAMPLE_CASES, EvalCase
    from app.graph.builder import build_graph
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"\n[依赖缺失] 未安装 {exc.name}。请先在项目根目录执行：\n"
        '    pip install -e ".[dev]"\n'
        "（国内网络不畅可加：-i https://pypi.tuna.tsinghua.edu.cn/simple）\n"
    ) from None


def run_case(graph, case: EvalCase, threshold: float, mock: bool = False) -> dict:
    started = time.perf_counter()
    result = graph.invoke({"query": case.query, "trace_id": f"eval-{case.id}"})
    latency_s = time.perf_counter() - started

    answer = result.get("answer", "")
    citations = result.get("citations") or []
    keywords = case.expect_keywords
    hit_rate = (sum(1 for kw in keywords if kw in answer) / len(keywords)) if keywords else 1.0

    if mock:
        # mock 模式只验证管道连通性（流程走完、有回答）；引用与关键词门槛只在真实模式生效
        passed = bool(answer)
    else:
        passed = (
            hit_rate >= threshold
            and bool(result.get("citation_valid"))
            and len(citations) >= case.expect_min_citations
        )
    return {
        "case_id": case.id,
        "passed": passed,
        "keyword_hit": round(hit_rate, 3),
        "keywords": keywords,
        "citations_count": len(citations),
        "expect_min_citations": case.expect_min_citations,
        "citation_valid": bool(result.get("citation_valid")),
        "latency_s": round(latency_s, 3),
        "errors": result.get("errors") or [],
        "notes": case.notes,
    }


def _print_table(rows: list[dict]) -> None:
    header = f"{'用例':<18}{'结果':<6}{'关键词命中':<10}{'引用数':<8}{'引用合法':<8}{'耗时(s)':<8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id']:<18}{mark:<6}{r['keyword_hit']:<10}{r['citations_count']:<8}"
            f"{('ok' if r['citation_valid'] else 'BAD'):<8}{r['latency_s']:<8}"
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
        "# 评测报告（RAG）",
        "",
        f"- 模式：{'离线 mock' if mock else '真实调用'}",
        f"- 通过：{sum(1 for r in rows if r['passed'])}/{len(rows)}",
        "",
        "| 用例 | 结果 | 关键词命中 | 引用数 | 引用合法 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case_id']} | {'✅' if r['passed'] else '❌'} | {r['keyword_hit']} "
            f"| {r['citations_count']} | {'ok' if r['citation_valid'] else 'BAD'} | {r['latency_s']} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG 模板自动化评测")
    parser.add_argument("--mock", action="store_true", help="离线模式：使用 FakeGateway")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--out", type=str, default="eval_results")
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
        print("（mock 模式：仅验证管道连通性；引用/关键词门槛在真实模式生效）")

    failed = [r["case_id"] for r in rows if not r["passed"]]
    if failed:
        print(f"未达标用例（阈值 {threshold}）: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"全部通过（阈值 {threshold}）。报告见 {args.out}/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
