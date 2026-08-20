# Changelog

本项目的显著变更记录在此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-08-18

首个公开版本。

### 新增

- CLI：`ai-app-template create`（交互式 + `--template/--yes` 非交互）、`ai-app-template list`
- 模板系统：base 全量骨架 + 变体文件级叠加 + `_overlay.json` 废弃清单 +
  README 追加段；`str.replace` 渲染保持模板始终为合法源码
- 三个内置模板：
  - `review-flow`：parse → extract（条件边重试）→ review → summary，
    每节点均有降级路径
  - `rag-agent`：纯 Python TF-IDF 检索 + 带引用生成 + 确定性引用校验
    （伪造引用剔除并带因重试）
  - `multi-agent`：Supervisor 动态路由 researcher/writer/critic，
    轮次预算强制收尾
- 模型网关：指数退避重试（含抖动与上限）、每模型熔断器（closed/open/half-open）、
  跨供应商降级链、成本/token 统计（1e-6 美元精度）
- 成本感知路由：任务类型 + 输入长度 + 结构化要求 → light/standard/heavy，
  决策带可解释 reasons
- 结构化输出：XxxSet 约定、strict json_schema 适配、
  `safe_extract_items` 统一安全解包（永不抛异常）
- 可观测性：LangFuse 客户端类替换式零侵入接入（可选）、
  JSON 结构化日志、`/health` 暴露网关统计与熔断状态
- 自动化评测：评测集 + 一键跑分 + 双门槛（mock 验管道 / live 验质量）+
  CI 退出码门禁 + Markdown 报告
- 离线测试体系：节点级 FakeGateway（输入感知）与 SDK 级 ScriptedClient
  两层替身；生成项目零 API Key 全绿
- 自动评测集生成与回退门禁（auto-eval P0+P1+P2，三模板）：
  - 身份卡（`app/eval/identity.json`）唯一输入，`gen_cases` 走模型网关
    按 11 类边界/异常/对抗分类矩阵生成用例，经确定性校验（关键词逐字
    在输入中、sub_kind 语义约束、批内去重）后固化到 `app/eval/generated/`
  - `run_eval --suite {all|seed|happy|boundary|anomaly|adversarial}` 套件化跑分；
    `--set-baseline` 签字固化质量线；live 跑分自动对比基线并输出
    pass/rollback/warn/improve 结论（总分容差 5pp、非焦点套件 10pp 回退线、
    焦点套件 15pp 警告线），建议回退时退出码 1 可直接当 CI 门禁
  - `--suggest` 读 git 变更按影响映射给出该跑套件的建议；
    `--runs N` 多次采样（逐用例多数决 + 命中率中位数）抑制 live 波动；
    生成项目自带 GitHub Actions（pytest + mock 冒烟 + suggest 输出）
- 工程配套：Dockerfile、docker-compose（可选观测栈 profile）、
  GitHub Actions CI（ruff + pytest，3.10–3.12 双 OS）、九篇中文教程、
  架构决策记录（ADR×10）、设计审查与发布指南

### 修复

- 交互式创建崩溃：CLI 命令函数 `def list` 遮蔽了内建 `list()`，
  导致 `_pick_template_interactively` 中 `ids = list(TEMPLATES)`
  实际执行了 typer 命令并得到 `None`，在 `enumerate(None)` 处抛出
  `TypeError: 'NoneType' object is not iterable`。命令函数已改名
  `list_templates` 并通过 `@app.command("list")` 保持命令名不变；
  新增交互路径回归测试（此前所有测试均走非交互分支，故未覆盖）。
