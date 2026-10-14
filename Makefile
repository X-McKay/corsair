.PHONY: test test-v2 eval eval-baseline baseline-commit eval-live-baselines release-check gate-status canary toolchain-images maven-hashes
.PHONY: test-config
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
# pytest otherwise infers its root from argument paths, so an evidence dir inside another checkout (for example
# the main repository's .runs from a worktree) would load that checkout's config and code.
PYTEST_ROOT := -c $(CURDIR)/pyproject.toml --rootdir=$(CURDIR)
# A new evidence directory under this checkout's own .runs for each live qualification target.
ifndef CORSAIR_QUAL_RUN
CORSAIR_QUAL_RUN := .runs/qualify-$(shell date -u +%Y%m%dT%H%M%S)
endif

# The offline suite is CPU-bound; pytest-xdist spreads it over the cores. `TEST_WORKERS=0 make test-v2` runs it
# serially. No model, no cluster; Docker-backed tests skip when Docker is unavailable.
TEST_WORKERS ?= auto
test-v2:
	uv run --locked python -m pytest $(PYTEST_ROOT) -n $(TEST_WORKERS) tests

test: test-v2

test-config:
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/configuration

# One agent's isolated eval suite on the host; results under .runs/evals/<agent>/.
# AGENT=grounding|builder|investigator|control_prober|exploit_prober|reviewer (cases, sets and release policy in
# src/corsair/agents/<agent>/evals/; summary.json, comparison.md and policy.json per run). Optional SET,
# EVAL_LANGUAGE (one language of a per-case set: python|java|javascript|ruby|perl|common), PROVIDER_CONFIG, REPEAT, NOTE.
eval:
	uv run --locked python -m evals.run "$(AGENT)" $(if $(SET),--set "$(SET)") $(if $(EVAL_LANGUAGE),--language "$(EVAL_LANGUAGE)") $(if $(PROVIDER_CONFIG),--provider-config "$(PROVIDER_CONFIG)") $(if $(REPEAT),--repeat "$(REPEAT)") $(if $(NOTE),--note "$(NOTE)")

eval-baseline:
	uv run --locked python -m evals.run "$(AGENT)" --promote "$(RUN)"

# v2: promote RUN and write <agent evals>/baselines/<set>-<mode>.json for committing (whole set, clean checkout).
baseline-commit:
	uv run --locked python -m evals.run "$(AGENT)" --commit-baseline "$(RUN)"

# Live baselines, one agent after another (one live inference user at a time). AGENTS defaults to the six v2
# agents; the chain (AGENTS=chain) also needs Docker. Prints each run id; commit the ones you choose with
# baseline-commit.
eval-live-baselines:
	@test -n "$(PROVIDER_CONFIG)" || { echo "PROVIDER_CONFIG is required"; exit 2; }
	@failed=""; for agent in $(or $(AGENTS),grounding investigator builder control_prober exploit_prober reviewer); do \
	  index=".runs/evals/$$agent/index.jsonl"; before=$$(cat "$$index" 2>/dev/null | wc -l); \
	  uv run --locked python -m evals.run "$$agent" --provider-config "$(PROVIDER_CONFIG)" $(if $(NOTE),--note "$(NOTE)") || true; \
	  after=$$(cat "$$index" 2>/dev/null | wc -l); \
	  if [ "$$after" -gt "$$before" ]; then tail -n +$$((before + 1)) "$$index"; \
	  else echo "$$agent: no run recorded"; failed="$$failed $$agent"; fi; \
	done; test -z "$$failed" || { echo "no run recorded for:$$failed"; exit 1; }

# Release check (tools/release_check.py, docs/design/gates-and-release.md), offline and deterministic: check every agent
# and the chain against its committed live baseline and release policy, and report whether the gate for turning gates
# back on holds.
release-check:
	uv run --locked python tools/release_check.py check $(foreach agent,$(AGENT),--agent $(agent))

gate-status:
	uv run --locked python tools/release_check.py gate

# Classify each runtime-matrix row's known-passing and known-failing canary on its image (evidence under .runs/canary/).
canary:
	uv run --locked python tools/v2_canary.py

# Build toolchain images from deploy/qualification/toolchains/<name> and run each one's trusted control; TOOLCHAINS
# limits preparation to the named image directories, e.g. TOOLCHAINS=python37 or TOOLCHAINS="java python".
toolchain-images:
	uv run --locked python tools/toolchain_images.py $(foreach language,$(TOOLCHAINS),--language $(language))

# Refresh each Java image's reviewed Maven cache list (SPEC-0064) from a clean build of its preparation stage, then
# review the diff: the image build fails on any difference from the checked-in list. TOOLCHAINS names the Java images
# (default: both).
maven-hashes:
	for dir in $(or $(TOOLCHAINS),java java8); do \
	  docker --host=unix:///var/run/docker.sock build --no-cache --target cache --tag corsair-m2-$$dir deploy/qualification/toolchains/$$dir \
	  && docker --host=unix:///var/run/docker.sock run --rm --network=none corsair-m2-$$dir cat /opt/corsair-m2.sha256 > deploy/qualification/toolchains/$$dir/m2.sha256.new \
	  && mv deploy/qualification/toolchains/$$dir/m2.sha256.new deploy/qualification/toolchains/$$dir/m2.sha256 \
	  || { rm -f deploy/qualification/toolchains/$$dir/m2.sha256.new; exit 1; }; \
	done

# Fresh kind + OpenShell cluster for the v2 OpenShell backend (docs/runbooks/openshell-v2.md). Every target runs
# against the one owned `corsair` cluster in .state/kind; evidence lands under this checkout's own .runs.
.PHONY: tools kind-up kind-down qualify-network admission-artifacts admission-install qualify-admission \
	openshell-install qualify-gateway openshell-images-load openshell-config openshell-forward-stop qualify-openshell-v2
QUAL_ARGS = --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" \
	--junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Checksum-verified kind and kubectl into .tools/linux-amd64 (admission-artifacts adds helm and the OpenShell CLI).
tools:
	uv run --locked python deploy/kind/bootstrap.py tools

kind-up:
	uv run --locked python deploy/kind/bootstrap.py up

kind-down:
	uv run --locked python deploy/kind/bootstrap.py down

qualify-network:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m platform $(QUAL_ARGS)

# Explicit preparation and installation. Neither target installs a gateway.
admission-artifacts:
	uv run --locked python -m deploy.openshell.artifacts

admission-install:
	uv run --locked python -m tests.qualification.install_admission

qualify-admission:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m admission $(QUAL_ARGS)

# Gateway work requires successful admission from this exact owned node (CORSAIR_ADMISSION_RUN, under .runs).
openshell-install:
	test -n "$(CORSAIR_ADMISSION_RUN)"
	uv run --locked python -m tests.qualification.install_gateway --admission-evidence "$(CORSAIR_ADMISSION_RUN)"

# Optional bounded gateway TLS/caller-auth/identity/access-isolation controls. It UNINSTALLS the gateway and removes
# .state/openshell afterwards, so run openshell-install again before the steps below.
qualify-gateway:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m gateway --tb=short $(QUAL_ARGS)

# Load each locally built deploy/v2/runtime-matrix.yaml image into the node; writes .state/openshell/images.json.
openshell-images-load:
	uv run --locked python -m tools.openshell_images load

# Private client mTLS, a loopback port-forward and .state/openshell/config.json for the v2 backend.
# OPENSHELL_PORT picks the local port (default: a free one).
openshell-config:
	uv run --locked python -m tools.openshell_images config $(if $(OPENSHELL_PORT),--port "$(OPENSHELL_PORT)")

openshell-forward-stop:
	uv run --locked python -m tools.openshell_images stop

# The v2 OpenShell backend's live tests (marker `openshell` in tests/v2) against the installed gateway.
qualify-openshell-v2:
	test -f .state/openshell/config.json
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	CORSAIR_WORKSPACE=openshell CORSAIR_OPENSHELL_CONFIG="$(CURDIR)/.state/openshell/config.json" \
	CORSAIR_EVIDENCE_DIR="$(abspath $(CORSAIR_QUAL_RUN))" \
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/v2 -m openshell --tb=short \
		--evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Read-only UI over v2 run records and eval runs (docs/runbooks/local-ui.md, SPEC-0084). Node 22.6+; it launches no
# work. `make ui` serves ui/dist and the API on http://127.0.0.1:8765 from .runs/evals, .runs/v2/runs and the v2 matrix.
.PHONY: ui-install ui-build ui-check ui-test ui
ui-install:
	npm --prefix ui ci

ui-build:
	npm --prefix ui run build

ui-check:
	npm --prefix ui test
	npm --prefix ui run build

ui-test:
	npm --prefix ui run test:e2e

ui:
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m corsair.web --root "$(CURDIR)"
