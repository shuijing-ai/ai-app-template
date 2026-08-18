<div align="center">

# ai-app-template

**一键生成生产级 AI 应用项目骨架**

内置模型网关 · 降级兜底 · 成本路由 · 可观测性 · 自动化评测

[![CI](https://github.com/shuijing-ai/ai-app-template/actions/workflows/ci.yml/badge.svg)](https://github.com/shuijing-ai/ai-app-template/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)

**简体中文** | [English](README.en.md)

</div>

---

## 为什么是 ai-app-template

现有的 AI 应用模板大多是「静态仓库，`git clone` 之后自己慢慢改」。ai-app-template 是**交互式 CLI 脚手架**，一条命令生成一个工程规范在线、离线可测、可直接部署的项目，并且每个模块都配了中文教学文档：

- **形态**：一条命令生成完整项目，而不是一堆要自己搬的文件
- **能力组合**：成本路由 + 降级兜底 + 结构化输出体系 + 自动化评测，一次配齐
- **离线全绿**：生成的项目 `pytest -q` 不需要任何 API Key —— Fake 网关 + 脚本化客户端是模板的一部分
- **教学导向**：`docs/tutorials/` 八篇教程把每个模块的设计取舍讲透，直接可用于面试与授课

## 快速开始

```bash
# 从源码安装（首次发布 PyPI 后可 pip install ai-app-template）
pip install -e .
ai-app-template list                     # 查看内置模板
ai-app-template create my-app            # 交互式创建
ai-app-template create my-app -t rag-agent --yes   # 非交互（脚本/CI）
```

生成之后（以 `my-app` 为例）：

```bash
cd my-app
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env         # 填入你的 API Key
pytest -q                    # 离线全绿，不花一分钱
uvicorn app.main:app --reload
python -m app.eval.run_eval --mock   # 一键跑评测集
```

## 内置模板

| 模板 | 图结构 | 适合 |
| --- | --- | --- |
| `review-flow`（默认） | `parse -> extract ->(重试) review -> summary` | 入门、文档审阅类应用 |
| `rag-agent` | `retrieve -> generate(citations) -> verify` | 知识库问答，自带确定性引用校验 |
| `multi-agent` | `supervisor -> researcher/writer/critic 循环` | Supervisor 模式多智能体协作 |

## 生成项目内置的工程化能力

| 能力 | 实现 | 一句话记忆 |
| --- | --- | --- |
| 模型网关 | `app/llm/gateway.py`：指数退避重试 + 每模型熔断 + 跨供应商降级链 | 所有 LLM 调用的唯一入口 |
| 成本路由 | `app/llm/router.py`：任务/长度/结构化要求 -> light/standard/heavy | 简单任务不烧大模型 |
| 结构化输出 | `app/schema/wrappers.py`：XxxSet 约定 + strict json_schema | 模型端保证合法 JSON |
| 通用解包 | `app/utils/extractor.py`：围栏/裸串/裸列表统一安全解包 | 永不抛异常 |
| 可观测性 | `GatewayStats` + 可选 LangFuse（客户端类替换式接入，零侵入） | token/成本/耗时全记录 |
| 自动化评测 | `app/eval/`：评测集 + 一键跑分 + CI 质量门禁（退出码） | 质量是回归出来的 |
| 弹性兜底 | 每个节点都有降级路径；LLM 全挂工作流照常返回 | LLM 增强，而非 LLM 依赖 |
| 容器化 | Dockerfile + docker-compose（可选自托管 LangFuse 栈） | 一条命令起依赖 |

## 文档

- [docs/architecture.md](docs/architecture.md) —— 整体架构与关键设计决策（ADR）
- [docs/design-review.md](docs/design-review.md) —— 对初版方案的审查与优化记录
- [docs/tutorials/](docs/tutorials/) —— **八篇中文教程**（从 CLI 实现到面试话术）
- [docs/publishing.md](docs/publishing.md) —— 发布到 GitHub / PyPI / 掘金 / B 站的操作指南

## 开发本仓库

```bash
pip install -e ".[dev]"
pytest -q          # 仓库测试（含三模板的生成/渲染/编译校验）
ruff check src tests
make demo          # 本地生成一个演示项目体验 CLI
```

新增模板见 [CONTRIBUTING.md](CONTRIBUTING.md) 的三步指南。

## 路线图

- [ ] 发布 PyPI（`pip install ai-app-template`）
- [ ] `ai-app-template doctor`：环境体检（Python 版本 / API Key / 端口占用）
- [ ] 第四个模板：`voice-flow`（语音转写 -> 摘要 -> 待办抽取）
- [ ] 模板市场：从任意 git 仓库安装第三方模板
- [ ] 英文完整文档

## License

[MIT](LICENSE)
