"""离线测试替身（voice-flow 版）。

FakeGateway 为 summarize / extract_todos 提供与节点 schema 一致的
预置响应；extract_todos 预置里故意带一条重复待办，供 finalize 去重测试使用。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from app.llm.gateway import GatewayExhaustedError, LLMRequest, LLMResponse

DEFAULT_SCRIPTED: dict[str, str] = {
    "summarize": (
        '{"summary": "会议讨论了发布计划与风险：两周内完成灰度发布，'
        '验收标准由张三补充，风险由李四跟进同步。", '
        '"topics": ["发布计划", "验收标准", "风险同步"]}'
    ),
    "extract_todos": (
        '{"todos": ['
        '{"action": "补充验收标准", "owner": "张三", "due": "周五"},'
        '{"action": "同步排期风险", "owner": "李四", "due": ""},'
        '{"action": "补充验收标准", "owner": "张三", "due": "周五"}'  # 故意重复，测 finalize 去重
        "]}"
    ),
}


class FakeGateway:
    def __init__(self, scripted: dict[str, str] | None = None):
        self.scripted = dict(DEFAULT_SCRIPTED)
        if scripted:
            self.scripted.update(scripted)
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        node = request.metadata.get("node", "unknown")
        content = self.scripted.get(node, "{}")
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
