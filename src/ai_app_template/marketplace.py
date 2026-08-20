"""模板市场：从任意 git 仓库安装第三方模板。

约定（刻意保持极简，见 README「模板市场」）：
- 仓库根目录（或 `#子目录` 片段指定的目录）即一个「变体模板」：
  与内置变体同构——只放差异文件（同名覆盖 base），可选 `_overlay.json`
  声明废弃文件、`README_APPEND.md` 追加说明、`template.json` 清单
  （{"id","title","description"}，缺省用目录名）；
- `git clone --depth 1` 拉取后按普通文件复制渲染，**不执行仓库中任何代码**；
- 但内容会进入你的项目，请只安装可信来源的模板。
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

MARKER_FILES = ("app", "_overlay.json", "README_APPEND.md")

REMOTE_PREFIXES = ("git+", "https://", "http://", "git@", "ssh://")


class MarketplaceError(Exception):
    """模板拉取/校验失败。"""


def is_remote_template(ref: str) -> bool:
    """判断 --template 的值是模板市场引用（远端 URL / git 引用 / 本地 git 仓库路径）。"""
    if ref.startswith(REMOTE_PREFIXES):
        return True
    base, _ = parse_ref(ref)  # 先剥离 #子目录 片段再判断路径
    path = Path(base)
    return path.suffix == ".git" or (path.is_dir() and (path / ".git").exists())


def parse_ref(ref: str) -> tuple[str, str | None]:
    """拆出 (git 地址, 子目录)。支持 git+URL、URL#subdir、本地路径。"""
    url = ref[4:] if ref.startswith("git+") else ref
    subdir = None
    if "#" in url:
        url, subdir = url.split("#", 1)
        subdir = subdir.strip("/") or None
    return url, subdir


def _clone(url: str, dest: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketplaceError(f"无法执行 git clone（git 可用吗？）：{exc}") from None
    if result.returncode != 0:
        hint = (result.stderr or "").strip().splitlines()
        raise MarketplaceError(f"git clone 失败：{hint[-1] if hint else '未知错误'}") from None


def _validate(variant: Path) -> None:
    if not variant.is_dir():
        raise MarketplaceError(f"子目录不存在：{variant}")
    if not any((variant / marker).exists() for marker in MARKER_FILES):
        raise MarketplaceError(
            "该目录不像一个变体模板（需包含 app/ 覆盖文件、_overlay.json "
            "或 README_APPEND.md 之一）。约定见 README「模板市场」。"
        )


def load_manifest(variant: Path) -> dict:
    manifest_path = variant / "template.json"
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"template.json 不是合法 JSON：{exc}") from None


@contextmanager
def fetched_template(ref: str):
    """拉取并校验第三方模板，yield (变体目录, 清单)；退出时自动清理临时目录。"""
    url, subdir = parse_ref(ref)
    with tempfile.TemporaryDirectory(prefix="ai-app-template-market-") as tmp:
        repo_dir = Path(tmp) / "repo"
        console_hint = re.sub(r"#\S+$", "", ref)
        print(f"正在拉取第三方模板：{console_hint} ...")
        _clone(url, repo_dir)
        variant = repo_dir / subdir if subdir else repo_dir
        _validate(variant)
        yield variant, load_manifest(variant)
