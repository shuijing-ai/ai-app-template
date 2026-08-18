.PHONY: install dev test lint run eval-mock docker

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check app tests

run:
	uvicorn app.main:app --reload

# 离线评测：不花一分钱，CI 可直接用
eval-mock:
	python -m app.eval.run_eval --mock

docker:
	docker build -t {{ project_name }} .
