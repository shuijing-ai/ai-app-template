.PHONY: install dev lint format test demo clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

lint:
	ruff check src tests

format:
	ruff format src tests && ruff check --fix src tests

test:
	pytest -q

# 生成本地演示项目（不进 git），用于快速体验 CLI
demo:
	rm -rf demo-app
	python -m ai_app_template.cli create demo-app --template review-flow --yes || ai-app-template create demo-app --template review-flow --yes

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache demo-app
