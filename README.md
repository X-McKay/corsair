# Corsair

Corsair investigates a reported security finding against a pinned source snapshot. Google ADK runs a bounded producer and an outcome-blind auditor inside ordinary Temporal activities. Temporal coordinates rounds, budgets, cancellation, and immutable results. Trusted code—not either agent—admits observations and determines the scoped disposition.

This branch is a from-scratch implementation of **Plan 1: durable investigation rounds**. It does not use the experimental native ADK–Temporal integration or a custom agent checkpoint engine. A completed activity is durable; an unfinished ADK episode is not resumable at every model call.

## Supported first slice

The initial recipe is `python.secret_disclosure/1`: a Python public callable receives a JSON payload, with operator-fixed keyword arguments. Trusted native pytest/coverage tooling runs a benign and adversarial input in fresh offline containers. A private random fixture is created independently of the producer; the observer checks whether the target returned it. The producer can read admitted source and submit payloads, but cannot author assertions or executable probe code.

The initial image supports standard-library Python projects. Dependency installation, arbitrary build scripts, child-process coverage, other languages, arbitrary probes, and general refutation are deliberately unsupported. These are capability additions requiring new recipes and conformance cases—not hidden fallbacks.

`SUPPORTED` means a violation was demonstrated within component scope. An application-level claim remains `CONDITIONAL` when only its component API was exercised. Failed reproduction is `INCONCLUSIVE`, never `REFUTED` merely because several attempts failed. Build/runtime/host failures remain operational statuses. A fix result means this demonstration was blocked while the benign behavior survived; it is not a universal patch-correctness claim.

The native observer is protected from model-authored code by accepting data-only submissions. It is not attestation of arbitrary malicious target/interpreter behavior. Read the [packaged risk assessment](src/corsair/runtime/risk.md) before admitting hostile repositories or deploying beyond a disposable personal-use sandbox.

## Quick start

Requirements: Python 3.12+, `uv`, an actual Docker daemon, and a Temporal service. Use a dedicated disposable Ubuntu/Debian sandbox host, not a host with sensitive workloads. Docker credentials/socket access must never reach target containers.

```bash
make sync
make check
make test
make images
make test-docker

mkdir -p .state
# Separate terminal. Persistent SQLite is for development, not production.
temporal server start-dev --db-filename .state/temporal.db

# Configure worker-side models; provider credentials stay in environment.
cp deploy/settings.example.json .state/settings.json
# Edit model connector/name and source_root as needed, then:
uv run --locked --extra providers corsair worker --settings .state/settings.json

# A second terminal, same artifact root and source-root policy:
uv run --locked --extra providers corsair investigate \
  evals/fixtures/case01/request.json --settings .state/settings.json --wait
```

The worker and client must share access to the configured artifact root. The pilot uses one host/task queue. A local artifact path is not recoverable after host loss; choose shared durable storage before promising that recovery level. Production Temporal requires an appropriate persistence backend or Temporal Cloud, not the dev server.

If the optional LiteLLM connector is selected, install `--extra providers` and set its usual provider credentials, such as `OPENAI_API_KEY` or AWS worker identity. The endpoint belongs in `models.api_base`, not workflow inputs. Gemini uses the standard ADK credential configuration. No credentials are included in the settings example.

## CLI

```bash
corsair investigate request.json --wait --settings settings.json
corsair inspect RUN_ID --settings settings.json           # committed local result
corsair inspect RUN_ID --online --settings settings.json  # Temporal phase and round
corsair cancel RUN_ID --settings settings.json

# Native reference replay, no model and no release-facing verdict:
corsair verify evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json --settings settings.json

# Oracle labels stay in the external evaluator, outside workflow/agent inputs:
corsair eval evals/datasets/dev.json --repeats 3 --settings settings.json
corsair rescore evals/datasets/dev.json RUN_ID... --settings settings.json
corsair report .runs/evaluations/REPORT.json
```

Commands emit JSON on stdout. Diagnostics use stderr and invalid configuration returns a nonzero exit. Submission acceptance is not security verification. Cancellation requests are not proof of cleanup; evidence activities wait for their owning sandbox thread to stop/remove resources.

## Directory structure

The layout follows the requested [playbook reference architecture](https://github.com/X-McKay/playbooks/blob/main/agent-playbook%2F02-reference-architecture.md), without empty catalogs or duplicate schemas:

```text
src/corsair/
  agents/producer/        factory, private tools, agent.json, instructions
  agents/auditor/         factory, agent.json, instructions
  contracts.py           one canonical shared wire schema
  tools/security/        source admission, Docker SDK, trusted native driver, evidence
  workflows/             deterministic investigation and bounded evaluation fan-out
  steps/                 ordinary Temporal activities
  runtime/               model/runner assembly, worker, artifacts, manifests, packaged risk
  policy/                pure disposition and fix rules
  observability/         authoritative scorer and report aggregation
  settings.py, cli.py

evals/
  datasets/              digest-frozen case/oracle references with family-grouped splits
  fixtures/              reviewed source pairs, submissions, evaluator-only oracles
  evaluators/            isolated agent evaluation entry point
  experiments/           instructions for comparison, not committed private runs
  baselines/             explicit qualification status, no invented live baseline

tests/{unit,integration,workflow,replay,security}/
docs/{risk-assessments,threat-models,runbooks,development}/
deploy/                  settings and trusted image build
```

Agent JSON files are declarative capability metadata referencing Python contracts. They do not duplicate the Python field schemas or contain secrets. Factories validate the admitted tool surface; the manifest identifies spec, instruction, output schema, risk assessment, image, model configuration and budget identities. Private tools stay beside their agent. Shared security/runtime components are owned by the Corsair maintainer.

## Evaluation and contribution

Use four different reruns for four different changes: rescore saved observations for policy changes; replay frozen submissions for driver/image changes; run fresh agents for prompt/model/tool changes; replay Temporal history for workflow changes. Exact tool-trajectory matching is not the security oracle.

Start with native reference conformance, then scripted genuine-ADK integration, isolated auditor cases, and finally frozen live investigations with repeats. Keep blocked/invalid/unavailable attempts in the denominator. Unknown token usage and cost stay `null`. The small authored pilot fixtures diagnose behavior; they are not evidence of a low population-wide error rate.

See [development status](docs/development/CURRENT.md), [the implementation plan](docs/development/plans/PLAN-0105-adk-temporal-redesign.md), and [the runbook](docs/runbooks/pilot.md). Follow [AGENTS.md](AGENTS.md): implement, test end to end, clean up, re-test, and verify the built artifact before delivery.
