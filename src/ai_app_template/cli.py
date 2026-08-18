"""ai-app-template 命令行入口。

用法：
    ai-app-template create my-app                      # 交互式
    ai-app-template create my-app -t rag-agent --yes   # 非交互（脚本/CI 友好）
    ai-app-template list                               # 查看内置模板
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_app_template import __version__
from ai_app_template.generator import (
    GeneratorError,
    build_context,
    generate,
    validate_project_name,
)
from ai_app_template.registry import TEMPLATES

app = typer.Typer(
    name="ai-app-template",
    help="一键生成生产级 AI 应用项目骨架：模型网关、降级兜底、成本路由、可观测性、自动化评测。",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
console = Console()


def _fail(message: str) -> None:
    console.print(f"[bold red]错误:[/bold red] {message}")
    raise typer.Exit(code=1)


def _pick_template_interactively() -> str:
    ids = list(TEMPLATES)
    console.print("[bold]可选模板：[/bold]")
    for i, tid in enumerate(ids, 1):
        info = TEMPLATES[tid]
        console.print(f"  {i}. [cyan]{tid}[/cyan] — {info.title}")
    choice = typer.prompt("选择模板编号", type=int, default=1)
    if not 1 <= choice <= len(ids):
        _fail(f"编号需在 1-{len(ids)} 之间")
    return ids[choice - 1]


def _next_steps(path: Path) -> Panel:
    on_windows = sys.platform == "win32"
    if on_windows:
        activate = r".\.venv\Scripts\activate"
        copy_env = r"copy .env.example .env"
    else:
        activate = "source .venv/bin/activate"
        copy_env = "cp .env.example .env"
    lines = [
        f"[bold cyan]cd {path.name}[/bold cyan]",
        f"python -m venv .venv && {activate}",
        'pip install -e ".[dev]"',
        copy_env + "   # 填入你的 API Key",
        "[green]pytest -q[/green]   # 全部离线运行，无需任何 API Key",
        "[green]uvicorn app.main:app --reload[/green]   # 打开 http://127.0.0.1:8000/docs",
        "[green]python -m app.eval.run_eval --mock[/green]   # 离线跑评测集",
    ]
    return Panel("\n".join(lines), title="下一步", border_style="green")


@app.command()
def list(
    detailed: bool = typer.Option(False, "--detailed", help="显示模板完整说明"),
) -> None:
    """列出内置模板。"""
    table = Table(title="ai-app-template 内置模板", show_lines=detailed)
    table.add_column("ID", style="cyan")
    table.add_column("名称")
    table.add_column("图结构", style="dim")
    if detailed:
        table.add_column("说明")
    for info in TEMPLATES.values():
        row = [info.id, info.title, info.graph_shape]
        if detailed:
            row.append(info.description)
        table.add_row(*row)
    console.print(table)


@app.command()
def create(
    name: str = typer.Argument(..., help="项目名（同时作为目录名）"),
    template: str = typer.Option(
        None, "--template", "-t", help="模板 ID，见 ai-app-template list；缺省时交互式选择"
    ),
    path: Path = typer.Option(None, "--path", help="目标父目录，默认当前目录"),
    description: str = typer.Option("", help="项目一句话描述（写入 README）"),
    author: str = typer.Option("", help="作者名（写入 README 与 pyproject）"),
    force: bool = typer.Option(False, "--force", help="目标目录非空时允许清空重建"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过所有确认（非交互模式）"),
    git: bool = typer.Option(False, "--git", help="生成后执行 git init"),
) -> None:
    """生成一个生产级 AI 应用项目骨架。"""
    if template is None:
        if sys.stdin.isatty() and not yes:
            template = _pick_template_interactively()
        else:
            _fail("非交互环境请用 --template 指定模板（可选：" + "、".join(TEMPLATES) + "）")
    if template not in TEMPLATES:
        _fail(f"未知模板 {template!r}，可选：{'、'.join(TEMPLATES)}")

    try:
        validate_project_name(name)
    except GeneratorError as exc:
        _fail(str(exc))

    parent = (path or Path.cwd()).expanduser().resolve()
    target = parent / name
    if target.exists() and any(target.iterdir()):
        if not force:
            _fail(f"目标目录非空：{target}（如确认覆盖请加 --force）")
        if not yes:
            typer.confirm(f"将清空 {target} 并重建，继续吗？", abort=True)
        for child in target.iterdir():
            if child.is_dir() and not child.is_symlink():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()

    info = TEMPLATES[template]
    ctx = build_context(name, template, info.title, description, author)
    try:
        written = generate(target, template, ctx)
    except GeneratorError as exc:
        _fail(str(exc))

    if git:
        subprocess.run(["git", "init"], cwd=target, capture_output=True)

    console.print(
        Panel(
            f"[green]已生成 [bold]{len(written)}[/bold] 个文件[/green]\n"
            f"模板：[cyan]{template}[/cyan]（{info.title}）\n"
            f"位置：{target}",
            title="ai-app-template 创建成功",
            border_style="green",
        )
    )
    console.print(_next_steps(target))


def version_callback(value: bool) -> None:
    if value:
        console.print(f"ai-app-template {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True, help="显示版本号"
    ),
) -> None:
    """ai-app-template —— 生产级 AI 应用脚手架。"""


if __name__ == "__main__":
    app()
