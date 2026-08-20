"""评测集（voice-flow 版）：会议转写 + 期望信号。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    transcript: str
    expect_keywords: list[str] = field(default_factory=list)  # 应出现在 summary+topics+todos
    expect_min_todos: int = 0
    tier: str = "seed"  # 手写种子用例；生成用例为 happy/boundary/anomaly/adversarial
    notes: str = ""


STANDUP = (
    "[00:00] 张三：本次迭代还剩登录模块，预计周四提测。\n"
    "[00:21] 李四：测试环境今天恢复，嗯，大家下午可以自测。\n"
    "[00:45] 王五：文档我来更新，周五前发出来。"
)

REVIEW_MEETING = (
    "【产品】这个版本必须包含新的审批流，就是说要支持两级审批。\n"
    "【研发】两级审批两周能做完，但性能压测需要提前排期，那个这个最好下周启动。\n"
    "【测试】自动化用例我跟进修一下，对对对，先补审批流的覆盖率。"
)

CLIENT_CALL = (
    "[00:02] 客户：合同里的违约条款我们需要再谈，百分之五十太高了。\n"
    "[00:38] 销售：我周五前给出一版修订建议，然后同步法务。\n"
    "[01:10] 客户：付款周期也想从三十天延长到六十天。"
)

FREE_CHAT = (
    "[00:00] 张三：周末团建去哪玩？\n"
    "[00:30] 李四：都行啊，看大家。\n"
    "[01:00] 王五：那还是老地方吧，先这样定了。"
)

SAMPLE_CASES: list[EvalCase] = [
    EvalCase(
        id="standup-todos",
        transcript=STANDUP,
        expect_keywords=["提测", "文档"],
        expect_min_todos=2,
        notes="站会：时间戳/说话人标签/口头填充混合，含明确待办",
    ),
    EvalCase(
        id="review-meeting",
        transcript=REVIEW_MEETING,
        expect_keywords=["审批"],
        expect_min_todos=2,
        notes="需求评审：含口头填充词（就是说/那个这个/对对对）",
    ),
    EvalCase(
        id="client-call",
        transcript=CLIENT_CALL,
        expect_keywords=["违约", "修订"],
        expect_min_todos=1,
        notes="客户电话：商务条款诉求 + 承诺动作",
    ),
    EvalCase(
        id="free-chat-no-todo",
        transcript=FREE_CHAT,
        expect_keywords=[],
        expect_min_todos=0,
        notes="闲聊无待办：考察「不编造待办」路径",
    ),
]
