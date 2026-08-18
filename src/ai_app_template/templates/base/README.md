# {{ project_name }}

> {{ description }}
>
> 由 [ai-app-template](https://github.com/shuijing-ai/ai-app-template) 的 **{{ template_title }}**（`{{ template_id }}`）模板生成。

## 快速开始

```bash
# 1. 安装依赖
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env   # 填入你的 API Key

# 3. 离线验证（不花一分钱，不发一个请求）
pytest -q

# 4. 启动服务
uvicorn app.main:app --reload
# 打开 http://127.0.0.1:8000/docs 体验 Swagger

# 5. 离线跑评测管道（CI 冒烟；真实模式加质量门禁）
python -m app.eval.run_eval --mock
```

## 架构一览

```
HTTP (FastAPI)
  └── LangGraph 工作流（parse -> extract -> review -> summary）
        └── 每个节点通过统一模型网关调用 LLM
              ├── 成本路由 CostAwareRouter   按任务/长度选档（light/standard/heavy）
              ├── 降级链 FallbackChain       主模型失败自动切换备用（可跨供应商）
              ├── 熔断 CircuitBreaker        连续失败直接跳过，快速恢复靠半开探测
              └── 观测 GatewayStats(+LangFuse) token/成本/耗时全记录
```

## 目录导读

| 路径 | 职责 | 一句话记忆 |
| --- | --- | --- |
| `app/main.py` | FastAPI 入口 | 只做协议转换，不含业务 |
| `app/config.py` | Pydantic Settings | 换模型只改这里 |
| `app/state.py` | 分层 State 定义 | 工作流唯一数据总线 |
| `app/graph/builder.py` | LangGraph 组装 | 改流程只改这里 |
| `app/graph/nodes/` | 节点工厂 | 每个节点都接收注入的 gateway |
| `app/llm/gateway.py` | 模型网关 | **所有 LLM 调用唯一入口** |
| `app/llm/router.py` | 成本感知路由 | 简单任务不烧大模型 |
| `app/llm/fakes.py` | 离线替身 | 测试/评测不花钱的秘密 |
| `app/schema/wrappers.py` | 结构化输出包装类 | XxxSet 约定 + strict schema |
| `app/utils/extractor.py` | 通用解包 | LLM 输出再野也能安全取出 |
| `app/observability/` | LangFuse 接入 | 可选、零依赖退化 |
| `app/eval/` | 评测集与跑分 | 质量是回归出来的 |

## 环境变量

全部变量见 `.env.example`，常用项：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 默认供应商密钥（flash/pro 档） |
| `DEEPSEEK_API_KEY` | 跨供应商兜底（backup 档） |
| `APP_MODELS__FLASH__MODEL_ID` | 覆盖某个模型别名（如换成 `qwen-turbo`） |
| `APP_GATEWAY_MAX_RETRIES` | 单模型重试次数（默认 2） |
| `LANGFUSE_ENABLED` | `true` 时自动全链路埋线（需装 `.[observability]`） |

## 测试哲学

- `tests/` 全部离线：`FakeGateway` / `ScriptedClient` 替身注入，覆盖快乐路径与「LLM 全面宕机」路径；
- `app/eval/` 是活的评测集：`--mock` 验证管道连通性（CI 冒烟），
  真实模式（配好 Key 后直接运行）按关键词命中率与数量门槛做质量门禁，
  跑分结果写入 `eval_results/report.md` 便于回归对比。

## 容器化

```bash
docker build -t {{ project_name }} .
docker run -p 8000:8000 --env-file .env {{ project_name }}

# 可选：自托管 LangFuse 观测栈（Postgres + LangFuse）
docker compose --profile observability up -d
```

## License

MIT
