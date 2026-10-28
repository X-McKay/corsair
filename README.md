# Corsair

Corsair investigates a reported security finding against a pinned source snapshot. **Google ADK** runs bounded producer and outcome-blind auditor episodes; **Temporal** coordinates durable rounds, budgets, cancellation, and immutable results. Trusted code records process evidence; model proposals do not establish security conclusions.

New investigations are [recipe-free](docs/guides/investigations.md): intake normalizes an issue, stops unsupported/out-of-scope inputs and selects a currently available image; producer and auditor episodes create and review bounded test plans; accepted code and commands run only in the configured Docker sandbox. Process results and semantic audit are separate. Security assessment remains `UNRESOLVED` without independent property evidence.

This is a personal-use pilot. Historical Python, Node and Java fixed-observer schemas and frozen evaluations remain for explicit diagnostics and replay. Current qualification and failures are recorded in [active work](docs/plans/README.md); native conformance does not establish model reliability or production readiness.

## Start here

Use the locked Nix tool shell on **Linux amd64 or macOS arm64**. You also need a reviewed Docker daemon or Linux VM; Nix does not provision Docker or Temporal persistence.

1. Follow [installation](docs/getting-started/installation.md) and [quickstart](docs/getting-started/quickstart.md).
2. Establish the native, no-model reference path before starting a worker.
3. Run your [first durable investigation](docs/getting-started/first-project.md) with an explicitly configured model provider.

Do not admit untrusted repositories on a machine containing production workloads or credentials. Read [SECURITY.md](SECURITY.md) and the [security architecture](docs/architecture/security.md) before execution.

## Documentation

The [documentation index](docs/index.md) is the navigation hub.

| Need | Read |
| --- | --- |
| Understand the design | [Architecture overview](docs/architecture/overview.md), [components](docs/architecture/components.md), [decisions](docs/architecture/decisions/0001-sdk-owned-durable-rounds.md) |
| Develop or contribute | [Setup](docs/development/setup.md), [conventions](docs/development/conventions.md), [testing](docs/development/testing.md), [CONTRIBUTING.md](CONTRIBUTING.md) |
| Configure or integrate | [Configuration](docs/guides/configuration.md), [language recipes](docs/guides/languages.md), [Python integration](docs/guides/integration.md), [API reference](docs/reference/api.md) |
| Operate the pilot | [Operations](docs/operations/overview.md), [deployment guide](docs/guides/deployment.md), [pilot runbook](docs/operations/runbooks/pilot.md) |
| Use the CLI | [CLI reference](docs/reference/cli.md), [monitoring](docs/operations/monitoring.md), [troubleshooting](docs/operations/troubleshooting.md) |
| Extend support | [Extension guide](docs/guides/extensions.md), [language recipe gates](docs/guides/languages.md), [coding-agent workflows](docs/development/coding-agent-workflows.md) |
| Improve agents | [Agent development](docs/agents/development.md), [evaluations](docs/agents/evaluations.md), [safety](docs/agents/safety.md) |
| Inspect contracts or status | [Schemas](docs/reference/schemas.md), [configuration](docs/reference/configuration.md), [active work and evidence](docs/plans/README.md), [changelog](CHANGELOG.md) |

## Code map

```text
src/corsair/
  agents/          role-local ADK factories, metadata, contract views, tools and runtime skills
  contracts/       canonical SDK-free Pydantic models
  ports/           narrow inference, source-snapshot and sandbox interfaces
  adapters/        real inference, SCM, sandboxing, storage and Temporal integrations
  entrypoints/     CLI, typed Python API, worker, terminal and diagnostics
  policies/        pure verdict/fix decisions and packaged risk assessment
  workflows/       deterministic durable coordination
  steps/           application/activity execution, evidence verification and manifests
  observability/   sanitized lifecycle logging
  evaluation/      isolated-agent evaluation and external scoring
```

Remote forge adapters, a separate HTTP API, a generic language/framework runtime, and a general repair framework are not hidden behind this layout.

## Development checks

After [development setup](docs/development/setup.md):

```bash
nix develop
just sync
just check
just -- test -q -W error
```

`just check` runs pinned Ruff lint/format, Just formatting, ty, and local documentation checks. The aggregate `just images` task builds all three reviewed observers. Per-language candidate task syntax is documented in [language recipes](docs/guides/languages.md): `just images-node 'TAG'` and `just images-java 'TAG'`; those tasks do not themselves establish native qualification. Native execution and live-provider checks have separate prerequisites—see [testing](docs/development/testing.md).

## Qualification and limits

Historical qualification records remain revision-specific evidence; [current plans](docs/plans/README.md) retain passing, failed and unrun gates. V3 success means expected process exits in the admitted environment, not demonstrated exploitability. Fixed-source results are process comparisons. Legacy paired outcomes keep their original finite-protocol interpretation.

Local artifacts do not survive artifact-host loss without backups or shared storage. The pilot does not establish hostile-interpreter observation integrity or production readiness. See [disaster recovery](docs/operations/disaster-recovery.md) and the [packaged risk assessment](src/corsair/policies/risk.md).

No project-wide license grant is currently specified; [LICENSE](LICENSE) records that status. Dependency licenses remain separate.
