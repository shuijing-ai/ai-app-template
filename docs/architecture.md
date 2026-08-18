# 架构与关键设计决策（ADR）

本文回答「ai-app-template 为什么长这样」。每个决策都给出背景与取舍，
方便贡献者理解决策边界，也方便使用者把同样的思路搬到自己的项目。

## 总体结构

ai-app-template 是一个 **CLI + 模板库** 的组合：

```
ai-app-template create my-app -t rag-agent
        │
        ▼
┌─────────────────────────────────────────────┐
│ CLI（typer）                                  │
│  create / list  ·  交互式与非交互（--yes）      │
├─────────────────────────────────────────────┤
│ 生成器 generator.py                           │
│  base 全量骨架 + 变体覆盖叠加 + 占位符渲染      │
│  _overlay.json 声明废弃文件 · README 追加段    │
├─────────────────────────────────────────────┤
│ 模板库 templates/                             │
│  base/        通用骨架（网关/图/评测/部署）     │
│  review-flow/ 文档审阅（默认，条件边重试）      │
│  rag-agent/   检索问答（TF-IDF + 引用校验）    │
│  multi-agent/ 多智能体（Supervisor + 预算）    │
└─────────────────────────────────────────────┘
```

生成项目内部的分层（三个模板共享同一套骨架）：

```
HTTP（FastAPI，只做协议转换）
  └── LangGraph 工作流（业务编排，节点全部依赖注入 gateway）
        └── 模型网关 ModelGateway（所有 LLM 调用唯一入口）
              ├── CostAwareRouter   成本感知路由（light/standard/heavy）
              ├── FallbackChain     降级链（可跨供应商）
              ├── CircuitBreaker    每模型熔断器
              └── GatewayStats      token/成本/耗时统计
                    └── LangFuse（可选，客户端类替换式接入）
```

## 关键决策记录

### ADR-1：命名全局统一为 ai-app-template

初版方案里 CLI 叫 `agent-forge`、PyPI 包却计划叫 `ai-app-template`，两个名字并存。
脚手架项目的名字就是品牌，必须全局唯一：GitHub 仓库、PyPI 包、Python 模块
（`ai_app_template`）、命令行入口（`ai-app-template`）四者同名。
最终定名 `ai-app-template`：直白描述「是什么」，对搜索（"ai app template"）
天然友好；代价是命令略长——换来的是零歧义与可检索性，值得。

### ADR-2：MVP 砍掉 Redis + PostgreSQL

初版 docker-compose 计划一键启动 Redis + PG + LangFuse，但 MVP 代码对
Redis/PG 零引用 —— 空转依赖是 cargo cult，会让新用户困惑「这些容器干嘛的」。
改为：应用零外部依赖可直接跑；观测栈（Postgres + LangFuse v2）放在
compose profile `observability` 里按需启动。等真正用到（如分布式限流、
评测结果入库）再把服务加回来，并让代码先有使用方。

### ADR-3：只依赖 LangGraph + openai SDK + pydantic，不引入 LangChain

LangGraph 做编排、openai SDK 做调用、pydantic 做结构化 —— 三者已覆盖全部需求。
不引入 LangChain 生态的链/代理抽象，避免版本耦合、概念负担与调试黑盒。
这个「薄依赖」决策让每个模块都可以单独读懂，是教学目标的一部分。

### ADR-4：观测能力用「客户端类替换」接入，而不是侵入代码

LangFuse v3 提供 `langfuse.openai`（与 openai SDK 同接口、自动埋线）。
网关的 `client_factory` 注入点原本就是为测试准备的，观测开关只是决定
注入原生还是埋线版客户端 —— 业务代码零改动、观测零侵入、未安装时零影响。
一个注入点解决两个问题（可测试性 + 可观测性），这是本仓库最值得抄的设计。

### ADR-5：生成的项目必须离线全绿

所有测试与 mock 评测不发一个真实请求：`FakeGateway`（节点级替身）+
`ScriptedClient`（SDK 级替身）是模板的一部分而非示例。
理由：① 新用户 30 秒内看到全绿才有信心；② CI 不需要密钥与预算；
③ 「如何确定性地测试 LLM 应用」本身就是最重要的教学点。

### ADR-6：渲染用 str.replace，不用 Jinja2

模板里的占位符只有 `{{ key }}` 一种形态，`str.replace` 足够。
收益：模板文件永远是合法的 Python/TOML/YAML，可以直接 `compile()` 校验
（仓库测试正是这么做的），也避免了模板语法失控（逻辑进模板是维护灾难）。

### ADR-7：变体覆盖用「文件级叠加 + 废弃清单」

变体目录覆盖 base 的同名文件；`_overlay.json` 的 `exclude` 声明被变体
淘汰的 base 文件（如 rag 模板不需要 review 节点）。
比「每模板全量复制」少 80% 重复，比「代码生成」可控得多。

### ADR-8：成本路由用规则启发式，不上 ML

`CostAwareRouter.classify` 用任务类型 + 输入长度 + 结构化要求三条规则选档。
MVP 阶段规则透明、可测试、可解释（面试被追问时每条都能说出为什么）；
等有真实流量数据后再考虑学习型路由，接口不变、只换实现。

### ADR-9：评测 mock 模式只验管道，不假装有质量

`--mock` 的通过标准是「流程走完 + schema 合法」，关键词/数量门槛只在
真实模式生效。替身不假装有质量 —— 把管道验证和质量门禁混在一杆秤上，
是评测体系腐化的第一步。

### ADR-10：入口点指向 app 对象

曾把 console script 指向 typer 的回调函数（`cli:main`），CLI 静默退出码 0。
回归测试 `test_console_script_entry_point` 用真实子进程调用二进制防止再犯。
教训：包装层（entry point / manifest / 配置）必须有自己的端到端测试。

## 数据流：一次 review-flow 请求

```
POST /v1/reviews {document}
  → trace_id 生成 → graph.invoke
    → parse：确定性按标题切分（0 次 LLM 调用）
    → extract：路由 → tier 链 → 网关（重试/熔断/降级）→ FindingSet
        ↘ 失败：条件边重试一次 → 仍失败则带空结果继续
    → review：ReviewSet 复核 → 剔除不成立项（失败则全保留）
    → summary：生成结论（失败则确定性拼接）
  → 响应：findings + summary + errors + gateway_stats
```

任何一层失败都不会让请求 500 —— 最坏情况是「空发现 + 错误说明 + 兜底摘要」。
这是「LLM 增强，而非 LLM 依赖」的完整表达。
