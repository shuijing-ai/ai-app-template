## 模板说明：voice-flow

本模板在通用骨架之上实现了**会议转写处理流**：

```
START -> ingest(确定性清洗) -> summarize(LLM) -> extract_todos(LLM) -> finalize(确定性归并) -> END
```

| 节点 | 类型 | 说明 |
| --- | --- | --- |
| ingest | 确定性 | 清除 ASR 噪音：时间戳 `[00:12:34]`、说话人标签 `张三：`/`【张三】`、口头填充词；统计清理量 |
| summarize | LLM | `SummarySet`：200 字摘要 + 3-5 个议题；LLM 不可用时退化为确定性节选 |
| extract_todos | LLM | `TodoSet`：待办（action/owner/due）；**宁缺毋滥**——失败返回空并记录错误，绝不编造待办 |
| finalize | 确定性 | 待办去重（归一化 action）、有截止时间/负责人的排前面、截断到 10 条 |

### 设计要点：为什么模板不内置 ASR

语音转写（Whisper 等）是独立服务，接口形态（文件/流式/实时）因场景而异。
本模板的边界从**转写文本**开始——外部 ASR 完成转写后 POST `/v1/meetings` 即可，
模板不绑定任何语音供应商，测试也因此完全离线（FakeGateway 预置含重复待办，
专门验证 finalize 去重路径）。

### 涉及文件

- `app/graph/nodes/ingest_node.py` —— 正则清洗与噪音统计
- `app/graph/nodes/finalize_node.py` —— 确定性去重排序
- `app/main.py` —— `POST /v1/meetings` 接口
