.PHONY: tools kind-up kind-down test-config eval eval-baseline qualify-network admission-artifacts admission-install qualify-admission openshell-install qualify-gateway qualify-lifecycle policy-image policy-image-load qualify-policy
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
# pytest otherwise infers its root from argument paths, so an evidence dir inside another checkout (for example
# the main repository's .runs from a worktree) would load that checkout's config and code.
PYTEST_ROOT := -c $(CURDIR)/pyproject.toml --rootdir=$(CURDIR)
ifndef CORSAIR_QUAL_RUN
CORSAIR_QUAL_RUN := .runs/network-$(shell date -u +%Y%m%dT%H%M%S)
endif

tools:
	uv run --locked python deploy/kind/bootstrap.py tools

kind-up:
	uv run --locked python deploy/kind/bootstrap.py up

kind-down:
	uv run --locked python deploy/kind/bootstrap.py down

# SPEC-0036 workspace quota class on the owned node (proposed, unqualified).
.PHONY: workspace-storage
workspace-storage:
	uv run --locked python deploy/kind/bootstrap.py workspace-storage

test-config:
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py tests/temporal/test_chain_composition.py

# One agent's isolated eval suite on the host (SPEC-0044); results under .runs/evals/<agent>/.
# AGENT=identification|planning|authoring|environment|assessment|chain; optional SET, PROVIDER_CONFIG, REPEAT, NOTE.
eval:
	uv run --locked python -m evals.run "$(AGENT)" $(if $(SET),--set "$(SET)") $(if $(PROVIDER_CONFIG),--provider-config "$(PROVIDER_CONFIG)") $(if $(REPEAT),--repeat "$(REPEAT)") $(if $(NOTE),--note "$(NOTE)")

eval-baseline:
	uv run --locked python -m evals.run "$(AGENT)" --promote "$(RUN)"

qualify-network:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m platform --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Explicit preparation and installation. Neither target installs a gateway.
admission-artifacts:
	uv run --locked python -m deploy.openshell.artifacts

admission-install:
	uv run --locked python -m tests.qualification.install_admission

qualify-admission:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m admission --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Gateway work requires successful admission from this exact owned node.
openshell-install:
	uv run --locked python -m tests.qualification.install_gateway --admission-evidence "$(CORSAIR_ADMISSION_RUN)"

qualify-gateway:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m gateway --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Includes the mandatory bounded gateway/identity controls on this installed node.
qualify-lifecycle:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m lifecycle --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

policy-image:
	uv run --locked python -m tests.qualification.prepare_policy_image build

policy-image-load:
	uv run --locked python -m tests.qualification.prepare_policy_image load

qualify-policy:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m policy --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: toolchain-images toolchain-images-load qualify-toolchain
# TOOLCHAINS limits preparation to the named image directories and the gate to the gates whose images are all
# named, e.g. TOOLCHAINS=python37 or TOOLCHAINS="java python"; a list no gate covers is a usage error.
toolchain-images:
	uv run --locked python -m tests.qualification.prepare_toolchains build $(foreach language,$(TOOLCHAINS),--language $(language))

toolchain-images-load:
	uv run --locked python -m tests.qualification.prepare_toolchains load $(foreach language,$(TOOLCHAINS),--language $(language))

qualify-toolchain:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m toolchain $(foreach language,$(TOOLCHAINS),--toolchain $(language)) --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Refresh each Java image's reviewed Maven cache list (SPEC-0064) from a clean build of its preparation stage, then
# review the diff: the image build fails on any difference from the checked-in list. TOOLCHAINS names the Java images
# (default: both).
.PHONY: maven-hashes
maven-hashes:
	for dir in $(or $(TOOLCHAINS),java java8); do \
	  docker --host=unix:///var/run/docker.sock build --no-cache --target cache --tag corsair-m2-$$dir deploy/qualification/toolchains/$$dir \
	  && docker --host=unix:///var/run/docker.sock run --rm --network=none corsair-m2-$$dir cat /opt/corsair-m2.sha256 > deploy/qualification/toolchains/$$dir/m2.sha256.new \
	  && mv deploy/qualification/toolchains/$$dir/m2.sha256.new deploy/qualification/toolchains/$$dir/m2.sha256 \
	  || { rm -f deploy/qualification/toolchains/$$dir/m2.sha256.new; exit 1; }; \
	done

.PHONY: qualify-recovery
qualify-recovery:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m recovery --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-readiness qualify-adapter-lifecycle
qualify-readiness:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m readiness --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-adapter-lifecycle:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m adapter_lifecycle --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-adapter-execution
qualify-adapter-execution:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m adapter_execution --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Independent local-host boundary; no gateway/transfer admission is inferred.
.PHONY: qualify-artifacts
qualify-artifacts:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -m 700 -p "$(CORSAIR_QUAL_RUN)"
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m tests.qualification.qualify_artifacts --evidence-dir "$(CORSAIR_QUAL_RUN)" --configuration "$(CORSAIR_ARTIFACT_CONFIG)" --source-manifest "$(CORSAIR_SOURCE_MANIFEST)"

# One documented native upload; no download or application transfer admission.
.PHONY: qualify-native-upload
qualify-native-upload:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m native_upload --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Pre-execution captured-source composition; no general transfer API or download.
.PHONY: qualify-source-upload
qualify-source-upload:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m source_upload --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Independent existing-adapter qualifications; one matrix per evidence root.
.PHONY: qualify-execution-artifacts qualify-execution-receipts
qualify-execution-artifacts:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m execution_artifacts --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-execution-receipts:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m execution_receipts --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Separate existing-component matrices; fixture evidence roots must not overlap.
.PHONY: qualify-source-execution qualify-execution-transport
qualify-source-execution:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m source_execution --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-execution-transport:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m execution_transport --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Fixed opaque-file recipe over bounded native execution; no archive download API.
.PHONY: qualify-untrusted-file
qualify-untrusted-file:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m untrusted_file --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# An independently owned native fixture service; never starts/downloads a server.
.PHONY: qualify-temporal-fixture
qualify-temporal-fixture:
	test -n "$(CORSAIR_TEMPORAL_ADDRESS)"
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -m 700 -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/temporal/test_fixture_native.py --temporal-address "$(CORSAIR_TEMPORAL_ADDRESS)" --temporal-evidence-dir "$(CORSAIR_QUAL_RUN)/histories" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Reviewed SPEC-0018 pair through OpenShellTestWorkspace and the native pytest runner; fixture source only.
.PHONY: qualify-test-workspace
qualify-test-workspace:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m test_workspace --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# SPEC-0025 provider placeholder delivery with a random fake credential; egress substitution unqualified.
.PHONY: qualify-credential-placeholder
qualify-credential-placeholder:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m credential_placeholder --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# E2E-0 over OpenShellTestWorkspace: scripted control, then CORSAIR_E2E_RUNS live runs of CORSAIR_E2E_LIVE stages;
# optional CORSAIR_STAGE_PROFILES is the evals.fixture_e2e.run --stage-profiles JSON.
CORSAIR_E2E_LIVE ?= identification,planning,authoring,assessment
CORSAIR_E2E_RUNS ?= 1
.PHONY: qualify-fixture-e2e
qualify-fixture-e2e:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	test -z "$(CORSAIR_E2E_LIVE)" -o "$(CORSAIR_E2E_RUNS)" = 0 -o -f "$(CORSAIR_PROVIDER_CONFIG)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m fixture_e2e --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --provider-config "$(CORSAIR_PROVIDER_CONFIG)" --e2e-live "$(CORSAIR_E2E_LIVE)" --e2e-runs "$(CORSAIR_E2E_RUNS)" $(if $(CORSAIR_STAGE_PROFILES),--e2e-stage-profiles "$(CORSAIR_STAGE_PROFILES)") --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-python37-case
# SPEC-0046: host-fetch CVE-2021-32839 into RUN-sources (pins written there, not to benchmarks/), then the pytest
# runner on its baseline and fix commits in fresh CPython 3.7 sandboxes. Needs TOOLCHAINS=python37 images loaded.
# Cases each per-image case target runs; make qualify-image reads these before it installs a gateway.
CASES_python37 := CVE-2021-32839
qualify-python37-case:
	test -z "$(CASE)" -o "$(CASE)" = "$(CASES_python37)"
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m evals.benchmark.sources fetch --run-dir "$(CORSAIR_QUAL_RUN)-sources" --cases CVE-2021-32839 --keep --pins "$(CORSAIR_QUAL_RUN)-sources/source-pins.json"
	CORSAIR_CASE_SOURCES="$(CORSAIR_QUAL_RUN)-sources" uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m python37_case --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# SPEC-0070 static workspace verifier, uploaded into every sandbox so no image needs an interpreter. Needs Go 1.22+;
# the build is reproducible for one Go version, and adapters pin the SHA-256 of the file they read.
.PHONY: workspace-verifier
workspace-verifier:
	mkdir -p .state/tools
	cd tools/workspace-verify && CGO_ENABLED=0 go build -trimpath -ldflags=-buildid= -o $(CURDIR)/.state/tools/workspace-verify .

.PHONY: qualify-environment-preparation
# SPEC-0070: the chain's environment stage in an OpenShellPreparation sandbox (scripted model) and an operator sweep.
qualify-environment-preparation: workspace-verifier
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m environment_preparation --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-witness
qualify-witness:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m witness --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# SPEC-0036 storage stage on plain pods; requires make workspace-storage on this owned node.
.PHONY: qualify-workspace-quota
qualify-workspace-quota:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest $(PYTEST_ROOT) tests/qualification -m workspace_quota --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# One image's live chain on this checkout's own cluster: tools, cluster (created only without this checkout's receipt),
# admission and network (reused while their gate checks pass on this node and lock), image build/load, gateway, the
# toolchain gate, then a fresh gateway and the image's qualify-<dir>-case. Stops at the first failure; evidence and
# SUMMARY.md under .runs/qualify/<RUN>. TOOLCHAIN=<image dir>; optional CASE, RUN, ADMISSION_RUN, NETWORK_RUN.
.PHONY: qualify-image cluster-status archive-runs
# These targets are pre-allowed on RIG0 (deploy/rig0/settings.local.json), so they refuse to share a make invocation with
# any other goal, accept only an existing image directory as TOOLCHAIN, and pass every other value through the
# environment, never into recipe text.
QUALIFY_TOOLCHAINS := $(notdir $(wildcard deploy/qualification/toolchains/*))
ifneq ($(filter qualify-image cluster-status archive-runs,$(MAKECMDGOALS)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error qualify-image, cluster-status and archive-runs each run alone, not with: $(MAKECMDGOALS))
endif
# A command-line variable reaches every recipe's environment (SHELL, PATH, PYTHONPATH, UV_*), so only these are taken.
QUALIFY_VARIABLES := TOOLCHAIN CASE RUN ADMISSION_RUN NETWORK_RUN DEST
QUALIFY_FOREIGN := $(strip $(foreach v,$(.VARIABLES),$(if $(filter command line,$(origin $(v))),$(filter-out $(QUALIFY_VARIABLES),$(v)))))
ifneq ($(QUALIFY_FOREIGN),)
$(error only $(QUALIFY_VARIABLES) may be set on the command line here, not: $(QUALIFY_FOREIGN))
endif
endif
ifeq ($(MAKECMDGOALS),qualify-image)
ifneq ($(words $(TOOLCHAIN))$(filter $(TOOLCHAIN),$(QUALIFY_TOOLCHAINS)),1$(TOOLCHAIN))
$(error TOOLCHAIN must be one of: $(QUALIFY_TOOLCHAINS))
endif
endif
qualify-image: export QUALIFY_CASE = $(CASE)
qualify-image: export QUALIFY_RUN = $(RUN)
qualify-image: export QUALIFY_ADMISSION_RUN = $(ADMISSION_RUN)
qualify-image: export QUALIFY_NETWORK_RUN = $(NETWORK_RUN)
qualify-image:
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m tests.qualification.qualify_image run --toolchain $(TOOLCHAIN) --case "$$QUALIFY_CASE" --run "$$QUALIFY_RUN" --admission "$$QUALIFY_ADMISSION_RUN" --network "$$QUALIFY_NETWORK_RUN"

# Read-only: whether this checkout holds the cluster, what is installed, which evidence is reusable.
cluster-status:
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m tests.qualification.qualify_image status

# Copy this worktree's .runs into the main checkout's .runs/worktrees/ before the worktree is deleted; removes nothing.
archive-runs: export QUALIFY_DEST = $(DEST)
archive-runs:
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m tests.qualification.qualify_image archive --dest "$$QUALIFY_DEST"
