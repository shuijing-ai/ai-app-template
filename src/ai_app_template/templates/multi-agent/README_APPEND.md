## 模板说明：multi-agent

本模板在通用骨架之上实现了 **Supervisor 模式**的多智能体协作：

```
START -> supervisor ->(动态路由) researcher | writer | critic | END
             ^                    |
             +--------------------+   工人执行完回到 supervisor
```

| 角色 | 职责 | 结构化输出 |
| --- | --- | --- |
| supervisor | 调度中枢：决定下一个工人，或收尾 | `NextAction` |
| researcher | 把任务拆成调研要点 | `ResearchSet` |
| writer | 依据要点（与评审意见）产出/修改草稿 | 纯文本 |
| critic | 评审草稿，pass / revise | `CritiqueSet` |

### 两个关键的工程约束

1. **轮次预算（max_rounds）**：agent 循环失控是无监督多智能体最常见的事故。
   supervisor 每轮 +1，超预算强制收尾并返回已有最佳产出 —— 流程必然终止。
2. **确定性优先的调度规则**：第 1 轮固定先调研、critic 给 pass 立即收尾、
   LLM 不可用直接兜底收尾。LLM 只负责「需要判断」的那一步调度，
   这样整个编排的行为边界是可测试、可解释的。

### 涉及文件

- `app/graph/nodes/supervisor_node.py` —— 调度与预算控制
- `app/graph/builder.py` —— 条件边路由表
- `app/main.py` —— `POST /v1/tasks` 任务接口
- `app/llm/fakes.py` —— **状态化** FakeGateway（按 node 顺序消费响应队列），
  这类替身是编写多智能体确定性测试的关键技巧
