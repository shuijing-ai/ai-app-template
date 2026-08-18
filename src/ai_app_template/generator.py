"""模板渲染与项目生成。

设计原则（刻意保持简单，教学友好）：
- 不引入 Jinja2 —— 占位符只有 ``{{ key }}`` 一种形态，用 ``str.replace`` 渲染，
  模板文件本身永远是合法的 Python/TOML/YAML，可以直接做语法校验；
- ``base`` 是全量骨架，各变体目录在其上做文件级覆盖叠加（同名文件直接替换）。
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"

# 这些扩展名 / 文件名按文本渲染；其余按二进制原样复制
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".json",
    ".cfg",
    ".ini",
    ".example",
}
TEXT_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore"}

NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,49}$")
RESERVED_NAMES = {"app", "tests", "src", "ai_app_template", "ai-app-template", "site-packages"}

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

# 变体目录里的控制文件，不进入生成结果
CONTROL_NAMES = {"_overlay.json", "README_APPEND.md"}


class GeneratorError(Exception):
    """生成失败（名称非法 / 模板不存在 / 目标目录非空等）。"""


def validate_project_name(name: str) -> str:
    if not NAME_PATTERN.match(name):
        raise GeneratorError(
            f"项目名 {name!r} 不合法：需以字母或下划线开头，"
            "仅含字母/数字/下划线/连字符，最长 50 字符"
        )
    if name.lower() in RESERVED_NAMES:
        raise GeneratorError(f"项目名 {name!r} 是保留字，请换一个")
    return name


def build_context(
    project_name: str,
    template_id: str,
    template_title: str,
    description: str = "",
    author: str = "",
) -> dict[str, str]:
    from datetime import date

    return {
        "project_name": project_name,
        "project_slug": project_name.replace("-", "_").lower(),
        "template_id": template_id,
        "template_title": template_title,
        "description": description or f"基于 ai-app-template {template_title} 模板生成的 AI 应用",
        "author": author or "Your Name",
        "year": str(date.today().year),
    }


def _is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES


def _render(text: str, ctx: dict[str, str]) -> str:
    for key, value in ctx.items():
        text = text.replace("{{ " + key + " }}", value).replace("{{" + key + "}}", value)
    return text


def _copy_tree(src: Path, dst: Path, ctx: dict[str, str], written: list[Path]) -> None:
    for path in sorted(src.rglob("*")):
        if path.is_dir() or path.name in CONTROL_NAMES:
            continue
        rel = path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if _is_text_file(path):
            target.write_text(_render(path.read_text(encoding="utf-8"), ctx), encoding="utf-8")
        else:
            target.write_bytes(path.read_bytes())
        written.append(target)


def generate(target_dir: Path, template_id: str, ctx: dict[str, str]) -> list[Path]:
    """把 base + 变体叠加渲染到 target_dir，返回写入的文件列表。

    变体目录可包含两个特殊文件（不进入生成结果）：
    - ``_overlay.json``：{"exclude": [...]} 声明 base 中被本变体废弃的文件；
    - ``README_APPEND.md``：内容追加到生成项目 README 末尾。
    """
    base_dir = TEMPLATES_DIR / "base"
    variant_dir = TEMPLATES_DIR / template_id
    if template_id != "base" and not variant_dir.is_dir():
        raise GeneratorError(f"未知模板: {template_id!r}")

    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    _copy_tree(base_dir, target_dir, ctx, written)

    if variant_dir.is_dir():
        manifest_path = variant_dir / "_overlay.json"
        if manifest_path.is_file():
            import json

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for rel in manifest.get("exclude", []):
                victim = target_dir / rel
                if victim.is_file():
                    victim.unlink()
                    written.remove(victim)

        _copy_tree(variant_dir, target_dir, ctx, written)

        append_path = variant_dir / "README_APPEND.md"
        if append_path.is_file():
            appended = "\n" + _render(append_path.read_text(encoding="utf-8"), ctx).lstrip()
            readme = target_dir / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + appended, encoding="utf-8")
    return written


def assert_fully_rendered(target_dir: Path) -> list[Path]:
    """校验目录内所有文本文件都不残留占位符（测试用）。"""
    leftovers: list[Path] = []
    for path in target_dir.rglob("*"):
        if (
            path.is_file()
            and _is_text_file(path)
            and PLACEHOLDER_RE.search(path.read_text(encoding="utf-8"))
        ):
            leftovers.append(path)
    return leftovers
