"""离线测试替身（fake）：让整个工作流不花一分钱、不发一个请求就能全绿。

- ``FakeGateway``：extract 节点用**输入感知的词法规则**生成确定性 findings
  （风险词表命中即报），其他节点返回预置响应；
- ``FailingGateway``：永远抛 GatewayExhaustedError，验证兜底路径；
- ``ScriptedClient``：OpenAI 客户端级别的脚本替身，精确测试网关的
  重试/熔断/降级逻辑（可以按模型名抛指定异常）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable

from app.llm.gateway import GatewayExhaustedError, LLMRequest, LLMResponse

# 风险词表：关键词命中即产出一条对应类别的候选问题（确定性、可解释）
RISK_LEXICON: list[tuple[str, str]] = [
    ("违约", "compliance"),
    ("交付", "compliance"),
    ("验收", "compliance"),
    ("保密", "compliance"),
    ("终止", "compliance"),
    ("里程碑", "logic"),
    ("预算", "logic"),
    ("风险", "logic"),
    ("来源", "evidence"),
    ("数据", "evidence"),
]

MAX_FAKE_FINDINGS = 5

DEFAULT_SCRIPTED: dict[str, str] = {
    "review": (
        '{"decisions": ['
        '{"index": 0, "keep": true, "reason": "风险成立"},'
        '{"index": 1, "keep": true, "reason": "风险成立"},'
        '{"index": 2, "keep": false, "reason": "证据不足，退回待核"}'
        "]}"
    ),
    "summary": (
        "审阅完成：复核保留了主要风险项。建议针对交付范围、违约条款等关键内容"
        "补充明确约定，并对存疑处人工复核。"
    ),
}


def scripted_findings_for(text: str) -> str:
    """按风险词表从输入文本确定性生成 FindingSet JSON。"""
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    findings = []
    for keyword, category in RISK_LEXICON:
        if keyword not in text:
            continue
        paragraph = next((p for p in paragraphs if keyword in p), text[:60])
        findings.append(
            {
                "quote": paragraph[:60],
                "issue": f"检测到与「{keyword}」相关的潜在风险，需人工复核",
                "category": category,
                "severity": 3,
            }
        )
        if len(findings) >= MAX_FAKE_FINDINGS:
            break
    return json.dumps({"findings": findings}, ensure_ascii=False)


class FakeGateway:
    """接口与 ModelGateway 一致的最小替身。

    - extract：默认用词法规则响应实际输入（可通过 scripted["extract"] 覆盖）；
    - 其他节点：返回 scripted 预置内容。
    """

    def __init__(self, scripted: dict[str, str] | None = None):
        self.scripted = dict(DEFAULT_SCRIPTED)
        if scripted:
            self.scripted.update(scripted)
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        node = request.metadata.get("node", "unknown")
        if node in self.scripted:
            content = self.scripted[node]
        elif node == "extract":
            content = scripted_findings_for(request.messages[-1]["content"])
        else:
            content = '{"items": []}'
        return LLMResponse(
            content=content,
            model="fake",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_s=0.001,
            attempts=1,
            fell_back=False,
        )


class FailingGateway:
    """永远失败：用于验证节点级兜底（工作流不能被 LLM 故障打死）。"""

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise GatewayExhaustedError("failing gateway for test")


class ScriptedClient:
    """OpenAI 客户端替身：handlers[模型ID] -> 返回内容字符串或抛异常。

    记录所有调用参数到 self.calls，供断言重试次数/参数正确性。
    """

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


def script_factory(handlers: dict[str, Callable[[dict], Any]]) -> Callable[..., ScriptedClient]:
    """gateway(client_factory=...) 需要的是「类」，包一层按参数实例化。"""

    def factory(**_kwargs: Any) -> ScriptedClient:
        return ScriptedClient(handlers)

    return factory
