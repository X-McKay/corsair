PYTHON := uv run --locked python
PROVIDER ?= config/providers.local.json
CASE ?= cases/path-traversal-fixture
RUNS ?= .runs/lite
MAX_SUBMISSIONS ?= 4
REQUEST_LIMIT ?= 60
DOCKER_BUILD_FLAGS ?=

.PHONY: sync test test-offline test-docker image verify investigate eval historical-eval pilot cleanup

sync:
	uv sync --locked

test: image
	$(PYTHON) -m pytest -q -m "not live"

test-offline:
	$(PYTHON) -m pytest -q -m "not docker and not live"

test-docker: image
	$(PYTHON) -m pytest -q -m docker

image:
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-python:dev images/python
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-javascript:dev images/javascript
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-java:dev images/java21
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-perl:dev images/perl

# Kernel only: verify a human- or agent-written submission (no model unless PROVIDER adds the blind auditor).
verify: image
	$(PYTHON) -m corsair.cli verify --case $(CASE) --submission $(CASE)/reference-submission.json --runs $(RUNS)

investigate: image
	$(PYTHON) -m corsair.cli investigate --case $(CASE) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --request-limit $(REQUEST_LIMIT) --runs $(RUNS)

# The release gate contains only cases reviewed for the lite verdict semantics. Historical cases remain exploratory
# until their oracles are reviewed; this kernel intentionally does not emit LIKELY_NOT_EXPLOITABLE.
RELEASE_CASES := cases/path-traversal-fixture cases/path-traversal-javascript cases/path-traversal-java cases/path-traversal-perl
HISTORICAL_CASES := $(wildcard evals/e2e/python/v2/*-a) $(wildcard evals/e2e/python/v2/*-b)
EVAL_CASES ?= $(RELEASE_CASES)
eval: image
	$(PYTHON) -m corsair.cli eval --cases $(EVAL_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --request-limit $(REQUEST_LIMIT) --runs $(RUNS)

historical-eval: image
	$(PYTHON) -m corsair.cli eval --cases $(HISTORICAL_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --request-limit $(REQUEST_LIMIT) --runs $(RUNS)

pilot: image
	$(PYTHON) -m corsair.cli verify --case cases/path-traversal-fixture --submission cases/path-traversal-fixture/reference-submission.json --provider $(PROVIDER) --runs $(RUNS)
	$(PYTHON) -m corsair.cli eval --cases $(RELEASE_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --request-limit $(REQUEST_LIMIT) --runs $(RUNS)

cleanup:
	$(PYTHON) -m corsair.cli cleanup
