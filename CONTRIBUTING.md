# 贡献指南

感谢你愿意贡献！本项目规模刻意保持克制，请先读 [架构决策](docs/architecture.md)，
尤其是 ADR-3（薄依赖）与 ADR-5（离线全绿）——它们是所有 PR 的底线。

## 开发环境

```bash
git clone https://github.com/shuijing-ai/ai-app-template.git
cd ai-app-template
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"
pytest -q && ruff check src tests
```

## 提交前检查

```bash
ruff format src tests   # 格式化
ruff check src tests    # 静态检查
pytest -q               # 全部测试（必须全绿，离线运行）
```

CI（GitHub Actions）会跑同样内容：ruff + pytest，Python 3.10–3.12 双系统。

## 新增一个模板：三步

1. 建目录 `src/ai_app_template/templates/<template-id>/`，只放与 base 的**差异文件**
   （同名覆盖 base；被淘汰的 base 文件写进 `_overlay.json` 的 `exclude`；
   追加说明写 `README_APPEND.md`——参考 `rag-agent/`）
2. 在 `src/ai_app_template/registry.py` 注册元信息（id/title/description/graph_shape）
3. 在 `tests/test_generator.py` 的 `VARIANT_SPECIFIC` / `VARIANT_EXCLUDED`
   加上你的模板，断言关键文件存在/已排除

要求：生成项目 `pytest -q` 与 `python -m app.eval.run_eval --mock` 离线全绿，
所有 `.py` 可编译（生成器测试会自动校验）。

## 修改 base 模板时

改的是所有模板的公共骨架——跑一遍三模板的完整验收：

```bash
for t in review-flow rag-agent multi-agent; do
  .venv/bin/ai-app-template create /tmp/check-$t -t $t --yes
  (cd /tmp/check-$t && pytest -q)
done
```

## 提交信息规范

Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`。
示例：`feat(gateway): add success_rate to GatewayStats`。

中文描述完全可以（本项目文档以中文为主），但类型前缀保留英文以便工具识别。

## Issue 与 PR

- Bug 请附：命令、完整输出、Python 版本、OS
- 功能建议先开 issue 讨论再写代码（避免与路线图冲突）
- PR 描述里写清楚「改了什么、为什么、怎么验证的」

## 行为准则

保持友善与具体。对事不对人，代码评审聚焦设计取舍与证据。
