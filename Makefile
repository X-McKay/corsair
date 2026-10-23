PYTHON := uv run --locked python
PROVIDER ?= config/providers.local.json
CASE ?= cases/path-traversal-fixture
RUNS ?= .runs/lite
MAX_SUBMISSIONS ?= 4
REPEATS ?= 1
DEV_SET ?= evals/e2e/sets/python-v2-dev.json
HELDOUT_SET ?= evals/e2e/sets/python-v2-heldout.json
WORKERS ?= 4
BENCH_ROOT ?= .runs/polyglot
LANGUAGE ?=

.PHONY: sync test test-offline test-docker image images benchmark benchmark-generate verify investigate eval eval-dev eval-heldout pilot cleanup

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

images: image
	docker build -q -t corsair-lite-node:dev images/node
	docker build -q -t corsair-lite-java:dev images/jvm
	docker build -q -t corsair-lite-perl:dev images/perl
	docker build -q -t corsair-lite-ruby:dev images/ruby
	docker build -q -t corsair-lite-cpp:dev images/cpp

benchmark-generate:
	$(PYTHON) tools/benchmark.py --root $(BENCH_ROOT) $(if $(LANGUAGE),--language $(LANGUAGE)) --generate-only --output $(BENCH_ROOT)/generated.json

benchmark:
	$(PYTHON) tools/benchmark.py --root $(BENCH_ROOT) $(if $(LANGUAGE),--language $(LANGUAGE)) --run-kernel --workers $(WORKERS) --output $(BENCH_ROOT)/report.json

# Kernel only: verify a human- or agent-written submission (no model unless PROVIDER adds the blind auditor).
verify: image
	$(PYTHON) -m corsair.cli verify --case $(CASE) --submission $(CASE)/reference-submission.json --runs $(RUNS)

investigate: image
	$(PYTHON) -m corsair.cli investigate --case $(CASE) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --runs $(RUNS)

# The pilot set: the reviewed fixture plus the local Python corpus cases that carry a fixed revision.
PILOT_CASES := cases/path-traversal-fixture $(wildcard evals/e2e/python/v2/*-a) $(wildcard evals/e2e/python/v2/*-b)
eval: image
	$(PYTHON) -m corsair.cli eval --cases $(PILOT_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --repeats $(REPEATS) --runs $(RUNS)

# Frozen splits of the paired Python v2 cases. Tune prompts and skills on eval-dev only; eval-heldout is for reporting a
# configuration already frozen on dev. REPEATS=N runs each case N times (provider config picks the model).
eval-dev: image
	$(PYTHON) -m corsair.cli eval --set $(DEV_SET) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --repeats $(REPEATS) --runs $(RUNS)

eval-heldout: image
	$(PYTHON) -m corsair.cli eval --set $(HELDOUT_SET) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --repeats $(REPEATS) --runs $(RUNS)

pilot: image
	$(PYTHON) -m corsair.cli verify --case cases/path-traversal-fixture --submission cases/path-traversal-fixture/reference-submission.json --provider $(PROVIDER) --runs $(RUNS)
	$(PYTHON) -m corsair.cli eval --cases $(PILOT_CASES) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --runs $(RUNS)

cleanup:
	$(PYTHON) -m corsair.cli cleanup
