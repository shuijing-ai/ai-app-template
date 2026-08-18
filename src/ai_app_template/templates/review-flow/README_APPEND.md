## 模板说明：review-flow

这是 ai-app-template 的默认模板，也是最适合入门的工作流：

```
START -> parse -> extract ->(条件边: 失败重试一次) review -> summary -> END
```

| 节点 | 类型 | 说明 |
| --- | --- | --- |
| parse | 确定性 | Markdown 标题/段落切分，不花一次 LLM 调用 |
| extract | LLM | `FindingSet` 结构化提取候选问题 |
| review | LLM | `ReviewSet` 逐条复核，剔除不成立的候选 |
| summary | LLM | 汇总结论；**LLM 不可用时退化为确定性拼接** |

### 值得读的三处代码

1. `app/graph/builder.py` 的 `route_after_extract` —— 条件边如何实现「重试后降级继续」；
2. `app/graph/nodes/summary_node.py` 的 `deterministic_summary` —— 最小成本的兜底设计；
3. `tests/test_graph.py` 的 `test_llm_total_outage_degrades_gracefully` —— 如何证明兜底真的生效。
