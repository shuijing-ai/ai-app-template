"""变更感知建议（--suggest）与多次采样聚合（--runs N）。

--suggest：读 git 工作区相对 HEAD 的变更文件，按影响映射表打印
「该跑哪个套件」的建议。v1 是提示制而非全自动（见设计文档 §6.2）：
目标是消除「不知道跑什么」的决策成本，不消灭人工确认。

--runs N：同一份用例连跑 N 次，逐用例通过与否取多数决、
关键词命中率取中位数，再进回退判定——抑制 live 模式的天然波动。
"""

from __future__ import annotations

import subprocess
from statistics import median

# (路径前缀, 影响说明, 建议命令)
IMPACT_MAP: list[tuple[str, str, str]] = [
    (
        "app/graph/nodes/",
        "提示词/节点逻辑变更，影响全部用例",
        "python -m app.eval.run_eval --suite all",
    ),
    (
        "app/schema/wrappers.py",
        "输出结构变更，schema 合法性需重点回归",
        "python -m app.eval.run_eval --mock  # 先冒烟，再 --suite all",
    ),
    (
        "app/llm/",
        "网关/路由/降级变更，档位与成本需复验",
        "python -m app.eval.run_eval --suite all  # 关注报告中的成本与延迟",
    ),
    (
        "app/eval/",
        "评测体系自身变更，不影响被测系统",
        "无需重跑（如需验证体系本身：python -m app.eval.run_eval --mock）",
    ),
]


def changed_files() -> list[str]:
    """工作区（已改+未跟踪）相对 HEAD 的变更文件；不在 git 仓库或无 git 时返回空。

    尚无任何提交的全新仓库没有 HEAD，此时全部文件都在未跟踪列表里，
    依然可以给出建议。
    """
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if diff.returncode != 0 and untracked.returncode != 0:
        return []  # 非 git 仓库
    lines = (diff.stdout or "") + (untracked.stdout or "")
    return [line.strip() for line in lines.splitlines() if line.strip()]


def print_suggestions(files: list[str]) -> None:
    if not files:
        print("未检测到未提交变更（或当前不在 git 仓库中）。比对历史改动可用 git diff 自查。")
        return
    print(f"检测到 {len(files)} 个变更文件，评测建议：")
    matched: set[str] = set()
    for name in files:
        for prefix, impact, command in IMPACT_MAP:
            if name.startswith(prefix) and prefix not in matched:
                matched.add(prefix)
                print(f"  - {name}\n      {impact}\n      建议命令：{command}")
    if not matched:
        print("  变更不影响评测面（文档/配置等），按需跑 --mock 冒烟即可。")


def median_rows(runs: list[list[dict]]) -> list[dict]:
    """多次跑分聚合：通过与否多数决（strict majority），命中率取中位数。

    其余字段（延迟、发现数等）取最后一次，用于表格展示。
    """
    if len(runs) == 1:
        return runs[0]
    samples_by_case: dict[str, list[dict]] = {}
    for rows in runs:
        for row in rows:
            samples_by_case.setdefault(row["case_id"], []).append(row)
    merged: list[dict] = []
    for case_id, samples in samples_by_case.items():
        latest = samples[-1]
        merged.append(
            {
                **latest,
                "passed": sum(1 for s in samples if s["passed"]) * 2 > len(samples),
                "keyword_hit": round(median(s["keyword_hit"] for s in samples), 3),
            }
        )
    return merged
