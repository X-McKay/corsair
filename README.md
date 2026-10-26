# Corsair

Corsair validates a reported security finding against a pinned source snapshot. **Google ADK** runs two bounded agents: a producer that proposes a benign/exploit payload pair as JSON, and an outcome-blind auditor with no tools that can only reject. A deterministic, coverage-gated **kernel** in trusted code admits the target, runs the differential pair in a sandbox, requires exact target-line coverage in both runs, and decides the label. **Temporal** runs each agent episode as one activity and coordinates rounds, budgets, cancellation and immutable results. No model ever assigns a verdict.

The label is one of `EXPLOIT_DEMONSTRATED`, `COMPONENT_EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN` or `ERROR`. `EXPLOIT_NOT_DEMONSTRATED` needs at least two independent producer sessions with covered, non-demonstrating exploit runs; `EXPLOIT_DEMONSTRATED` rests on the vulnerable-revision control-versus-exploit differential, with a supplied fix revision as optional confirmation. `COMPONENT_EXPLOIT_DEMONSTRATED` is the same genuine differential proven only at the component seam when an application-scope claim's reachability to the claimed entry point was not established. Everything else is never a negative security clearance. This is a personal-use pilot whose running runtime is Python, not a general-purpose autonomous penetration tester.

## Start here

Use the locked tool shell on **Linux amd64 or macOS arm64**. Live runs also need a reviewed Docker daemon, a Temporal service and an explicitly configured model provider; a cloud development environment without those runs only the offline gates.

1. Follow [installation](docs/getting-started/installation.md) and the [quickstart](docs/getting-started/quickstart.md).
2. Establish the native, no-model reference path with `just verify` before starting a worker.
3. Run your [first durable investigation](docs/getting-started/first-project.md) with an explicitly configured model provider.

Do not admit untrusted repositories on a machine containing production workloads or credentials. Read [SECURITY.md](SECURITY.md) and the [security architecture](docs/architecture/security.md) before execution.

## Documentation

The [documentation index](docs/index.md) is the main navigation page.

| Need | Read |
| --- | --- |
| Understand the design | [Architecture overview](docs/architecture/overview.md), [components](docs/architecture/components.md), [data flow](docs/architecture/data-flow.md), [decisions](docs/architecture/decisions/0004-payload-pair-and-coverage-gated-verdict.md) |
| Develop or contribute | [Setup](docs/development/setup.md), [conventions](docs/development/conventions.md), [testing](docs/development/testing.md), [CONTRIBUTING.md](CONTRIBUTING.md) |
| Configure or integrate | [Configuration guide](docs/guides/configuration.md), [Python integration](docs/guides/integration.md), [API reference](docs/reference/api.md) |
| Operate the pilot | [Operations](docs/operations/overview.md), [deployment guide](docs/guides/deployment.md), [pilot runbook](docs/operations/runbooks/pilot.md) |
| Use the CLI | [CLI reference](docs/reference/cli.md), [monitoring](docs/operations/monitoring.md), [troubleshooting](docs/operations/troubleshooting.md) |
| Extend support | [Extension guide](docs/guides/extensions.md), [coding-agent workflows](docs/development/coding-agent-workflows.md) |
| Improve agents | [Agent development](docs/agents/development.md), [evaluations](docs/agents/evaluations.md), [safety](docs/agents/safety.md) |
| Inspect contracts or status | [Schemas](docs/reference/schemas.md), [current work and open decisions](docs/plans/README.md), [changelog](CHANGELOG.md) |

## Code map

```text
src/corsair/
  agents/          producer and auditor ADK factories, instructions, source tools and packaged skills with per-class references
  contracts/       canonical SDK-free Pydantic models: payload pair, audit result, evidence, labels, one recipe per runtime
  ports/           narrow inference, source-snapshot and sandbox interfaces
  adapters/        ADK inference, local SCM, Docker sandboxing with one trusted driver per runtime, filesystem storage and Temporal
  entrypoints/     CLI, typed Python API, worker, diagnostics; terminal.py dispatches human output to render/, one module per view family
  policies/        the deterministic kernel: gate order, verdict table, fix decisions, target and line binding, time bounds, explanations, risk assessment
  workflows/       deterministic durable coordination of episodes and gates
  steps/           activities, differential execution, coverage and receipt verification, manifests
  observability/   sanitized lifecycle logging
  evaluation/      isolated-agent evaluation, external scoring, dataset validation, gate ledger, comparison, replay, intake and previews
```

Remote forge adapters, a separate HTTP API, an OpenShell sandbox adapter, additional qualified runtimes and a general repair framework are not hidden behind this layout. The Python API and CLI share the same native workflow submission functions.

## Development checks

After [development setup](docs/development/setup.md):

```bash
just sync
just check
just test
```

| Recipe | Runs |
| --- | --- |
| `just check` | Pinned Ruff lint/format, Just formatting, ty with warnings failing, and local documentation link checks |
| `just test` | Offline tests (no Docker, Temporal or provider) |
| `just test-docker` | Real Docker sandbox tests (`CORSAIR_TEST_TEMPORAL=1` adds integrated durable tests) |
| `just test-temporal` | Real Temporal workflow and replay tests |
| `just test-live` | Explicitly configured provider tests; requires `CORSAIR_LIVE_CONFIG` |
| `just verify REQUEST SUBMISSION` | Execute a frozen reference pair through the kernel without a model |
| `just eval DATASET` | Run a durable frozen dataset through the full workflow |
| `just eval-agent AGENT DATASET` | Run an isolated producer or auditor evaluation against its frozen oracle |

Use `just -- RECIPE ...` when forwarding command flags. Native and live recipes have real prerequisites; see [testing](docs/development/testing.md).

## Qualification and limits

Gate results, unrun gates and the decisions still open with the project owner are recorded in [current work](docs/plans/README.md). A passing offline suite is not a live qualification, a small live batch is not population accuracy, and `INCONCLUSIVE`, `UNABLE_TO_RUN` or `ERROR` is never a negative finding.

Local artifacts do not survive artifact-host loss without backups or shared storage. The pilot does not establish hostile-interpreter observation integrity or production readiness. See [disaster recovery](docs/operations/disaster-recovery.md) and the [packaged risk assessment](src/corsair/policies/risk.md).

No project-wide license grant is currently specified; [LICENSE](LICENSE) records that status. Dependency licenses remain separate.
