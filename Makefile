.PHONY: tools kind-up kind-down test-config eval eval-baseline qualify-network admission-artifacts admission-install qualify-admission openshell-install qualify-gateway qualify-lifecycle policy-image policy-image-load qualify-policy
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
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
	uv run --locked python -m pytest tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py tests/temporal/test_chain_composition.py

# One agent's isolated eval suite on the host (SPEC-0044); results under .runs/evals/<agent>/.
# AGENT=identification|planning|authoring|assessment|chain; optional SET, PROVIDER_CONFIG, REPEAT, NOTE.
eval:
	uv run --locked python -m evals.run "$(AGENT)" $(if $(SET),--set "$(SET)") $(if $(PROVIDER_CONFIG),--provider-config "$(PROVIDER_CONFIG)") $(if $(REPEAT),--repeat "$(REPEAT)") $(if $(NOTE),--note "$(NOTE)")

eval-baseline:
	uv run --locked python -m evals.run "$(AGENT)" --promote "$(RUN)"

qualify-network:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m platform --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Explicit preparation and installation. Neither target installs a gateway.
admission-artifacts:
	uv run --locked python -m deploy.openshell.artifacts

admission-install:
	uv run --locked python -m tests.qualification.install_admission

qualify-admission:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m admission --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Gateway work requires successful admission from this exact owned node.
openshell-install:
	uv run --locked python -m tests.qualification.install_gateway --admission-evidence "$(CORSAIR_ADMISSION_RUN)"

qualify-gateway:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m gateway --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Includes the mandatory bounded gateway/identity controls on this installed node.
qualify-lifecycle:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m lifecycle --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

policy-image:
	uv run --locked python -m tests.qualification.prepare_policy_image build

policy-image-load:
	uv run --locked python -m tests.qualification.prepare_policy_image load

qualify-policy:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m policy --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

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
	uv run --locked python -m pytest tests/qualification -m toolchain $(foreach language,$(TOOLCHAINS),--toolchain $(language)) --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-recovery
qualify-recovery:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m recovery --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-readiness qualify-adapter-lifecycle
qualify-readiness:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m readiness --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-adapter-lifecycle:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m adapter_lifecycle --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-adapter-execution
qualify-adapter-execution:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m adapter_execution --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

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
	uv run --locked python -m pytest tests/qualification -m native_upload --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Pre-execution captured-source composition; no general transfer API or download.
.PHONY: qualify-source-upload
qualify-source-upload:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m source_upload --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Independent existing-adapter qualifications; one matrix per evidence root.
.PHONY: qualify-execution-artifacts qualify-execution-receipts
qualify-execution-artifacts:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m execution_artifacts --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-execution-receipts:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m execution_receipts --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Separate existing-component matrices; fixture evidence roots must not overlap.
.PHONY: qualify-source-execution qualify-execution-transport
qualify-source-execution:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m source_execution --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

qualify-execution-transport:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m execution_transport --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Fixed opaque-file recipe over bounded native execution; no archive download API.
.PHONY: qualify-untrusted-file
qualify-untrusted-file:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m untrusted_file --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# An independently owned native fixture service; never starts/downloads a server.
.PHONY: qualify-temporal-fixture
qualify-temporal-fixture:
	test -n "$(CORSAIR_TEMPORAL_ADDRESS)"
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -m 700 -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/temporal/test_fixture_native.py --temporal-address "$(CORSAIR_TEMPORAL_ADDRESS)" --temporal-evidence-dir "$(CORSAIR_QUAL_RUN)/histories" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Reviewed SPEC-0018 pair through OpenShellTestWorkspace and the native pytest runner; fixture source only.
.PHONY: qualify-test-workspace
qualify-test-workspace:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m test_workspace --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# SPEC-0025 provider placeholder delivery with a random fake credential; egress substitution unqualified.
.PHONY: qualify-credential-placeholder
qualify-credential-placeholder:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m credential_placeholder --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# E2E-0 over OpenShellTestWorkspace: scripted control, then CORSAIR_E2E_RUNS live runs of CORSAIR_E2E_LIVE stages;
# optional CORSAIR_STAGE_PROFILES is the evals.fixture_e2e.run --stage-profiles JSON.
CORSAIR_E2E_LIVE ?= identification,planning,authoring,assessment
CORSAIR_E2E_RUNS ?= 1
.PHONY: qualify-fixture-e2e
qualify-fixture-e2e:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	test -z "$(CORSAIR_E2E_LIVE)" -o "$(CORSAIR_E2E_RUNS)" = 0 -o -f "$(CORSAIR_PROVIDER_CONFIG)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m fixture_e2e --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --provider-config "$(CORSAIR_PROVIDER_CONFIG)" --e2e-live "$(CORSAIR_E2E_LIVE)" --e2e-runs "$(CORSAIR_E2E_RUNS)" $(if $(CORSAIR_STAGE_PROFILES),--e2e-stage-profiles "$(CORSAIR_STAGE_PROFILES)") --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-python37-case
# SPEC-0046: host-fetch CVE-2021-32839 into RUN-sources (pins written there, not to benchmarks/), then the pytest
# runner on its baseline and fix commits in fresh CPython 3.7 sandboxes. Needs TOOLCHAINS=python37 images loaded.
qualify-python37-case:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	PYTHONPATH="$(CURDIR)/src:$(CURDIR)" uv run --locked python -m evals.benchmark.sources fetch --run-dir "$(CORSAIR_QUAL_RUN)-sources" --cases CVE-2021-32839 --keep --pins "$(CORSAIR_QUAL_RUN)-sources/source-pins.json"
	CORSAIR_CASE_SOURCES="$(CORSAIR_QUAL_RUN)-sources" uv run --locked python -m pytest tests/qualification -m python37_case --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

.PHONY: qualify-witness
qualify-witness:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m witness --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --network-evidence "$(CORSAIR_NETWORK_RUN)" --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# SPEC-0036 storage stage on plain pods; requires make workspace-storage on this owned node.
.PHONY: qualify-workspace-quota
qualify-workspace-quota:
	test ! -e "$(CORSAIR_QUAL_RUN)"
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m workspace_quota --tb=short --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"
