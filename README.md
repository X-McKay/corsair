# Corsair

Corsair investigates a reported security finding against a pinned source snapshot. **Google ADK** runs bounded producer and outcome-blind auditor episodes; **Temporal** coordinates durable rounds, budgets, cancellation and immutable results. Trusted native evidence—not either model—determines the scoped disposition.

This is a personal-use pilot for `python.secret_disclosure/1`, not a general-purpose autonomous penetration tester. It currently admits standard-library Python callables and data-only JSON proposals, executed by a trusted observer in offline Docker containers. `SUPPORTED` is component evidence; an application-level claim with only component evidence is `CONDITIONAL`. A failed reproduction stays `INCONCLUSIVE`, never a negative security clearance.

## Start here

Use the locked Nix tool shell on **Linux amd64 or macOS arm64**. You also need a reviewed Docker daemon or Linux VM; Nix does not provision either Docker or Temporal persistence.

1. Follow [installation](docs/getting-started/installation.md) and the [quickstart](docs/getting-started/quickstart.md).
2. Establish the native, no-model reference path before starting a worker.
3. Run your [first durable investigation](docs/getting-started/first-project.md) with an explicitly configured model provider.

Do not admit untrusted repositories on a machine containing production workloads or credentials. Read [SECURITY.md](SECURITY.md) and the [security architecture](docs/architecture/security.md) before execution.

## Documentation

The [documentation index](docs/index.md) is the main navigation page.

| Need | Read |
| --- | --- |
| Understand the design | [Architecture overview](docs/architecture/overview.md), [components](docs/architecture/components.md), [decisions](docs/architecture/decisions/0001-sdk-owned-durable-rounds.md) |
| Develop or contribute | [Setup](docs/development/setup.md), [conventions](docs/development/conventions.md), [testing](docs/development/testing.md), [CONTRIBUTING.md](CONTRIBUTING.md) |
| Configure or integrate | [Configuration guide](docs/guides/configuration.md), [Python integration](docs/guides/integration.md), [API reference](docs/reference/api.md) |
| Operate the pilot | [Operations](docs/operations/overview.md), [deployment guide](docs/guides/deployment.md), [pilot runbook](docs/operations/runbooks/pilot.md) |
| Use the CLI | [CLI reference](docs/reference/cli.md), [monitoring](docs/operations/monitoring.md), [troubleshooting](docs/operations/troubleshooting.md) |
| Extend support | [Extension guide](docs/guides/extensions.md), [coding-agent workflows](docs/development/coding-agent-workflows.md) |
| Improve agents | [Agent development](docs/agents/development.md), [evaluations](docs/agents/evaluations.md), [safety](docs/agents/safety.md) |
| Inspect contracts or status | [Schemas](docs/reference/schemas.md), [active work and evidence](docs/plans/README.md), [changelog](CHANGELOG.md) |

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

Remote forge adapters, a separate HTTP API, additional languages and a general repair framework are not hidden behind this layout. The Python API and CLI share the same native workflow submission functions.

## Development checks

After [development setup](docs/development/setup.md):

```bash
nix develop
just sync
just check
just test
```

`just check` runs pinned Ruff lint/format, Just formatting, ty and local documentation checks; type warnings fail the gate. Native execution and live-provider tests have separate real prerequisites—see [testing](docs/development/testing.md). Use `just -- RECIPE ...` when forwarding command flags.

## Qualification and limits

`manus/just` includes all eight latest recommendation heads and the role-local agent layout. Each role owns its native factory, typed metadata, canonical contract views, instructions, toolsets and private procedural skills. The producer's source tools have one file each; the auditor has no source/external tools. Final physical-Mac native qualification passed **209 tests before and after cleanup**, including real Docker, Temporal, replay, CLI, live-auditor and installed-wheel checks. See [current evidence](docs/plans/README.md).

Required core procedures are native-ADK-loaded into instructions before generation, with honest preload versus model-requested tool-use logs. Context loading is not model compliance: the current frozen expanded producer scored **3/9**, auditor **6/12**, and the fresh full-live batch scored **2/3** with zero operational failures. No live-model baseline was promoted; [ISSUE-0013](docs/plans/active/ISSUE-0013-runtime-procedure-live-quality.md) and [ISSUE-0012](docs/plans/active/ISSUE-0012-producer-decision-live-quality.md) retain the misses. Earlier3/3 composition and12/12 auditor results remain revision-specific evidence, not current accuracy. Failed reproduction never becomes negative security clearance.

Local artifacts do not survive artifact-host loss without backups or shared storage. The pilot does not establish hostile-interpreter observation integrity or production readiness. See [disaster recovery](docs/operations/disaster-recovery.md) and the [packaged risk assessment](src/corsair/policies/risk.md).

No project-wide license grant is currently specified; [LICENSE](LICENSE) records that status. Dependency licenses remain separate.
