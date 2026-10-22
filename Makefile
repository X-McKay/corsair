PYTHON := uv run --locked python
PROVIDER ?= config/providers.local.json
CASE ?= cases/path-traversal-fixture
RUNS ?= .runs/lite
MAX_SUBMISSIONS ?= 4

.PHONY: sync test test-offline test-docker image verify investigate eval pilot cleanup

sync:
	uv sync --locked

test: image
	$(PYTHON) -m pytest -q -m "not live"

test-offline:
	$(PYTHON) -m pytest -q -m "not docker and not live"

test-docker: image
	$(PYTHON) -m pytest -q -m docker

image:
	docker build -q -t corsair-lite-python:dev images/python

# Kernel only: verify a human- or agent-written submission (no model unless PROVIDER adds the blind auditor).
verify: image
	$(PYTHON) -m corsair.cli verify --case $(CASE) --submission $(CASE)/reference-submission.json --runs $(RUNS)

investigate: image
	$(PYTHON) -m corsair.cli investigate --case $(CASE) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --runs $(RUNS)

# The pilot set: the reviewed fixture plus the local Python corpus cases that carry a fixed revision.
PILOT_CASES := cases/path-traversal-fixture $(wildcard evals/e2e/python/v2/*-a) $(wildcard evals/e2e/python/v2/*-b)
eval: image
	$(PYTHON) -m corsair.cli eval --cases $(PILOT_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --runs $(RUNS)

pilot: image
	$(PYTHON) -m corsair.cli verify --case cases/path-traversal-fixture --submission cases/path-traversal-fixture/reference-submission.json --provider $(PROVIDER) --runs $(RUNS)
	$(PYTHON) -m corsair.cli eval --cases $(PILOT_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --runs $(RUNS)

cleanup:
	$(PYTHON) -m corsair.cli cleanup
