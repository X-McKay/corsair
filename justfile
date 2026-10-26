# Developer tasks for Just 1.58.0 from `nix develop` (or: uv tool install rust-just==1.58.0).
# Another Just fails to parse this file; `python3 scripts/check_toolchain.py` names the remedy.
set default-list
set positional-arguments
set shell := ["bash", "-euo", "pipefail", "-c"]

# Install the locked SDKs and development tools; refuses a .venv uv would keep but cannot import.
sync:
    python3 scripts/check_toolchain.py --before-sync
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

# Build the reviewed native observer images (one per language under deploy/).
images:
    docker build -f deploy/python/Dockerfile -t corsair-python:0.1 .
    docker build -f deploy/javascript/Dockerfile -t corsair-javascript:0.1 .
    docker build -f deploy/ruby/Dockerfile -t corsair-ruby:0.1 .
    docker build -f deploy/java/Dockerfile -t corsair-java:0.1 .
    docker build -f deploy/perl/Dockerfile -t corsair-perl:0.1 .
    docker build -f deploy/c/Dockerfile -t corsair-c:0.1 .

# Create .state/settings.json from the template with an absolute source_root; never overwrites.
settings-init:
    uv run --locked python scripts/local_stack.py settings-init

# Start a background Temporal dev server; pid, log and database live under .state.
temporal-up: settings-init
    uv run --locked python scripts/local_stack.py temporal-up

# Stop the Temporal dev server started by temporal-up and confirm it is gone.
temporal-down:
    uv run --locked python scripts/local_stack.py temporal-down

# Start a background worker; provider credentials come from this environment.
worker-up: settings-init
    uv run --locked python scripts/local_stack.py worker-up

# Stop the worker started by worker-up after its graceful drain.
worker-down:
    uv run --locked python scripts/local_stack.py worker-down

# First run without a model: settings, Temporal, doctor, then the case01 native verify.
demo: settings-init temporal-up
    uv run --locked python scripts/local_stack.py demo-doctor
    uv run --locked corsair --format human verify evals/fixtures/case01/request.json evals/fixtures/case01/submission.json --settings .state/settings.json
    @echo "Next: configure models in .state/settings.json, export provider credentials, run 'just worker-up', then follow docs/getting-started/first-project.md. Stop with 'just worker-down temporal-down'."

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

# Score a frozen scanner-intake dataset (evals/datasets/intake.json); no model, container or service.
eval-intake dataset *args:
    uv run --locked python -m corsair.evaluation.intake "$@"

# Live isolated eval with .state/settings.json; record in .runs/live. Optional BASELINE report, --dry-run.
live-agent role dataset *args:
    uv run --locked --extra providers python scripts/live_eval.py agent "$@"

# Live composed eval (needs Temporal and a worker); same record. Optional BASELINE report, --dry-run.
live-chain dataset *args:
    uv run --locked --extra providers python scripts/live_eval.py chain "$@"

# Check that dataset families, cases and chain pairs keep one split; default evals/datasets/*.json.
dataset-families *datasets:
    uv run --locked python -m corsair.evaluation.families "$@"
