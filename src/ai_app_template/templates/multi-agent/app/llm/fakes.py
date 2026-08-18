"""离线测试替身（multi-agent 版）。

多智能体是**有状态**的多轮流程，静态替身不够用 ——
FakeGateway 为每个 node 维护一个「按顺序消费、耗尽后重复最后一项」
的响应队列，可以精确编排 supervisor 的每一轮调度。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from app.llm.gateway import GatewayExhaustedError, LLMRequest, LLMResponse

DRAFT_TEXT = "ai-app-template 一键生成生产级 AI 应用骨架：内置模型网关、降级兜底与自动化评测，开箱即用。"

DEFAULT_SCRIPTED: dict[str, list[str]] = {
    "supervisor": [
        '{"next": "writer", "reason": "调研资料已齐"}',
        '{"next": "critic", "reason": "已有初稿，进入评审"}',
    ],
    "researcher": ['{"points": [{"point": "明确目标用户与核心场景"}, {"point": "提炼两个差异化卖点"}]}'],
    "writer": [DRAFT_TEXT],
    "critic": ['{"verdict": "pass", "issues": []}'],
}


class FakeGateway:
    def __init__(self, scripted: dict[str, list[str]] | None = None):
        self.scripted = {k: list(v) for k, v in (scripted or DEFAULT_SCRIPTED).items()}
        self._last: dict[str, str] = {}
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        node = request.metadata.get("node", "unknown")
        queue = self.scripted.get(node)
        if queue:
            content = queue.pop(0)
            self._last[node] = content
        else:
            content = self._last.get(node, "{}")
        return LLMResponse(
            content=content,
            model="fake",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_s=0.001,
            attempts=1,
            fell_back=False,
        )


class FailingGateway:
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise GatewayExhaustedError("failing gateway for test")


class ScriptedClient:
    """OpenAI 客户端替身（与 base 模板一致，供网关单元测试复用）。"""

    def __init__(self, handlers: dict[str, Callable[[dict], Any]]):
        self.handlers = handlers
        self.calls: list[dict] = []
        self._chained = _Chained(self)

    @property
    def chat(self):
        return self._chained

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        handler = self.handlers.get(kwargs["model"], self.handlers.get("*"))
        if handler is None:
            raise KeyError(f"ScriptedClient 未脚本化模型: {kwargs['model']}")
        result = handler(kwargs)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result))],
            usage=SimpleNamespace(
                model_dump=lambda: {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            ),
        )


class _Chained:
    def __init__(self, client: ScriptedClient):
        self._client = client
        self.completions = self

    def create(self, **kwargs):
        return self._client._create(**kwargs)


def script_factory(handlers):
    def factory(**_kwargs) -> ScriptedClient:
        return ScriptedClient(handlers)

    return factory
