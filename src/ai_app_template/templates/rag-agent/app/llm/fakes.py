"""离线测试替身（rag-agent 版）。

FakeGateway 的 generate 是**输入感知**的：从请求里的资料块中解析出
第一个 doc_id，引用其第一句原文 —— 因此任何查询都能产出「能通过
verify 校验」的合法回答，完整走通「检索 -> 生成 -> 校验」链路；
伪造引用场景由测试通过 scripted 覆盖。
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any, Callable

from app.llm.gateway import GatewayExhaustedError, LLMRequest, LLMResponse

DOC_ID_RE = re.compile(r"\[doc_id:\s*(.+?)\]")


def scripted_answer_for(context_message: str) -> str:
    """从 generate 节点的用户消息（含检索资料）中确定性构造 AnswerSet。"""
    match = DOC_ID_RE.search(context_message)
    if not match:
        return json.dumps({"answer": "知识库中没有找到相关资料。", "citations": []}, ensure_ascii=False)
    doc_id = match.group(1)
    body = context_message.split(f"[doc_id: {doc_id}]", 1)[1]
    body = body.split("[doc_id:", 1)[0].strip()
    quote = body.split("。")[0] + "。" if body else ""
    answer = f"根据资料（{doc_id}）：{quote}"
    return json.dumps(
        {"answer": answer, "citations": [{"doc_id": doc_id, "quote": quote}]},
        ensure_ascii=False,
    )


class FakeGateway:
    def __init__(self, scripted: dict[str, str] | None = None):
        self.scripted = dict(scripted or {})
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        node = request.metadata.get("node", "unknown")
        if node in self.scripted:
            content = self.scripted[node]
        elif node == "generate":
            content = scripted_answer_for(request.messages[-1]["content"])
        else:
            content = "{}"
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
