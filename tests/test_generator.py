"""生成器核心逻辑测试：渲染、叠加、排除、名称校验。"""

from __future__ import annotations

import pytest

from ai_app_template.generator import (
    TEMPLATES_DIR,
    GeneratorError,
    assert_fully_rendered,
    build_context,
    generate,
    validate_project_name,
)
from ai_app_template.registry import TEMPLATES

ALL_TEMPLATES = list(TEMPLATES)

BASE_REQUIRED_FILES = [
    "pyproject.toml",
    "README.md",
    "LICENSE",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
    "app/main.py",
    "app/config.py",
    "app/state.py",
    "app/graph/builder.py",
    "app/llm/gateway.py",
    "app/llm/router.py",
    "app/llm/fallback.py",
    "app/llm/fakes.py",
    "app/schema/wrappers.py",
    "app/observability/langfuse_setup.py",
    "app/eval/test_cases.py",
    "app/eval/run_eval.py",
    "app/utils/extractor.py",
    "app/utils/logger.py",
    "tests/test_gateway.py",
]

VARIANT_SPECIFIC = {
    "review-flow": ["app/graph/nodes/parse_node.py", "app/graph/nodes/extract_node.py"],
    "rag-agent": [
        "app/retrieval/store.py",
        "data/sample_kb.md",
        "app/graph/nodes/verify_node.py",
        "tests/test_store.py",
    ],
    "multi-agent": ["app/graph/nodes/supervisor_node.py", "app/graph/nodes/critic_node.py"],
}

VARIANT_EXCLUDED = {
    "rag-agent": ["app/graph/nodes/parse_node.py", "app/graph/nodes/review_node.py"],
    "multi-agent": ["app/graph/nodes/parse_node.py", "app/graph/nodes/summary_node.py"],
}


def make_ctx(template_id: str) -> dict:
    info = TEMPLATES[template_id]
    return build_context("my-app", template_id, info.title, "测试描述", "Tester")


def test_registry_dirs_exist():
    assert (TEMPLATES_DIR / "base").is_dir()
    for template_id in TEMPLATES:
        assert (TEMPLATES_DIR / template_id).is_dir(), template_id


@pytest.mark.parametrize("template_id", ALL_TEMPLATES)
def test_generate_produces_complete_project(tmp_path, template_id):
    target = tmp_path / "my-app"
    written = generate(target, template_id, make_ctx(template_id))

    assert written, "至少应写入一个文件"
    for rel in BASE_REQUIRED_FILES:
        assert (target / rel).is_file(), f"{template_id} 缺少 {rel}"
    for rel in VARIANT_SPECIFIC.get(template_id, []):
        assert (target / rel).is_file(), f"{template_id} 缺少 {rel}"
    for rel in VARIANT_EXCLUDED.get(template_id, []):
        assert not (target / rel).exists(), f"{template_id} 应排除 {rel}"

    # 占位符必须全部被渲染
    leftovers = assert_fully_rendered(target)
    assert leftovers == []

    # 渲染进关键文件的内容
    pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "my-app"' in pyproject
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "# my-app" in readme
    assert TEMPLATES[template_id].title in readme

    # 所有 Python 文件语法合法（渲染后必须是可编译的）
    for py in target.rglob("*.py"):
        compile(py.read_text(encoding="utf-8"), str(py), "exec")


def test_variant_overrides_base_file(tmp_path):
    target = tmp_path / "app"
    generate(target, "rag-agent", make_ctx("rag-agent"))
    # rag 变体的 builder 应包含其专属内容而非 base 版本
    builder = (target / "app" / "graph" / "builder.py").read_text(encoding="utf-8")
    assert "RagState" in builder
    assert "ReviewState" not in builder


def test_unknown_template_raises(tmp_path):
    ctx = build_context("x", "no-such", "不存在的模板")
    with pytest.raises(GeneratorError, match="未知模板"):
        generate(tmp_path / "x", "no-such", ctx)


def test_validate_project_name():
    assert validate_project_name("my-app") == "my-app"
    assert validate_project_name("My_App_2") == "My_App_2"
    for bad in ("1abc", "with space", "a" * 51, "", "app", "-leading"):
        with pytest.raises(GeneratorError):
            validate_project_name(bad)


def test_build_context_defaults():
    ctx = build_context("demo", "rag-agent", "检索增强问答 Agent")
    assert ctx["project_slug"] == "demo"
    assert ctx["description"]  # 缺省描述自动生成
    assert ctx["year"].isdigit()
