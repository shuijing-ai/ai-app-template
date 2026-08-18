"""评测集定义：把「质量」变成可回归的数字。

约定：EvalCase 只描述输入与期望信号（关键词命中数、最小发现数），
不绑定任何具体实现 —— 换模型、换提示词、换路由策略，评测集不动，
跑分结果才能横向对比。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    document: str
    expect_keywords: list[str] = field(default_factory=list)  # 在 findings+summary 中应出现
    expect_min_findings: int = 0
    notes: str = ""


CONTRACT_DOC = """\
## 交付条款
本项目将在三个月内完成交付，具体范围以双方沟通为准。

## 违约条款
如乙方延期，违约金为合同总额的百分之五十，按日累计。

## 运维条款
乙方负责全部运维工作。
"""

PLAN_DOC = """\
## 项目计划
第一季度完成调研，之后开始开发，尽量在年底上线。
预算方面初步估计五十万，视情况调整。

## 风险
暂无。
"""

REPORT_DOC = """\
## 市场分析
调查显示市场份额将达到百分之七十，用户满意度提升三倍。
竞争对手已全面落后。
"""

PLAIN_DOC = """\
## 会议纪要
本次会议确认了周报模板与例会时间：每周一上午十点，全体成员参加。
周报需包含本周进展、下周计划与需要的支持三项内容。
"""

LONG_DOC = """\
## 合作协议（节选）
甲方委托乙方开发数据平台，工期共六个月。

## 付款条款
合同签订后支付百分之三十，交付后支付百分之四十，
剩余百分之三十在验收合格后十个工作日内支付。

## 知识产权
全部成果归甲方所有。

## 保密条款
双方对本协议内容保密，保密期两年，违约需赔偿全部损失。

## 终止条款
任一方可提前七天书面通知终止本协议，无需赔偿。
"""

SAMPLE_CASES: list[EvalCase] = [
    EvalCase(
        id="contract-risk",
        document=CONTRACT_DOC,
        expect_keywords=["违约", "交付"],
        expect_min_findings=2,
        notes="高违约金 + 模糊交付范围，是审阅类应用最典型的用例",
    ),
    EvalCase(
        id="plan-vague",
        document=PLAN_DOC,
        expect_keywords=["验收", "风险"],
        expect_min_findings=1,
        notes="里程碑模糊、预算无依据、「风险：暂无」本身即风险",
    ),
    EvalCase(
        id="report-no-evidence",
        document=REPORT_DOC,
        expect_keywords=["来源", "数据"],
        expect_min_findings=1,
        notes="数据断言无来源支撑",
    ),
    EvalCase(
        id="plain-no-risk",
        document=PLAIN_DOC,
        expect_keywords=[],
        expect_min_findings=0,
        notes="无风险文档不应编造问题（考察空结果路径）",
    ),
    EvalCase(
        id="long-mixed",
        document=LONG_DOC,
        expect_keywords=["保密", "终止"],
        expect_min_findings=2,
        notes="长文本多风险混合",
    ),
]
