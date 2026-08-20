"""内置模板注册表。

新增一个模板只需三步：
1. 在 ``src/ai_app_template/templates/`` 下建一个同名目录（在 base 之上做覆盖叠加）；
2. 在本文件的 ``TEMPLATES`` 中注册元信息；
3. 在 ``tests/test_generator.py`` 的参数化列表里加上它。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    title: str
    description: str
    graph_shape: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


TEMPLATES: dict[str, TemplateInfo] = {
    "review-flow": TemplateInfo(
        id="review-flow",
        title="文档审阅工作流（默认）",
        description=(
            "parse -> extract -> review -> summary 四节点线性+条件回边工作流："
            "确定性解析、LLM 结构化提取、复核过滤、汇总兜底。最适合入门。"
        ),
        graph_shape="parse -> extract ->(条件重试) review -> summary",
        tags=("langgraph", "structured-output", "fastapi"),
    ),
    "rag-agent": TemplateInfo(
        id="rag-agent",
        title="检索增强问答 Agent",
        description=(
            "内置纯 Python TF-IDF 检索（可替换为任意向量库）、带引用生成、"
            "确定性引用校验（grounding check）三道工序。"
        ),
        graph_shape="retrieve -> generate(citations) -> verify",
        tags=("rag", "retrieval", "citations", "grounding"),
    ),
    "multi-agent": TemplateInfo(
        id="multi-agent",
        title="多智能体协作（Supervisor 模式）",
        description=(
            "supervisor 动态路由 researcher / writer / critic 三个专职 agent，"
            "循环协作直到任务完成或达到轮次上限。"
        ),
        graph_shape="supervisor ->(动态路由) researcher|writer|critic -> supervisor ...",
        tags=("multi-agent", "supervisor", "orchestration"),
    ),
    "voice-flow": TemplateInfo(
        id="voice-flow",
        title="语音会议纪要流",
        description=(
            "ingest(确定性清洗) -> summarize -> extract_todos -> finalize(确定性归并)："
            "转写文本进，摘要+议题+去重待办出。ASR 由外部提供，不绑定语音供应商。"
        ),
        graph_shape="ingest -> summarize -> extract_todos -> finalize",
        tags=("meeting", "transcript", "todos", "asr-friendly"),
    ),
}
