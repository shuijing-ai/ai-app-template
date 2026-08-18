"""降级策略定义。

一条 FallbackChain 就是一个「按序尝试」的模型别名队列：
头部是首选（通常最便宜/最快），尾部是最后的兜底。
路由层给出 tier，网关层消费 chain，两层解耦。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FallbackChain:
    models: tuple[str, ...]
    name: str = ""

    def __post_init__(self) -> None:
        if not self.models:
            raise ValueError("FallbackChain 不能为空")

    def __iter__(self):
        return iter(self.models)

    def __len__(self) -> int:
        return len(self.models)

    @property
    def primary(self) -> str:
        return self.models[0]


def chain_from_settings(settings, tier: str) -> FallbackChain:
    """按 tier 从配置解析降级链；未知 tier 回落到默认 tier。"""
    chains = settings.tier_chains
    models = chains.get(tier) or chains.get(settings.default_tier)
    if not models:
        raise ValueError(f"配置中没有任何 tier chain 可用：{chains}")
    return FallbackChain(models=tuple(models), name=tier)
