# Corsair

Corsair validates a reported security issue against an exact repository revision. Agents write exactly two native
unit tests, a benign control probe and a security-regression (exploit) probe, against the real code; trusted code runs
both in a sandbox and a fixed rule table labels the issue `LIKELY_EXPLOITABLE`, `LIKELY_NOT_EXPLOITABLE`,
`INCONCLUSIVE`, `UNABLE_TO_RUN` or `ERROR`. No model runs after execution.

This branch carries Corsair v2, a rebuild on native PydanticAI agents and skills, the PydanticAI workspace interface
(Docker is the default; the explicitly selected OpenShell backend is implemented but not live-qualified) and
Temporal durability. The v1 implementation remains on `main`.
[src/corsair/v2/README.md](src/corsair/v2/README.md) describes the chain, its stages and the rules every module keeps.

## Commands

Requirements: Linux, Python 3.12, `uv`; Docker for workspace, build and canary runs.

```shell
make test-v2                     # offline suite (alias: make test); no model, no cluster; Docker tests skip without Docker
make eval AGENT=<agent> [SET=<set>] [PROVIDER_CONFIG=<providers.json>]   # one agent's isolated eval
make eval-baseline AGENT=<agent> RUN=<run id>                             # promote a run as that agent's baseline
make canary                      # classify each runtime-matrix row's passing and failing canary on its image
make toolchain-images TOOLCHAINS=python   # build toolchain images and run their trusted controls
uv run --locked corsair-v2 run --case <name> [--mode direct|temporal]     # one case through the chain
```

The kind + OpenShell cluster for the v2 OpenShell backend (`make tools kind-up ... openshell-config qualify-openshell-v2`) is in the [OpenShell v2 runbook](docs/runbooks/openshell-v2.md).

Stage logs go to stderr. Interactive terminals show an indeterminate Rich spinner and scrolling
stage states; pipes remain append-only. The final text includes recorded per-agent tokens, requests,
tool calls and agent seconds, with missing values shown as `unknown`. `NO_COLOR` and `--color never`
disable color. Tool identities/durations and live token deltas remain a follow-on, not inferred metrics.

```shell
uv run --locked corsair-v2 run --case <name> --format json
uv run --locked corsair-v2 runs compare <run_dir>... --agents
uv run --locked corsair-v2 runs compare <run_dir>... --format json
```

JSON mode emits one versioned object on stdout and retains null telemetry. Direct cancellation
records a lifecycle receipt without manufacturing a verdict; it is not proof of external command
termination, cleanup, or resumability. An unfinished recorded run is `incomplete`, not presumed active.

Evidence lands under `.runs/` and is never committed.

## Layout

```text
src/corsair/v2/           the chain: contracts, stages, intake, matrix selection, build, execute, rules, workflow, CLI
  skills/frameworks/      per-framework guidance and canaries (the only place framework knowledge lives, with the matrix)
  workspace/              sandbox port and explicit Docker/OpenShell backends (pydantic_ai.workspaces)
deploy/v2/runtime-matrix.yaml   operator-owned runtime rows: image, framework, exit-code map
deploy/qualification/toolchains/ toolchain image sources; tools/toolchain_images.py builds them
config/v2/                provider configuration
evals/                    frozen per-case eval data and sets, the corpus loader, and `make eval` (evals/run.py)
benchmarks/               benchmark inventory and the imported infosec-harness corpus
tools/                    canary runner and toolchain image builder
tests/v2/                 offline tests
```

Development rules are in [AGENTS.md](AGENTS.md).
