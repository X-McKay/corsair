# Developer tasks for Just 1.58.0 from `nix develop` (or: uv tool install rust-just==1.58.0).
# Another Just fails to parse this file; `python3 scripts/check_toolchain.py` names the remedy.
set default-list
set positional-arguments
set shell := ["bash", "-euo", "pipefail", "-c"]

# Install the locked SDKs and development tools.
sync:
    uv sync --locked --all-extras

# Run the toolchain, lint, formatting, typing and documentation gates.
check: toolchain lint format-check typecheck docs-check

# Report tool, .venv and extra versions against the Nix shell; runs before uv touches .venv.
toolchain:
    python3 scripts/check_toolchain.py

# Lint maintained source, tests and evaluators.
lint:
    uv run --locked ruff check src tests evals scripts

# Check Python and Just formatting without rewriting frozen fixtures.
format-check:
    uv run --locked ruff format --check src tests evals scripts
    just --fmt --check

# Fail on type errors and warnings.
typecheck:
    uv run --locked ty check --error-on-warning

# Check checked-in local Markdown links and heading anchors without network access.
docs-check:
    uv run --locked python scripts/check_docs.py

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
    uv run --locked --extra providers python -m corsair.evaluation.agents "$@"
