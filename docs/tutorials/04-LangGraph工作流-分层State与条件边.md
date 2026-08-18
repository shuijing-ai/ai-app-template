# 04 · LangGraph 工作流：分层 State 与条件边

> 目标：读懂 `templates/base/app/state.py` 与 `app/graph/`，
> 建立「图即业务」的编排心智，并理解三个模板各自的教学点。

## 1. State 是唯一的数据总线

`state.py` 的分层：

```python
class SharedState(TypedDict, total=False):
    trace_id: str
    errors: Annotated[list[str], operator.add]   # 追加式合并

class ReviewState(SharedState, total=False):     # 业务层继承共享层
    document: str
    findings: Annotated[list[dict], operator.add]
    ...
```

**为什么用 `Annotated[list, operator.add]`**：LangGraph 的 reducer 机制。
默认行为是「后写覆盖先写」，声明 `operator.add` 后变成「追加合并」。
对 findings/messages 这类多节点累积的字段，没有 reducer 的话，
extract 节点重试一次就会把上次结果冲掉——这是真实踩过的坑。

**为什么 `total=False`**：每个节点只返回自己写过的键，缺省键不占内存、
不强迫每个节点都初始化全量 State。配合 reducer，节点之间彻底解耦。

## 2. 节点 = 工厂函数（依赖注入的钥匙）

```python
def extract_node(gateway, settings=None):
    def node(state: dict) -> dict:
        ...gateway.complete(request)...
        return {"findings": items, "extract_attempts": attempts, ...}
    return node
```

节点不 import 全局网关，而是**由 builder 注入**：

```python
graph.add_node("extract", extract_node(gateway, settings))
# 测试时：
build_graph(FakeGateway())        # 离线替身
build_graph(FailingGateway())     # 故障演练
```

一个参数同时实现了可测试、可替换、可观测（见教程 03 的 client_factory）。

## 3. 条件边：工作流的「if」

review-flow 的核心编排：

```python
def route_after_extract(state) -> str:
    if state.get("extract_ok"):  return "review"
    if state.get("extract_attempts", 0) >= 2: return "review"   # 放弃，降级继续
    return "extract"                                             # 重试一次

graph.add_conditional_edges("extract", route_after_extract,
                            {"extract": "extract", "review": "review"})
```

这是「LLM 输出不稳定」在编排层的直接回应：失败→重试一次→仍失败→
**带着空结果继续**而不是 500。对照测试：

- `test_happy_path_with_fake_gateway`：正常路径 3 段 → 2 发现 → 2 保留
- `test_llm_total_outage_degrades_gracefully`：全挂时 attempts==2、errors 非空、
  summary 仍有值

条件边函数必须是**纯函数**（只读 state、无副作用），这让它自身可单测
（`test_route_after_extract_rules` 三个断言覆盖三分支）。

## 4. 三个模板，三种编排范式

### review-flow：线性 + 回边（默认模板）

```
parse →(确定)→ extract →(条件重试)→ review → summary
```

教学点：不是每个节点都需要 LLM。parse 用 40 行正则完成切分——
**能用确定性代码解决的事不要烧 token**。

### rag-agent：生成-校验循环（templates/rag-agent/）

```
retrieve →(TF-IDF)→ generate(带引用) → verify(确定性校验) →(伪造则重试)
```

教学点：verify 是纯代码的 grounding check（doc_id 必须在检索结果中、
quote 前 40 字必须逐字存在）。**用确定性代码兜住概率系统的可信度**。

### multi-agent：动态路由 + 预算（templates/multi-agent/）

```
supervisor →(LLM 决策)→ researcher|writer|critic → 回 supervisor …
```

教学点：无监督循环必须有两道终止保险——critic 的 pass 短路 +
轮次预算强制收尾。**会结束的多智能体才是能上线的多智能体**。
supervisor 的调度规则刻意做成「确定性优先」：第 1 轮必调研、
pass 必收尾、LLM 只负责中间那些真正需要判断的调度。

## 5. 图的编译与复用

```python
graph = StateGraph(ReviewState) ... return graph.compile()
```

`compile()` 做两件事：校验边引用的节点都存在；返回可 invoke 的执行器。
`app/main.py` 里 `@lru_cache` 包住 `build_graph()`——图编译一次进程内复用，
请求间只传不同的初始 State。

## 6. 动手练习

1. 给 review-flow 加一个 `translate` 节点（summary 后翻译成英文），
   并为其写 Fake 响应与测试。
2. 把 `route_after_extract` 的重试上限从硬编码 2 改为读取 settings
   （`extract_max_attempts`），同步修改两个测试。
3. 进阶：为 multi-agent 增加第四个工人 `fact-checker`，只处理含
   「数据/调查」关键词的任务——在哪一层加判断最合适？

## 7. 自测题

1. `Annotated[list[dict], operator.add]` 不写会发生什么？构造一个具体故障场景。
2. 条件边函数为什么必须是纯函数？
3. review-flow 为什么让 parse 确定性而不是「让 LLM 顺便切分」？
4. multi-agent 的两道终止保险分别防什么事故？
5. `graph.compile()` 之后再 `add_node` 会怎样？为什么图是编译型的？

下一篇：[05 结构化输出——包装类与安全解包](05-结构化输出-包装类与安全解包.md)。
