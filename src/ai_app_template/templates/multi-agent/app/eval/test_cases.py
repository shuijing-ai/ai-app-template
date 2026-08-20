"""评测集（multi-agent 版）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    task: str
    expect_keywords: list[str] = field(default_factory=list)  # 应出现在最终产出中
    expect_min_drafts: int = 0
    tier: str = "seed"  # 手写种子用例；生成用例为 happy/boundary/anomaly/adversarial
    notes: str = ""


SAMPLE_CASES: list[EvalCase] = [
    EvalCase(
        id="product-intro",
        task="为 ai-app-template 写一段 100 字以内的中文产品介绍，必须包含「一键」与「降级」两个关键词。",
        expect_keywords=["一键", "降级"],
    ),
    EvalCase(
        id="email-draft",
        task="写一封 100 字以内的合作邀约邮件，需包含行动号召。",
        expect_keywords=[],
        notes="不设关键词，考察流程完整性（有调研、有草稿、有评审）",
    ),
    EvalCase(
        id="summary-task",
        task="把「网关、路由、降级」三个概念各用一句话解释给新人。",
        expect_keywords=["网关"],
    ),
]
