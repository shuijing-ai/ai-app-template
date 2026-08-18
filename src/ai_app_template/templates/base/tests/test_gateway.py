"""模型网关单元测试：重试 / 降级 / 熔断 / 成本核算，全部离线。"""

from __future__ import annotations

import httpx
import pytest
from openai import RateLimitError

from app.config import Settings
from app.llm.fakes import script_factory
from app.llm.gateway import GatewayExhaustedError, LLMRequest, ModelGateway


def make_settings(**overrides) -> Settings:
    params = dict(
        _env_file=None,
        gateway_max_retries=2,
        gateway_backoff_base_s=0.0,
        gateway_backoff_cap_s=0.0,
        gateway_backoff_jitter_s=0.0,
        breaker_failure_threshold=2,
        breaker_cooldown_s=60.0,
        default_tier="standard",
        tier_chains={"standard": ["flash", "backup"], "light": ["flash"]},
    )
    params.update(overrides)
    return Settings(**params)


def rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.test/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def make_request() -> LLMRequest:
    return LLMRequest(messages=[{"role": "user", "content": "审阅以下文档"}], task="extract", structured=True)


def test_retry_with_backoff_then_success():
    calls = {"n": 0}

    def handler(_kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise rate_limit_error()
        return "ok"

    gateway = ModelGateway(make_settings(), client_factory=script_factory({"*": handler}))
    response = gateway.complete(make_request())
    assert response.content == "ok"
    assert response.attempts == 3  # 失败两次，第三次成功
    assert response.fell_back is False
    assert response.model == "flash"


def test_non_retryable_error_falls_back_immediately():
    counts = {"flash": 0, "backup": 0}

    def flash(_kw):
        counts["flash"] += 1
        raise ValueError("invalid api key")  # 不可重试：直接换下一个模型

    def backup(_kw):
        counts["backup"] += 1
        return "from-backup"

    gateway = ModelGateway(
        make_settings(),
        client_factory=script_factory({"gpt-4o-mini": flash, "deepseek-chat": backup}),
    )
    response = gateway.complete(make_request())
    assert response.content == "from-backup"
    assert response.model == "backup"
    assert response.fell_back is True
    assert counts == {"flash": 1, "backup": 1}  # flash 只调了一次，没有无谓重试


def test_circuit_breaker_opens_and_skips_model():
    counts = {"flash": 0}

    def flash(_kw):
        counts["flash"] += 1
        raise rate_limit_error()

    def backup(_kw):
        return "ok"

    settings = make_settings(gateway_max_retries=0, breaker_failure_threshold=1)
    gateway = ModelGateway(
        settings,
        client_factory=script_factory({"gpt-4o-mini": flash, "deepseek-chat": backup}),
    )

    first = gateway.complete(make_request())
    assert first.model == "backup"
    assert gateway.breakers["flash"].state == "open"  # 阈值 1：一次失败即熔断

    gateway.complete(make_request())  # 第二次：flash 被熔断器直接跳过
    assert counts["flash"] == 1  # flash 总共只被真实调用过一次


def test_all_models_exhausted_raises():
    def always_fail(_kw):
        raise rate_limit_error()

    gateway = ModelGateway(
        make_settings(gateway_max_retries=0),
        client_factory=script_factory({"*": always_fail}),
    )
    with pytest.raises(GatewayExhaustedError):
        gateway.complete(make_request())
    assert gateway.stats.failures == 2  # 链上两个模型各失败一次


def test_cost_estimation_and_stats():
    gateway = ModelGateway(make_settings(), client_factory=script_factory({"*": lambda _kw: "ok"}))
    response = gateway.complete(make_request())
    # ScriptedClient 上报 usage: 10 prompt + 5 completion tokens，首选拆 flash 档价
    expected = 10 / 1e6 * 0.15 + 5 / 1e6 * 0.60
    assert response.cost == pytest.approx(expected)
    summary = gateway.stats.summary()
    assert summary["calls"] == 1
    assert summary["total_tokens"] == 15
    assert summary["total_cost_usd"] == pytest.approx(expected)


def test_router_unknown_alias_raises_helpful_error():
    from app.llm.router import CostAwareRouter

    router = CostAwareRouter(make_settings())
    with pytest.raises(KeyError, match="未知模型别名"):
        router.model("no-such-model")
