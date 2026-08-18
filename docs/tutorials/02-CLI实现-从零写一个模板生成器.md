# 02 · CLI 实现：从零写一个模板生成器

> 目标：读懂 `src/ai_app_template/` 下约 400 行代码，学会用 typer 写 CLI、
> 用「叠加渲染」实现模板系统，并知道如何发布到 PyPI。
> 代码走读对象：`cli.py`、`generator.py`、`registry.py`、`pyproject.toml`。

## 1. typer 最小心智模型

typer 把「命令」建模为「函数」，把「参数」建模为「类型标注」：

```python
app = typer.Typer()

@app.command()
def create(
    name: str = typer.Argument(...),                    # 位置参数
    template: str = typer.Option(None, "--template", "-t"),  # 选项
    yes: bool = typer.Option(False, "--yes", "-y"),     # 开关
) -> None: ...
```

`typer.Argument(...)` 的 `...` 表示必填；`Option(None)` 表示可选、默认 None。
错误处理统一走 `typer.Exit(code=1)`——比 `sys.exit` 好在能被 CliRunner 测试捕获。

**交互与非交互的分叉点**（cli.py 的关键四行）：

```python
if template is None:
    if sys.stdin.isatty() and not yes:      # 真终端且未跳过 → 交互选择
        template = _pick_template_interactively()
    else:                                   # 脚本/CI → 报错并提示 --template
        _fail("非交互环境请用 --template 指定模板")
```

这是所有 CLI 工具的通用模式：**交互是增值，永远不是必经之路**。

## 2. 生成器：叠加 + 渲染 + 废弃清单

`generator.py` 只做三件事：

### 2.1 复制即渲染

```python
def _copy_tree(src, dst, ctx, written):
    for path in sorted(src.rglob("*")):
        ...
        if _is_text_file(path):
            target.write_text(_render(path.read_text(...), ctx), ...)
```

文本文件边复制边把 `{{ project_name }}` 替换成真实值，二进制原样复制。
不用 Jinja2 的理由见 ADR-6：模板文件保持「始终是合法源码」，
仓库测试才能对生成的每个 `.py` 直接 `compile()` 校验。

### 2.2 base + 变体叠加

```python
_copy_tree(base_dir, target_dir, ctx, written)     # 全量骨架
if variant_dir.is_dir():
    _copy_tree(variant_dir, target_dir, ctx, written)  # 同名覆盖
```

rag-agent 只需要维护与 base 的**差异**（约 17 个文件），
而不是全量复制 40+ 个文件。骨架修 bug，三个变体同时受益。

### 2.3 废弃清单 _overlay.json

rag 模板不需要 review-flow 的四个节点，变体目录里放：

```json
{"exclude": ["app/graph/nodes/parse_node.py", ...]}
```

生成器据此删除 base 复制过来的文件。没有这个机制，
生成的项目里会躺着永远不会被 import 的死代码。

## 3. 注册表驱动的可扩展性

`registry.py` 用一个 dict 描述全部模板元信息，`list` 命令、交互选择、
create 校验全部从这份数据派生——**新增模板零改 CLI 代码**。
这是「数据驱动配置」的最小案例：代码读数据，而不是代码堆分支。

## 4. 打包：pyproject.toml 里最关键的五行

```toml
[project.scripts]
ai-app-template = "ai_app_template.cli:app"     # 注意指向 app 对象（ADR-10 的教训）

[tool.hatch.build.targets.wheel]
packages = ["src/ai_app_template"]           # src 布局：模板随包一起分发
```

templates 目录没有 `__init__.py` 也行——hatchling 会把包目录下的
**全部文件**（包括数据文件）打进 wheel。安装后
`Path(__file__).parent / "templates"` 即模板根。

> 曾把入口写成 `cli:main`，而 `main` 是 typer 回调函数——CLI 静默退出 0。
> 现在 `tests/test_cli.py::test_console_script_entry_point` 用子进程调用
> 真实二进制防止回归。**包装层必须有端到端测试。**

## 5. 动手练习

1. 给 CLI 加 `ai-app-template info <template_id>` 命令：输出注册表里该模板的
   全部字段（约 15 行，参考 `list --detailed`）。
2. 新增 `--no-git-check` 之外的任意一个你自己想要的选项，并补一条测试。
3. 进阶：让 `_render` 支持 `{{ now }}`（生成日期），思考：这会让模板
   「不可重制」吗？同一输入两次生成结果不同是好是坏？

## 6. 自测题

1. 为什么交互式提示要同时判断 `sys.stdin.isatty()` 和 `--yes`？
2. `_overlay.json` 解决什么问题？不用它会有什么残留？
3. 入口点 `cli:app` 与 `cli:main` 的差别曾在什么层面爆炸？（不是 import 错误）
4. 模板里的 `{{ project_name }}` 出现在 `.py` 文件中，为什么编译校验不会失败？

下一篇：[03 模型网关——重试、降级、熔断](03-模型网关-重试降级熔断.md)。
