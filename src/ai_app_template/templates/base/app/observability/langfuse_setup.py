"""LangFuse 可观测性接入（可选，零依赖退化）。

设计要点：观测能力通过「替换 OpenAI 客户端类」实现 ——
LangFuse v3 提供 ``langfuse.openai`` 模块（与 openai SDK 同接口、自动埋线），
因此网关代码完全不用改，观测开关只决定注入哪个客户端工厂。

未安装 langfuse / 未配置密钥时，一切照常工作，只是没有 trace。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

_checked: bool = False
_factory: Callable[..., Any] | None = None


def observability_enabled() -> bool:
    return os.getenv("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes"}


def get_openai_client_factory() -> Callable[..., Any]:
    """返回 OpenAI 客户端类；观测开启且 langfuse>=3 已安装时返回自动埋线版本。"""
    global _checked, _factory
    if _checked:
        assert _factory is not None
        return _factory

    _checked = True
    _factory = _default_openai
    if observability_enabled():
        try:
            from langfuse.openai import OpenAI as LangfuseOpenAI  # type: ignore[import]

            _factory = LangfuseOpenAI
            logger.info("LangFuse 观测已启用：LLM 调用将自动上报 trace")
        except ImportError:
            logger.warning(
                "LANGFUSE_ENABLED=true 但未安装 langfuse（pip install '.[observability]'），观测关闭"
            )
    else:
        logger.debug("LangFuse 观测未启用（设置 LANGFUSE_ENABLED=true 开启）")
    return _factory


def _default_openai(**kwargs: Any) -> Any:
    from openai import OpenAI

    return OpenAI(**kwargs)
