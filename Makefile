.PHONY: sync check lint format-check typecheck test test-offline test-docker test-temporal test-live images build verify eval

sync:
	uv sync --locked --all-extras

check: lint format-check typecheck

lint:
	uv run --locked ruff check src tests evals

format-check:
	uv run --locked ruff format --check src tests evals

typecheck:
	uv run --locked ty check --error-on-warning

test test-offline:
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
