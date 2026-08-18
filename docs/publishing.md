# 发布指南：GitHub / PyPI / 内容平台

把仓库变成「看起来就专业」的开源项目，剩余动作按本清单执行。

## 0. 发布前必改项（5 分钟）

- 全局搜索 `shuijing-ai`，替换为你的 GitHub 用户名
  （出现于 README 徽章、`pyproject.toml` 的 Homepage/Documentation 链接、
  base 模板 README 里的脚手架链接）
- 确认 `pyproject.toml` 中 `authors` 填你的名字
- 确认 LICENSE 中版权行（base 模板的 LICENSE 会用生成时的 `{{ author }}`
  与 `{{ year }}` 自动填充；本仓库 LICENSE 需手改一次）

## 1. GitHub

```bash
cd ai-app-template
git add -A && git commit -m "feat: initial release of ai-app-template 0.1.0"
gh repo create ai-app-template --public --source=. --push
# 没有 gh CLI：在网页建仓后 git remote add origin <url> && git push -u origin main
```

仓库设置建议：

| 项 | 建议值 |
| --- | --- |
| Description | 一键生成生产级 AI 应用骨架：模型网关 · 降级兜底 · 成本路由 · 可观测 · 评测 |
| Topics | `llm` `agent` `langgraph` `scaffold` `cli` `fastapi` `rag` `template` `chatgpt` `observability` |
| Branches | 保护 main：要求 CI 通过 + 1 approval（仓库小也可先只开 CI 检查） |
| Settings → General | 勾选 Discussions（教程答疑区）、Releases |

CI 已就绪（`.github/workflows/ci.yml`：ruff + pytest，3.10–3.12 双 OS）。
首次 push 后确认徽章变绿，替换 README 中徽章 URL 的 `shuijing-ai`。

打第一个 release：

```bash
git tag -a v0.1.0 -m "ai-app-template 0.1.0: three templates, offline-green tests"
git push origin v0.1.0
# Releases → Draft new release → 选 tag → 贴 CHANGELOG 内容
```

### 加分项（按性价比排序）

1. **演示 GIF**：`ai-app-template list` + `create` + `pytest 全绿` 录 15 秒
   （Windows 可用 ScreenToGif），贴在 README 快速开始之前
2. **英文教程翻译**：README.en.md 已就位，下一步是把八篇教程中的
   03/06 两篇（网关/测试）翻成英文放 `docs/tutorials-en/`
3. **Discussions 置顶**：学习路线帖 + 「用 ai-app-template 做了什么」展示帖

## 2. PyPI

发布前先确认包名可用（`pip index versions ai-app-template` 或网页搜索；
若被占用，备选 `ai-app-template-cli` / `aiappt`，改动 `pyproject.toml` 一处即可）。

```bash
pip install build twine
python -m build                    # 产出 dist/*.whl 与 *.tar.gz
twine check dist/*                 # 元数据校验
twine upload dist/*                # 需要 PyPI API Token
```

验证：干净的虚拟环境里 `pip install ai-app-template && ai-app-template --version`。

更专业的姿势是 **Trusted Publishing**（GitHub Actions 直接发布，无 token）：
在 PyPI 创建 project → Publishing 绑定仓库与 workflow `pypi.yml`，
然后加一个 release 触发的 workflow 调 `pypa/gh-action-pypi-publish`。

发布后更新 README 安装命令为 `pip install ai-app-template`，
并在教程 02 补一行「已发布」。

## 3. 内容平台（获客漏斗）

### 掘金系列（对应八篇教程）

| 顺序 | 标题建议 | 引流钩子 |
| --- | --- | --- |
| 1 | 我写了一个 AI 应用脚手架：一条命令生成生产级项目骨架 | 市场分析 + GIF |
| 2 | LLM 应用的模型网关：重试、降级、熔断的 300 行实现 | 教程 03 |
| 3 | 如何离线测试 LLM 应用：两层替身设计 | 教程 06 替身部分 |
| 4 | RAG 落地最大的坑是编造引用，我用 30 行代码治好了它 | verify_node |
| 5 | 会结束的多智能体才是能上线的多智能体 | 轮次预算 |

每篇末尾固定版欄件：「本文是 ai-app-template 系列第 N 篇，项目开源于此 ↗」。

### B 站（5 分钟 demo）

脚本直接用教程 07 的 demo 流程；标题参考
「一条命令生成生产级 AI 应用【开源脚手架】」；置顶评论放仓库链接。

### 节奏建议

GitHub README 绿了 → 掘金第 1 篇 → B 站 demo → 其余篇目每周 1-2 篇。
教程文档就在仓库里，写作成本≈排版成本。

## 4. 发布检查单

- [ ] 徽章 URL 指向 `shuijing-ai/ai-app-template` 且为绿
- [ ] `pip install -e ".[dev]" && pytest && ruff check src tests` 本地全绿
- [ ] `ai-app-template create tmp-demo -t review-flow --yes` 生成后 `pytest -q` 全绿
- [ ] LICENSE 版权行、pyproject authors 已是本人信息（已配置：任慧荣）
- [ ] tag v0.1.0 + GitHub Release 已发
- [ ] PyPI 包名确认 / 已发布（可选，之后补也行）
- [ ] 掘金首篇 + B 站 demo 已排期
