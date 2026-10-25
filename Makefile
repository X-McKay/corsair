.PHONY: sync check test test-offline test-config test-docker test-temporal test-live images build verify eval

sync:
	uv sync --locked --all-extras

check:
	uv run --locked ruff check src tests evals/evaluators
	uv run --locked ruff format --check src tests evals/evaluators

test test-offline test-config:
	uv run --locked pytest -m 'not docker and not temporal and not live'

images:
	docker build -f deploy/python/Dockerfile -t corsair-python:0.1 .

test-docker:
	CORSAIR_TEST_DOCKER=1 uv run --locked pytest -m docker

test-temporal:
	CORSAIR_TEST_TEMPORAL=1 uv run --locked pytest -m temporal

test-live:
	uv run --locked --extra providers pytest -m live

build:
	uv build

verify:
	uv run --locked corsair verify $(CASE) $(SUBMISSION) $(if $(SETTINGS),--settings $(SETTINGS),)

eval:
	uv run --locked --extra providers corsair eval $(SET) $(if $(SETTINGS),--settings $(SETTINGS),)
