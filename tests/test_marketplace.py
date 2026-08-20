"""模板市场测试：引用解析、本地 git 仓库拉取生成、结构校验。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_app_template.cli import app
from ai_app_template.generator import assert_fully_rendered, build_context, generate
from ai_app_template.marketplace import (
    MarketplaceError,
    fetched_template,
    is_remote_template,
    parse_ref,
)

runner = CliRunner()


def make_template_repo(base: Path, name: str = "repo") -> Path:
    """构造一个合法的第三方模板 git 仓库（含清单/覆盖/废弃声明/README 追加）。"""
    repo = base / name
    (repo / "app" / "graph" / "nodes").mkdir(parents=True)
    (repo / "app" / "graph" / "nodes" / "echo_node.py").write_text(
        '"""第三方示例节点。"""\n', encoding="utf-8"
    )
    (repo / "template.json").write_text(
        json.dumps(
            {"id": "mini", "title": "迷你模板", "description": "第三方测试模板"}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    (repo / "_overlay.json").write_text(
        json.dumps({"exclude": ["app/graph/nodes/summary_node.py"]}), encoding="utf-8"
    )
    (repo / "README_APPEND.md").write_text("## 第三方说明：{{ project_name }}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def test_parse_ref_variants():
    assert parse_ref("git+https://x/y.git") == ("https://x/y.git", None)
    assert parse_ref("https://x/y.git#sub/dir") == ("https://x/y.git", "sub/dir")
    assert parse_ref("git@github.com:o/r.git") == ("git@github.com:o/r.git", None)
    assert parse_ref("C:/local/repo") == ("C:/local/repo", None)


def test_is_remote_template(tmp_path):
    assert is_remote_template("git+https://x/y.git")
    assert is_remote_template("https://x/y.git#sub")
    assert not is_remote_template("review-flow")

    local_git = make_template_repo(tmp_path)
    assert is_remote_template(str(local_git))


def test_fetch_validates_structure(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=plain, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", "--allow-empty"],
        cwd=plain,
        check=True,
    )
    with (
        pytest.raises(MarketplaceError, match="不像一个变体模板"),
        fetched_template(str(plain)),
    ):
        pass


def test_generate_from_remote_template(tmp_path):
    repo = make_template_repo(tmp_path)
    target = tmp_path / "proj"

    with fetched_template(str(repo)) as (variant_dir, manifest):
        assert manifest["id"] == "mini"
        ctx = build_context("my-app", manifest["id"], manifest["title"], manifest["description"])
        written = generate(target, manifest["id"], ctx, variant_dir=variant_dir)

    assert written
    assert (target / "app" / "graph" / "nodes" / "echo_node.py").is_file()  # 覆盖文件进来了
    assert not (target / "app" / "graph" / "nodes" / "summary_node.py").exists()  # 废弃清单生效
    assert "第三方说明：my-app" in (target / "README.md").read_text(encoding="utf-8")  # 追加段渲染
    assert assert_fully_rendered(target) == []


def test_cli_create_from_remote_template(tmp_path):
    repo = make_template_repo(tmp_path)
    result = runner.invoke(
        app,
        ["create", "mkt-app", "-t", str(repo), "--path", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "mkt-app" / "app" / "graph" / "nodes" / "echo_node.py").is_file()
    assert not (tmp_path / "mkt-app" / "app" / "graph" / "nodes" / "summary_node.py").exists()


def test_cli_create_remote_subdir(tmp_path):
    repo = make_template_repo(tmp_path, name="outer")
    sub = repo / "tpl"
    sub.mkdir()
    for item in ("template.json", "_overlay.json", "README_APPEND.md"):
        (repo / item).rename(sub / item)
    (sub / "app").mkdir()
    (sub / "app" / "extra.py").write_text("X = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "sub"],
        cwd=repo,
        check=True,
    )

    result = runner.invoke(
        app,
        ["create", "sub-app", "-t", f"{repo}#tpl", "--path", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sub-app" / "app" / "extra.py").is_file()
