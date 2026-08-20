"""一键评测脚本（multi-agent 版）：关键词命中 + 流程完整性 + 轮次预算。"""

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


def run_case(graph, case: EvalCase, threshold: float, max_rounds: int, mock: bool = False) -> dict:
    started = time.perf_counter()
    result = graph.invoke({"task": case.task, "max_rounds": max_rounds, "trace_id": f"eval-{case.id}"})
    latency_s = time.perf_counter() - started

    final = result.get("final", "")
    keywords = case.expect_keywords
    hit_rate = (sum(1 for kw in keywords if kw in final) / len(keywords)) if keywords else 1.0

    complete = bool(result.get("research_notes")) and bool(result.get("drafts"))
    if mock:
        # mock 模式只验证管道连通性（流程走完、有调研有草稿）；关键词门槛只在真实模式生效
        passed = complete and bool(final)
    else:
        passed = hit_rate >= threshold and complete and bool(final)
    return {
        "case_id": case.id,
        "passed": passed,
        "keyword_hit": round(hit_rate, 3),
        "keywords": keywords,
        "rounds": result.get("round", 0),
        "drafts": len(result.get("drafts") or []),
        "flow_complete": complete,
        "latency_s": round(latency_s, 3),
        "errors": result.get("errors") or [],
        "notes": case.notes,
    }


def _print_table(rows: list[dict]) -> None:
    header = f"{'用例':<16}{'结果':<6}{'关键词命中':<10}{'轮次':<6}{'草稿数':<8}{'流程完整':<8}{'耗时(s)':<8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id']:<16}{mark:<6}{r['keyword_hit']:<10}{r['rounds']:<6}{r['drafts']:<8}"
            f"{('ok' if r['flow_complete'] else 'BAD'):<8}{r['latency_s']:<8}"
        )
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    print("-" * len(header))
    print(f"合计: {passed}/{total} 通过\n")


def _write_report(rows: list[dict], out_dir: Path, mock: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps({"mode": "mock" if mock else "live", "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 评测报告（多智能体）",
        "",
        f"- 模式：{'离线 mock' if mock else '真实调用'}",
        f"- 通过：{sum(1 for r in rows if r['passed'])}/{len(rows)}",
        "",
        "| 用例 | 结果 | 关键词命中 | 轮次 | 草稿数 | 流程完整 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['case_id']} | {'✅' if r['passed'] else '❌'} | {r['keyword_hit']} "
            f"| {r['rounds']} | {r['drafts']} | {'ok' if r['flow_complete'] else 'BAD'} | {r['latency_s']} |"
        )
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多智能体模板自动化评测")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--out", type=str, default="eval_results")
    args = parser.parse_args(argv)

    settings = get_settings()
    threshold = args.threshold if args.threshold is not None else settings.eval_min_keyword_hit

    if args.mock:
        # 多智能体替身是「按顺序消费」的状态机：每个用例必须独立实例，避免串场
        from app.llm.fakes import FakeGateway

        cases = SAMPLE_CASES[: args.limit] if args.limit else SAMPLE_CASES
        rows = [
            run_case(
                build_graph(FakeGateway(), settings, max_rounds=args.max_rounds),
                case,
                threshold,
                args.max_rounds,
                mock=True,
            )
            for case in cases
        ]
    else:
        from app.llm.gateway import get_gateway

        graph = build_graph(get_gateway(), settings, max_rounds=args.max_rounds)
        cases = SAMPLE_CASES[: args.limit] if args.limit else SAMPLE_CASES
        rows = [
            run_case(graph, case, threshold, args.max_rounds, mock=False) for case in cases
        ]

    _print_table(rows)
    _write_report(rows, Path(args.out), args.mock)
    if args.mock:
        print("（mock 模式：仅验证管道连通性；关键词门槛在真实模式生效）")

    failed = [r["case_id"] for r in rows if not r["passed"]]
    if failed:
        print(f"未达标用例（阈值 {threshold}）: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"全部通过（阈值 {threshold}）。报告见 {args.out}/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
