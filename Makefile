.PHONY: tools kind-up kind-down test-config qualify-network admission-artifacts admission-install qualify-admission openshell-install qualify-gateway qualify-lifecycle
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

test-config:
	uv run --locked python -m pytest tests/configuration

qualify-network:
	mkdir -p "$(CORSAIR_QUAL_RUN)"
	uv run --locked python -m pytest tests/qualification -m platform --kubeconfig .state/kind/kubeconfig --context kind-corsair --evidence-dir "$(CORSAIR_QUAL_RUN)" --junitxml "$(CORSAIR_QUAL_RUN)/junit.xml"

# Explicit preparation and installation. Neither target installs a gateway.
admission-artifacts:
	uv run --locked python -m deploy.openshell.artifacts

admission-install:
	uv run --locked python -m tests.qualification.install_admission

qualify-admission:
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
