"""全局配置（Pydantic Settings）。

约定：
- 所有环境变量带 ``APP_`` 前缀，例如 ``APP_GATEWAY_MAX_RETRIES=3``；
- 嵌套字段用双下划线覆盖，例如 ``APP_MODELS__FLASH__MODEL_ID=qwen-turbo``；
- 模型注册表中的价格为「每百万 token」单位，示例价格请按你所用服务商修改。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """模型注册表条目：别名 -> 具体模型与计价。

    别名（flash/pro/backup）贯穿路由、降级链与监控报表，
    换供应商时只改这里的 model_id/base_url，业务代码零改动。
    """

    model_id: str
    base_url: str | None = None  # None 表示用 OpenAI 官方地址
    api_key_env: str = "OPENAI_API_KEY"
    price_per_m_input: float = 0.0  # 每百万输入 token 价格（美元）
    price_per_m_output: float = 0.0


DEFAULT_MODELS: dict[str, ModelConfig] = {
    "flash": ModelConfig(
        model_id="gpt-4o-mini",
        price_per_m_input=0.15,
        price_per_m_output=0.60,
    ),
    "pro": ModelConfig(
        model_id="gpt-4o",
        price_per_m_input=2.50,
        price_per_m_output=10.00,
    ),
    # 跨供应商兜底示例：主模型全挂时切到 DeepSeek
    "backup": ModelConfig(
        model_id="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        price_per_m_input=0.27,
        price_per_m_output=1.10,
    ),
}

DEFAULT_TIER_CHAINS: dict[str, list[str]] = {
    "light": ["flash"],
    "standard": ["flash", "backup"],
    "heavy": ["pro", "flash"],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "{{ project_name }}"
    debug: bool = False

    # ---- 模型网关 ----
    default_tier: str = "standard"
    gateway_max_retries: int = 2  # 单模型额外重试次数（总尝试 = 1 + 该值）
    gateway_backoff_base_s: float = 1.0
    gateway_backoff_cap_s: float = 30.0
    gateway_backoff_jitter_s: float = 0.5
    breaker_failure_threshold: int = 3  # 连续失败 N 次后熔断
    breaker_cooldown_s: float = 60.0  # 熔断冷却时间

    # ---- 业务节点 ----
    extract_max_input_chars: int = 12000

    # ---- 评测 ----
    eval_min_keyword_hit: float = 0.6  # 低于该命中率的用例视为失败（CI 门槛）

    # ---- 模型注册表与分层降级链 ----
    models: dict[str, ModelConfig] = DEFAULT_MODELS
    tier_chains: dict[str, list[str]] = DEFAULT_TIER_CHAINS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
