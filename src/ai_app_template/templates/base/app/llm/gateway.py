"""统一模型网关：所有 LLM 调用的唯一入口。

职责（按调用顺序）：
1. 成本路由：按 tier 解析降级链（router.py）；
2. 熔断：每个模型别名一个 CircuitBreaker，连续失败则跳过；
3. 重试：可重试错误（限流/超时/网络）按指数退避 + 抖动重试；
4. 降级：当前模型彻底失败则切换链上的下一个模型（可跨供应商）；
5. 观测：记录每次调用的 token 用量、耗时、成本，供 /health 与评测使用。

测试注入点：``client_factory``（返回 OpenAI 兼容客户端），
离线测试用 ``app.llm.fakes.ScriptedClient`` 替换即可，不发任何真实请求。
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)

from app.config import Settings
from app.llm.fallback import FallbackChain
from app.llm.router import CostAwareRouter

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    """限流、超时、网络抖动、网关 5xx 值得重试；鉴权/参数错误重试没有意义。"""
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code in RETRYABLE_STATUS


class GatewayExhaustedError(RuntimeError):
    """降级链上所有模型都失败了。调用方（图节点）必须捕获并走兜底路径。"""


@dataclass
class LLMRequest:
    messages: list[dict[str, str]]
    task: str = "general"  # 供 router.classify 做档位决策
    structured: bool = False
    response_format: dict | None = None
    temperature: float = 0.2
    max_tokens: int = 2000
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    model: str  # 实际使用的模型别名
    usage: dict[str, int]
    latency_s: float
    attempts: int  # 在该模型上的尝试次数
    fell_back: bool  # 是否使用了非首选模型
    cost: float = 0.0
    route_reason: str = ""


class CircuitBreaker:
    """极简熔断器：closed -> open(冷却期内直接跳过) -> half-open(放行探测一次)。"""

    def __init__(self, failure_threshold: int = 3, cooldown_s: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        return "half-open" if time.time() - self._opened_at >= self.cooldown_s else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        if self.state == "half-open":  # 探测失败，重新熔断
            self._opened_at = time.time()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.time()


@dataclass
class GatewayStats:
    calls: int = 0
    failures: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    per_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def record(
        self, model: str, *, ok: bool, usage: dict | None = None, cost: float = 0.0, latency_s: float = 0.0
    ) -> None:
        self.calls += 1
        slot = self.per_model.setdefault(model, {"calls": 0, "failures": 0, "tokens": 0, "cost": 0.0})
        slot["calls"] += 1
        if not ok:
            self.failures += 1
            slot["failures"] += 1
            return
        tokens = (usage or {}).get("total_tokens", 0) or 0
        self.total_tokens += tokens
        self.total_cost += cost
        slot["tokens"] += tokens
        slot["cost"] += cost
        slot["latency_avg_s"] = (slot.get("latency_avg_s", 0.0) * (slot["calls"] - 1) + latency_s) / slot["calls"]

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "failures": self.failures,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 8),  # 单次调用成本在 1e-6 量级，保留足够精度
            "per_model": self.per_model,
        }


class ModelGateway:
    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., Any] | None = None,
        router: CostAwareRouter | None = None,
    ):
        self._settings = settings
        self._router = router or CostAwareRouter(settings)
        # 观测开关打开时，langfuse_setup 返回自动埋线的 OpenAI 兼容客户端类
        if client_factory is None:
            from app.observability.langfuse_setup import get_openai_client_factory

            client_factory = get_openai_client_factory()
        self._client_factory = client_factory
        self._clients: dict[str, Any] = {}
        self.breakers: dict[str, CircuitBreaker] = {}
        self.stats = GatewayStats()

    # ---- 对外主入口 ----

    def complete(self, request: LLMRequest) -> LLMResponse:
        decision = self._router.classify(
            "\n".join(m.get("content", "") for m in request.messages),
            task=request.task,
            structured=request.structured,
        )
        chain = self._router.chain_for(decision.tier)
        logger.info("路由决策 %s | chain=%s node=%s", decision.explain(), chain.models, request.metadata.get("node"))
        response = self.execute(chain, request)
        response.route_reason = decision.explain()
        return response

    def execute(self, chain: FallbackChain, request: LLMRequest) -> LLMResponse:
        """逐个模型尝试整条降级链，全部失败抛 GatewayExhaustedError。"""
        for alias in chain:
            breaker = self.breakers.get(alias)
            if breaker is None:
                breaker = CircuitBreaker(
                    failure_threshold=self._settings.breaker_failure_threshold,
                    cooldown_s=self._settings.breaker_cooldown_s,
                )
                self.breakers[alias] = breaker
            if not breaker.allow():
                logger.warning("模型 %s 熔断中（state=%s），跳过", alias, breaker.state)
                continue
            response = self._try_model(alias, request)
            if response is not None:
                response.fell_back = alias != chain.primary
                return response
        raise GatewayExhaustedError(f"降级链全部失败: {list(chain)}")

    # ---- 内部：单模型重试 ----

    def _try_model(self, alias: str, request: LLMRequest) -> LLMResponse | None:
        cfg = self._router.model(alias)
        started = time.perf_counter()
        max_attempts = self._settings.gateway_max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                client = self._client(alias, cfg)
                kwargs: dict[str, Any] = dict(
                    model=cfg.model_id,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
                if request.response_format:
                    kwargs["response_format"] = request.response_format
                raw = client.chat.completions.create(**kwargs)
                usage = self._extract_usage(raw)
                latency = time.perf_counter() - started
                self.breakers[alias].record_success()
                cost = self._router.estimate_cost(alias, usage)
                self.stats.record(alias, ok=True, usage=usage, cost=cost, latency_s=latency)
                content = raw.choices[0].message.content or ""
                logger.info(
                    "LLM ok model=%s attempt=%s latency=%.3fs tokens=%s cost=$%.6f",
                    alias, attempt, latency, usage.get("total_tokens"), cost,
                )
                return LLMResponse(
                    content=content,
                    model=alias,
                    usage=usage,
                    latency_s=latency,
                    attempts=attempt,
                    fell_back=False,
                    cost=cost,
                )
            except Exception as exc:
                retryable = is_retryable(exc)
                logger.warning(
                    "LLM error model=%s attempt=%s/%s retryable=%s: %r",
                    alias, attempt, max_attempts, retryable, exc,
                )
                if retryable and attempt < max_attempts:
                    self._sleep_backoff(attempt)
                    continue
                self.breakers[alias].record_failure()
                self.stats.record(alias, ok=False)
                return None  # 交给降级链的下一个模型
        return None

    def _client(self, alias: str, cfg):
        if alias not in self._clients:
            self._clients[alias] = self._client_factory(
                api_key=os.getenv(cfg.api_key_env, "EMPTY"),
                base_url=cfg.base_url,
            )
        return self._clients[alias]

    def _sleep_backoff(self, attempt: int) -> None:
        delay = min(
            self._settings.gateway_backoff_cap_s,
            self._settings.gateway_backoff_base_s * (2 ** (attempt - 1)),
        )
        delay += random.uniform(0, self._settings.gateway_backoff_jitter_s)
        logger.info("退避 %.2fs 后重试", delay)
        time.sleep(delay)

    @staticmethod
    def _extract_usage(raw: Any) -> dict:
        usage = getattr(raw, "usage", None)
        if usage is None:
            return {}
        dump = getattr(usage, "model_dump", None)
        return dump() if callable(dump) else dict(usage)


# ---- 进程级单例（生产路径用；测试请显式 new 一个并注入 fake） ----

_gateway: ModelGateway | None = None


def get_gateway() -> ModelGateway:
    global _gateway
    if _gateway is None:
        from app.config import get_settings

        _gateway = ModelGateway(get_settings())
    return _gateway


def reset_gateway() -> None:
    """测试辅助：清空单例。"""
    global _gateway
    _gateway = None
