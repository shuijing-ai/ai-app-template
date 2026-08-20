"""评测集（rag-agent 版）：问答对 + 期望信号。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    query: str
    expect_keywords: list[str] = field(default_factory=list)  # 应出现在 answer 中
    expect_min_citations: int = 0
    tier: str = "seed"  # 手写种子用例；生成用例为 happy/boundary/anomaly/adversarial
    notes: str = ""


SAMPLE_CASES: list[EvalCase] = [
    EvalCase(
        id="return-policy",
        query="退货政策是什么？运费谁承担？",
        expect_keywords=["退货", "运费"],
        expect_min_citations=1,
        notes="核心政策问答，必须带合法引用",
    ),
    EvalCase(
        id="membership",
        query="会员有几个等级？金卡有什么权益？",
        expect_keywords=["金卡"],
        expect_min_citations=1,
    ),
    EvalCase(
        id="delivery",
        query="下单后多久能送到？",
        expect_keywords=["工作日"],
        expect_min_citations=1,
    ),
    EvalCase(
        id="kb-miss",
        query="你们董事长今年多少岁？",
        expect_keywords=[],
        expect_min_citations=0,
        notes="知识库外问题：考察「不编造」路径",
    ),
]
