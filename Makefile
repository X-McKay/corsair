.PHONY: tools kind-up kind-down test-config qualify-network
export UV_CACHE_DIR := $(CURDIR)/.cache/uv
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
