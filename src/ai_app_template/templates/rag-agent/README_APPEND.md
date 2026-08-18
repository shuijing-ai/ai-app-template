## 模板说明：rag-agent

本模板在通用骨架（模型网关 / 降级 / 可观测 / 评测）之上，替换了工作流层：

```
START -> retrieve -> generate -> verify ->(条件边) generate(引用修正重试) / END
```

| 文件 | 说明 |
| --- | --- |
| `app/retrieval/store.py` | 纯 Python TF-IDF 检索（`InMemoryStore`），接口对齐向量库 |
| `data/sample_kb.md` | 示例知识库（按 `##` 标题切分为文档） |
| `app/graph/nodes/verify_node.py` | **确定性引用校验**：doc_id 必须命中检索结果，quote 必须逐字存在于原文 |
| `app/main.py` | `POST /v1/answers` 问答接口 |

### 为什么自带 TF-IDF 而不是接 Milvus？

RAG 系统的质量瓶颈几乎从不在「存储引擎」，而在「检索-生成-校验」的链路设计。
先用零依赖实现把链路跑通、测试写满，生产化时把 `InMemoryStore` 换成任何
实现了 `add() / search()` 的向量库即可，其余代码零改动。

### 引用校验（grounding check）

`verify_node` 用约 30 行确定性代码解决 RAG 落地最大的坑——模型编造引用：
- 引用的 `doc_id` 必须出现在本次检索结果中；
- `quote` 的前 40 字（忽略空白）必须逐字出现在该文档里；
- 校验失败会自动带着失败原因重试一次生成，再失败则剔除引用并标记 `citation_valid=false`。
