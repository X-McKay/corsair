# Corsair

Corsair investigates a reported security finding against a pinned source snapshot. Google ADK runs bounded producer and outcome-blind auditor episodes inside ordinary Temporal activities. Temporal coordinates durable rounds, budgets, cancellation, and immutable results. Trusted code—not either model—admits observations and determines the scoped disposition.

This is a personal-use pilot for the `python.secret_disclosure/1` recipe. An operator fixes a Python callable, its fixed keyword arguments, and the allowed public fixture. The producer may read admitted source and submit JSON payloads; it cannot author assertions or executable probes. The trusted native observer runs control and adversarial inputs in fresh offline Docker containers and independently creates the private fixture it checks for disclosure.

`SUPPORTED` means a violation was demonstrated within the admitted component scope. An application-level claim backed only by component evidence is `CONDITIONAL`. A failed reproduction is `INCONCLUSIVE`, never `REFUTED`. Build, runtime, host, and provider failures remain operational statuses. A fixed-source result says that this particular demonstration was blocked while benign behavior survived; it is not universal patch correctness.

## Start here

Use a dedicated, disposable Ubuntu/Debian host with Python 3.12+, `uv`, a working Docker daemon, and the Temporal CLI/service. Do not admit third-party source on a host containing credentials or production workloads. Docker credentials and its socket must never reach target containers.

Start with the native reference replay. It uses the configured Docker image and trusted observer, but makes **no model call and no Temporal request**. It is the fastest way to establish the local source/image/runtime path before starting a worker.

```bash
make sync
make images
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
# Narrow source_root in .state/settings.json before admitting any other source tree.

# Interactive terminal: compact human result panel.
uv run --locked corsair --format human verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json
```

For a pipe, select JSON explicitly. JSON is the complete stdout stream; diagnostics and logs remain on stderr, so the command below is safe to parse.

```bash
set -o pipefail
uv run --locked corsair --format json verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json | python -m json.tool
```

Only after the reference works, start the durable workflow path in separate terminals:

```bash
# Terminal 1: local development Temporal persistence only.
temporal server start-dev --db-filename .state/temporal.db
```

```bash
# Terminal 2: provider credentials belong in this worker environment, not settings or requests.
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-file .state/worker.log
```

```bash
# Terminal 3: doctor is read-oriented and does not call a model or verify credentials.
# This spelling demonstrates that global switches also work after a command.
uv run --locked corsair doctor --format human --settings .state/settings.json

RUN_ID="case01-$(date +%s)"
uv run --locked --extra providers corsair investigate \
  evals/fixtures/case01/request.json --run-id "$RUN_ID" --wait \
  --format human --settings .state/settings.json
```

The worker and clients must share the configured artifact root. A local artifact path does not survive host loss; use shared durable storage and a production Temporal persistence backend or Temporal Cloud before promising that recovery level.

## CLI at a glance

Corsair chooses human output on an interactive terminal and JSON when stdout is piped (`--format auto`, the default). Override it with `--format human` or `--format json`. The formatting, logging, and settings switches may appear on either side of the command:

```bash
corsair --format human --no-animation doctor --settings .state/settings.json
corsair doctor --format human --no-animation --settings .state/settings.json
```

The main commands are:

```bash
corsair doctor --settings .state/settings.json
corsair investigate REQUEST.json --wait --settings .state/settings.json
corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
corsair cancel "$RUN_ID" --settings .state/settings.json

# Native reference replay; it never emits a release-facing disposition.
corsair verify REQUEST.json SUBMISSION.json --settings .state/settings.json

# Existing report paths remain explicit and stable.
corsair eval evals/datasets/dev.json --repeats 3 \
  --output .runs/evaluations/dev.json --settings .state/settings.json
corsair rescore evals/datasets/dev.json RUN_ID... \
  --output .runs/evaluations/rescored.json --settings .state/settings.json
corsair report .runs/evaluations/dev.json
```

`doctor` checks the actual Docker daemon, configured image and runtime, configured source/artifact directories, and the configured Temporal namespace/task-queue worker pollers. It does not create directories, test provider credentials, send a prompt, make a model call, or certify that a future investigation will succeed. Read the full [CLI reference](docs/cli.md) for output contracts, watch/recovery behavior, logging, and every command.

## Recovery, logs, and exits

`inspect RUN_ID` reads a committed result from the shared artifact store. `inspect RUN_ID --online` asks the live Temporal workflow for its native phase and round; `--watch` continues until the workflow’s actual result is available. Pressing Ctrl-C while a client waits detaches that client only—the remote workflow is not cancelled. Use `corsair cancel RUN_ID` to request cancellation, then inspect the final result and cleanup evidence.

Human output shows only compact operational and evidence summaries. JSON output is intended for tools. Logs always use stderr and may be mirrored as structured JSON Lines with `--log-file PATH`; use `--log-format text|json` to choose the stderr encoding. Structured JSON logs are a safe metadata allowlist; raw SDK diagnostics are suppressed, and exception logging redacts configured endpoint URLs and known credential values. With JSON logs, expected CLI errors remain JSON Lines rather than a plaintext second channel. Logs still contain operational metadata such as times and run identifiers, so store them as restricted diagnostics rather than publishing them with reports.

| Exit | Meaning |
| --- | --- |
| `0` | The command completed its stated healthy/success condition. |
| `1` | A completed check, investigation, replay, or evaluation reported an unhealthy, failed, blocked, or non-success outcome. |
| `2` | Invocation, input, settings, or local configuration error prevented normal execution. |
| `130` | The local CLI was interrupted with Ctrl-C; an in-flight remote workflow is left running unless explicitly cancelled. |

## Scope and qualification

The initial image supports standard-library Python projects only. Dependency installation, arbitrary build scripts, child-process coverage, other languages, arbitrary code-authored probes, general refutation, application-exposure proof, and stronger hostile-target attestation are not hidden fallbacks.

The original live security producer request was blocked by provider policy. That block cannot certify full live-chain accuracy. Scripted ADK episodes are confined to tests as labelled integration coverage; they are never a production model fallback. Do not evade a provider policy, silently switch providers, or turn a blocked request into a security conclusion.

Source/evidence binding, the data-only producer boundary, and the hardened container do not attest arbitrary malicious target/interpreter behavior. Read the [packaged risk assessment](src/corsair/runtime/risk.md) before admitting hostile repositories or deploying beyond a disposable personal-use sandbox.

## Project map and further reading

```text
src/corsair/
  agents/                 role-local factories, prompts, and producer tools
  contracts.py            canonical wire schema
  tools/security/         source admission, Docker SDK, trusted driver, evidence
  workflows/              deterministic Temporal coordination
  steps/                  ordinary Temporal activities
  runtime/                model assembly, worker, artifacts, manifests, risk
  policy/                 pure disposition and fix rules
  observability/          evaluator-owned scoring and reports

evals/                    frozen fixtures, datasets, evaluators, experiments
tests/                    unit, integration, workflow, replay, and security tests
docs/                     architecture, runbooks, risks, threats, development plans
deploy/                   trusted image and operator settings example
```

For operating detail, use the [pilot runbook](docs/runbooks/pilot.md). For all commands and machine-output rules, use the [CLI reference](docs/cli.md). The system design is in [architecture](docs/architecture.md); development status remains in [CURRENT](docs/development/CURRENT.md). [Implementation audit](docs/implementation-audit.md) explains the SDK cleanup and exact scope. [PLAN-0106](docs/development/plans/PLAN-0106-cli-audit.md) and [HANDOFF-0139](docs/development/handoffs/HANDOFF-0139-cli-audit.md) record the completed CLI audit and its 90-test post-cleanup qualification.
