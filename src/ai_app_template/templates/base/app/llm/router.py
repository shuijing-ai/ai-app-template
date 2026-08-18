"""成本感知路由：决定「这次调用用哪一档模型」。

MVP 采用透明的规则启发式而非 ML 打分 —— 每条规则都能被解释、被测试、
被面试官追问。若未来要升级为学习型路由，只需替换 ``classify`` 一个方法。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import ModelConfig, Settings
from app.llm.fallback import FallbackChain, chain_from_settings

# 任务名 -> 倾向档位（可被长度/结构化要求覆盖）
TASK_TIERS = {
    "general": "light",
    "chat": "light",
    "extract": "standard",
    "review": "standard",
    "rewrite": "standard",
    "planning": "heavy",
    "deep_analysis": "heavy",
}

LONG_INPUT_THRESHOLD = 1500  # 字符
VERY_LONG_INPUT_THRESHOLD = 6000


@dataclass
class RouteDecision:
    tier: str
    reasons: list[str] = field(default_factory=list)

    def explain(self) -> str:
        return f"tier={self.tier}（" + "；".join(self.reasons) + "）"


class CostAwareRouter:
    def __init__(self, settings: Settings):
        self._settings = settings

    # ---- 模型注册表访问 ----

    def model(self, alias: str) -> ModelConfig:
        try:
            return self._settings.models[alias]
        except KeyError:
            available = "、".join(self._settings.models)
            raise KeyError(f"未知模型别名 {alias!r}，已注册：{available}") from None

    def chain_for(self, tier: str) -> FallbackChain:
        return chain_from_settings(self._settings, tier)

    # ---- 路由决策 ----

    def classify(self, text: str, *, task: str = "general", structured: bool = False) -> RouteDecision:
        """根据输入长度 / 任务类型 / 是否结构化输出，选择 light|standard|heavy。"""
        tier = TASK_TIERS.get(task, "standard")
        reasons = [f"任务 {task} 默认倾向 {tier}"]

        n = len(text)
        if n > VERY_LONG_INPUT_THRESHOLD:
            tier = "heavy"
            reasons.append(f"输入超长（{n} > {VERY_LONG_THRESHOLD} 字符）")
        elif n > LONG_INPUT_THRESHOLD and tier == "light":
            tier = "standard"
            reasons.append(f"输入较长（{n} > {LONG_INPUT_THRESHOLD} 字符），light 升 standard")

        if structured and task in {"extract", "review"} and n > LONG_INPUT_THRESHOLD:
            tier = "heavy"
            reasons.append("长文本 + 严格结构化输出，升 heavy 保质量")

        return RouteDecision(tier=tier, reasons=reasons)

    # ---- 成本核算 ----

    def estimate_cost(self, alias: str, usage: dict) -> float:
        cfg = self.model(alias)
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        return (
            prompt / 1_000_000 * cfg.price_per_m_input
            + completion / 1_000_000 * cfg.price_per_m_output
        )
