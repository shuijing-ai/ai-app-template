"""环境体检：一条命令定位「跑不起来」的四大来源——版本/依赖/密钥/端口。

设计约束：只用标准库（sys/shutil/socket/subprocess），不依赖 gitpython 等；
被检项目不需要启动任何服务；检查项分级 ok / warn / fail——
fail 阻断（退出码 1），warn 只提示（离线测试不需要 API Key 就是典型的 warn）。
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PY_MIN = (3, 10)
KEY_RE = re.compile(r"^[A-Z0-9_]*?(API_?KEY|TOKEN|SECRET)[A-Z0-9_]*$")


@dataclass
class CheckResult:
    name: str
    status: str  # ok | warn | fail
    detail: str

    @property
    def glyph(self) -> str:
        return {"ok": "[OK]", "warn": "[警告]", "fail": "[失败]"}[self.status]


# ---- 各检查项 ----


def check_python() -> CheckResult:
    version = sys.version_info
    if version >= PY_MIN:
        return CheckResult("Python 版本", "ok", f"{version.major}.{version.minor}.{version.micro}")
    required = ".".join(map(str, PY_MIN))
    return CheckResult(
        "Python 版本", "fail", f"当前 {version.major}.{version.minor}，需 >={required}"
    )


def check_git() -> CheckResult:
    executable = shutil.which("git")
    if executable:
        return CheckResult("git", "ok", executable)
    return CheckResult("git", "warn", "未找到（--git 与第三方模板安装需要；核心生成功能不受影响）")


def check_structure(project: Path) -> CheckResult:
    has_pyproject = (project / "pyproject.toml").is_file()
    has_app = (project / "app").is_dir()
    if has_pyproject and has_app:
        return CheckResult("项目结构", "ok", "pyproject.toml + app/ 齐备")
    missing = [n for n, ok in [("pyproject.toml", has_pyproject), ("app/", has_app)] if not ok]
    return CheckResult("项目结构", "fail", f"缺少 {'、'.join(missing)}（确认目录是否为生成项目根）")


def check_venv(project: Path) -> CheckResult:
    venv = project / ".venv"
    if venv.is_dir():
        return CheckResult("虚拟环境", "ok", str(venv))
    return CheckResult(
        "虚拟环境", "warn", "未找到 .venv（python -m venv .venv 创建；不影响用其他环境安装）"
    )


def _venv_python(project: Path) -> Path | None:
    for candidate in ("Scripts/python.exe", "Scripts/python", "bin/python"):
        path = project / ".venv" / candidate
        if path.is_file():
            return path
    return None


def check_deps(project: Path) -> CheckResult:
    python = _venv_python(project)
    if python is None:
        return CheckResult(
            "项目依赖", "warn", "跳过（无 .venv；激活环境后自检 pip install -e '.[dev]'）"
        )
    probe = "import pydantic, fastapi, langgraph, openai, pydantic_settings"
    try:
        result = subprocess.run([str(python), "-c", probe], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult("项目依赖", "warn", f"探测失败：{exc}")
    if result.returncode == 0:
        return CheckResult("项目依赖", "ok", "核心依赖已安装（pydantic/fastapi/langgraph/openai）")

    stderr = (result.stderr or b"").decode("utf-8", "ignore")
    missing = sorted(
        {
            line.split("'")[-2]
            for line in stderr.splitlines()
            if "No module named" in line and "'" in line
        }
    )
    detail = f"缺少：{'、'.join(missing)}。" if missing else ""
    return CheckResult("项目依赖", "fail", f"{detail}修复：{python} -m pip install -e '.[dev]'")


def _read_env_keys(project: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    env_file = project / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            keys[key.strip()] = value.strip().strip('"').strip("'")
    return keys


def check_api_keys(project: Path) -> CheckResult:
    env_file = project / ".env"
    if not env_file.is_file():
        return CheckResult(
            "API Key", "warn", "无 .env（cp .env.example .env 后填入；离线测试不需要 Key）"
        )
    merged = {**_read_env_keys(project), **os.environ}
    placeholders = {"sk-xxxx", "pk-lf-xxxx", "sk-lf-xxxx", ""}
    provided = sorted(k for k, v in merged.items() if KEY_RE.match(k) and v not in placeholders)
    if provided:
        return CheckResult("API Key", "ok", f"已配置：{'、'.join(provided[:3])}")
    return CheckResult(
        "API Key", "warn", ".env 存在但无有效 Key（真实调用与评测需要；离线测试不需要）"
    )


def check_port(port: int) -> CheckResult:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return CheckResult(
                f"端口 {port}", "warn", "已被占用（uvicorn 无法监听；--port 换端口）"
            )
    return CheckResult(f"端口 {port}", "ok", "可用")


def check_kb(project: Path) -> CheckResult | None:
    """rag-agent 模板特有：示例知识库在位。其他模板返回 None（不展示）。"""
    if not (project / "app" / "retrieval").is_dir():
        return None
    if (project / "data" / "sample_kb.md").is_file():
        return CheckResult("知识库", "ok", "data/sample_kb.md 在位")
    return CheckResult("知识库", "warn", "缺 data/sample_kb.md（rag 检索将为空，流程仍可运行）")


# ---- 汇总 ----


def run_doctor(project: Path | None, port: int = 8000) -> list[CheckResult]:
    """project 为空时只体检 CLI 自身环境；否则对生成项目做全量体检。"""
    results = [check_python(), check_git()]
    if project is None:
        return results
    results.append(check_structure(project))
    if any(r.status == "fail" and r.name == "项目结构" for r in results):
        return results  # 不是生成项目，后续检查无意义
    results += [
        check_venv(project),
        check_deps(project),
        check_api_keys(project),
        check_port(port),
    ]
    kb = check_kb(project)
    if kb:
        results.append(kb)
    return results
