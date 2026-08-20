"""doctor 体检模块测试：分级判定与修复提示。"""

from __future__ import annotations

import socket
import sys

from ai_app_template import doctor


def test_check_python_ok():
    assert doctor.check_python().status == "ok"


class _FakeVersion(tuple):
    """行为同 sys.version_info：支持元组比较，又有 major/minor/micro 属性。"""

    @property
    def major(self):
        return self[0]

    @property
    def minor(self):
        return self[1]

    @property
    def micro(self):
        return self[2]


def test_check_python_too_old(monkeypatch):
    monkeypatch.setattr(sys, "version_info", _FakeVersion((3, 9, 18)))
    result = doctor.check_python()
    assert result.status == "fail"
    assert "3.10" in result.detail


def test_check_structure(tmp_path):
    ok_dir = tmp_path / "proj"
    (ok_dir / "app").mkdir(parents=True)
    (ok_dir / "pyproject.toml").write_text("{}", encoding="utf-8")
    assert doctor.check_structure(ok_dir).status == "ok"

    result = doctor.check_structure(tmp_path / "empty")
    assert result.status == "fail"
    assert "pyproject.toml" in result.detail and "app/" in result.detail


def test_check_venv_and_env_keys(tmp_path):
    assert doctor.check_venv(tmp_path).status == "warn"  # 无 .venv

    proj = tmp_path / "p2"
    proj.mkdir()
    (proj / ".env").write_text("# 注释\nOPENAI_API_KEY=sk-real\nEMPTY_KEY=\n", encoding="utf-8")
    result = doctor.check_api_keys(proj)
    assert result.status == "ok" and "OPENAI_API_KEY" in result.detail

    (proj / ".env").write_text("OPENAI_API_KEY=sk-xxxx\n", encoding="utf-8")  # 占位值
    assert doctor.check_api_keys(proj).status == "warn"

    assert doctor.check_api_keys(tmp_path / "no-env").status == "warn"  # 无 .env


def test_check_port_free_and_occupied():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert doctor.check_port(free_port).status == "ok"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied_port = blocker.getsockname()[1]
        result = doctor.check_port(occupied_port)
        assert result.status == "warn" and "占用" in result.detail


def test_run_doctor_modes(tmp_path):
    self_only = doctor.run_doctor(None)
    assert [r.name for r in self_only] == ["Python 版本", "git"]

    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "pyproject.toml").write_text("{}", encoding="utf-8")
    results = doctor.run_doctor(proj, port=1)  # 端口 1 通常无权限 -> 也只是 warn
    names = [r.name for r in results]
    assert "项目结构" in names and "API Key" in names and "虚拟环境" in names

    # 非项目目录：结构失败后短路
    short = doctor.run_doctor(tmp_path / "not-a-project")
    assert [r.name for r in short] == ["Python 版本", "git", "项目结构"]
    assert short[-1].status == "fail"
