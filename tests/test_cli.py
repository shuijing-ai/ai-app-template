"""CLI 端到端测试（typer.testing.CliRunner，全离线）。"""

from __future__ import annotations

from typer.testing import CliRunner

from ai_app_template.cli import app
from ai_app_template.registry import TEMPLATES

runner = CliRunner()


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "create" in result.output and "list" in result.output


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ai-app-template" in result.output


def test_list_shows_all_templates():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    for template_id in TEMPLATES:
        assert template_id in result.output


def test_create_non_interactive_requires_template(tmp_path):
    result = runner.invoke(app, ["create", "demo", "--path", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "--template" in result.output


def test_create_rejects_unknown_template(tmp_path):
    result = runner.invoke(app, ["create", "demo", "-t", "nope", "--path", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "未知模板" in result.output


def test_create_rejects_invalid_name(tmp_path):
    result = runner.invoke(
        app, ["create", "1bad-name", "-t", "review-flow", "--path", str(tmp_path), "--yes"]
    )
    assert result.exit_code == 1
    assert "不合法" in result.output


def test_create_generates_project(tmp_path):
    result = runner.invoke(
        app, ["create", "demo-app", "-t", "rag-agent", "--path", str(tmp_path), "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo-app" / "app" / "retrieval" / "store.py").is_file()
    assert "下一步" in result.output


def test_create_refuses_non_empty_dir(tmp_path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "keep.txt").write_text("do not touch", encoding="utf-8")
    result = runner.invoke(
        app, ["create", "demo", "-t", "review-flow", "--path", str(tmp_path), "--yes"]
    )
    assert result.exit_code == 1
    assert (target / "keep.txt").read_text(encoding="utf-8") == "do not touch"


def test_create_force_overwrites(tmp_path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    result = runner.invoke(
        app, ["create", "demo", "-t", "review-flow", "--path", str(tmp_path), "--yes", "--force"]
    )
    assert result.exit_code == 0, result.output
    assert not (target / "old.txt").exists()  # --force 清空重建
    assert (target / "pyproject.toml").is_file()


def test_console_script_entry_point():
    """回归测试：入口点必须指向可调用的 app 对象（曾错指向无输出的回调函数）。

    直接在当前解释器的 Scripts/bin 目录里定位二进制——不依赖 PATH，
    本地 venv 与 CI 都能真正执行到安装产物本身。
    """
    import subprocess
    import sys
    from pathlib import Path

    bin_dir = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
    candidates = [bin_dir / "ai-app-template.exe", bin_dir / "ai-app-template"]
    executable = next((p for p in candidates if p.is_file()), None)
    if executable is None:  # 未以可编辑模式安装的环境（如 tox 隔离）下跳过
        import pytest

        pytest.skip(f"未在 {bin_dir} 找到 ai-app-template 控制台脚本")

    result = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "ai-app-template" in result.stdout


def test_pick_template_interactively(monkeypatch, capsys):
    """回归测试：交互式选择必须返回合法模板 ID。

    曾因命令函数命名 ``def list`` 遮蔽内建 ``list()``，导致
    ``ids = list(TEMPLATES)`` 实际执行了 typer 命令并拿到 None，
    交互式创建在 ``enumerate(None)`` 处崩溃（非交互路径无此问题，
    所以当时的测试全部通过）。本测试直接覆盖交互路径。
    """
    import builtins

    import typer

    import ai_app_template.cli as cli_mod

    # 模块里不允许再出现遮蔽内建 list 的名字
    assert getattr(cli_mod, "list", builtins.list) is builtins.list

    monkeypatch.setattr(typer, "prompt", lambda *args, **kwargs: 2)
    assert cli_mod._pick_template_interactively() == "rag-agent"

    monkeypatch.setattr(typer, "prompt", lambda *args, **kwargs: 1)
    assert cli_mod._pick_template_interactively() == "review-flow"

    # 同时确认交互菜单真的打印了模板行（而非静默通过）
    out = capsys.readouterr().out
    assert "review-flow" in out
