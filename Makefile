PYTHON := uv run --locked python
PROVIDER ?= config/providers.local.json
AUDIT_PROVIDER ?=
CASE ?= cases/path-traversal-fixture
RUNS ?= .runs/lite
MAX_SUBMISSIONS ?= 4
REQUEST_LIMIT ?= 60
DOCKER_BUILD_FLAGS ?=
CORPUS_MANIFEST ?= benchmarks/dataset/manifest.json
EVAL_SET ?= development
ATTEMPTS ?= 3
RECEIPTS ?= benchmarks/dataset/receipts

.PHONY: sync test test-offline test-docker corpus-check benchmark-verify image verify verify-scripts investigate eval historical-eval pilot cleanup

sync:
	uv sync --locked

test: image
	$(PYTHON) -m pytest -q -m "not live"

test-offline:
	$(PYTHON) -m pytest -q -m "not docker and not live"

test-docker: image
	$(PYTHON) -m pytest -q -m docker

corpus-check:
	$(PYTHON) -m corsair.corpus .

benchmark-verify: image
	$(PYTHON) -m corsair.cli benchmark-verify --manifest $(CORPUS_MANIFEST) --eval-set $(EVAL_SET) \
	  --attempts $(ATTEMPTS) --runs $(RUNS) --receipts $(RECEIPTS)

image:
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-python:dev images/python
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-javascript:dev images/javascript
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-java:dev images/java21
	docker build $(DOCKER_BUILD_FLAGS) -q -t corsair-lite-perl:dev images/perl

# Verify a v2 submission. Without AUDIT_PROVIDER, the evidence remains nondecisive and exits nonzero.
verify: image
	$(PYTHON) -m corsair.cli verify --case $(CASE) --submission $(CASE)/reference-submission.json --runs $(RUNS) $(if $(AUDIT_PROVIDER),--provider $(AUDIT_PROVIDER))

# Deterministic native mechanics gate for the four reviewed script/CLI/main references. The test-only accepting
# auditor isolates runtime and coverage mechanics; this target is not evidence of live producer model quality.
SCRIPT_CASES := cases/cs-0001-b cases/cs-0002-b cases/cs-0003-b cases/cs-0004-b
verify-scripts: image
	SCRIPT_CASES='$(SCRIPT_CASES)' CORSAIR_REQUIRE_SCRIPT_GATE=1 $(PYTHON) -m pytest -q tests/test_script_conformance.py

investigate: image
	$(PYTHON) -m corsair.cli investigate --case $(CASE) --provider $(PROVIDER) --max-submissions $(MAX_SUBMISSIONS) --request-limit $(REQUEST_LIMIT) --runs $(RUNS)

# The release gate contains only cases reviewed for the lite verdict semantics. Historical cases remain exploratory
# until their oracles and probes are reviewed against the Boolean v2 submission contract.
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
