# Developer tasks. Install: uv tool install rust-just==1.58.0
set default-list
set positional-arguments
set shell := ["bash", "-euo", "pipefail", "-c"]

# Install the locked SDKs and development tools.
sync:
    uv sync --locked --all-extras

# Run every lint, formatting and typing gate.
check: lint format-check typecheck

# Lint maintained source, tests and evaluators.
lint:
    uv run --locked ruff check src tests evals

# Check Python and Just formatting without rewriting frozen fixtures.
format-check:
    uv run --locked ruff format --check src tests evals
    just --fmt --check

# Fail on type errors and warnings.
typecheck:
    uv run --locked ty check --error-on-warning

# Run offline tests; remaining arguments go directly to pytest.
test *args:
    uv run --locked pytest -m 'not docker and not temporal and not live' "$@"

alias test-offline := test

# Build the reviewed native observer image.
images:
    docker build -f deploy/python/Dockerfile -t corsair-python:0.1 .

# Run real Docker tests; set CORSAIR_TEST_TEMPORAL=1 for integrated durable tests.
test-docker *args:
    CORSAIR_TEST_DOCKER=1 uv run --locked pytest -m docker "$@"

# Run actual Temporal workflow and replay tests.
test-temporal *args:
    CORSAIR_TEST_TEMPORAL=1 uv run --locked pytest -m temporal "$@"

# Run explicitly configured provider tests; requires CORSAIR_LIVE_CONFIG.
test-live *args:
    uv run --locked --extra providers pytest -m live "$@"

# Run all native gates; live tests also require CORSAIR_LIVE_CONFIG.
test-all *args:
    CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 uv run --locked --extra providers pytest "$@"

# Build the source distribution and wheel.
build:
    uv build

# Execute a frozen reference; pass normal Corsair switches after the two paths.
verify request submission *args:
    uv run --locked corsair verify "$@"

# Run a durable frozen dataset; pass normal Corsair switches after its path.
eval dataset *args:
    uv run --locked --extra providers corsair eval "$@"

# Run an isolated producer/auditor evaluation; pass --settings and other switches.
eval-agent agent dataset *args:
    uv run --locked --extra providers python evals/evaluators/agents.py "$@"
