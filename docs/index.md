# Corsair documentation

Corsair is a personal-use security-investigation pilot built on Google ADK and Temporal. These pages describe implemented behavior and explicit pending gates, not a generic agent platform. Begin with native reference replay, then explicitly configure a provider before a durable investigation. [Current work and qualification](plans/README.md) records evidence without rewriting historical records.

## Getting started

- [Installation](getting-started/installation.md): supported platforms and prerequisites.
- [Quickstart](getting-started/quickstart.md): establish the trusted no-model native path.
- [First project](getting-started/first-project.md): run a durable investigation with a real worker and provider.

## Architecture

- [Overview](architecture/overview.md): design goals, boundaries, and non-goals.
- [System context](architecture/system-context.md): operator, model provider, Temporal, source, and sandbox relationships.
- [Components](architecture/components.md): package ownership, recipe-aware images, and evidence boundaries.
- [Data flow](architecture/data-flow.md): requests, bounded agent rounds, native receipts, and scoped results.
- [Deployment architecture](architecture/deployment.md): process/storage boundaries and durability limits.
- [Security architecture](architecture/security.md): trust boundaries, evidence gates, and residual risk.

Recorded decisions describe implemented choices:

1. [SDK-owned durable rounds](architecture/decisions/0001-sdk-owned-durable-rounds.md).
2. [Canonical Pydantic contracts and narrow ports](architecture/decisions/0002-pydantic-contracts-and-ports.md).
3. [Immutable native evidence](architecture/decisions/0003-immutable-native-evidence.md).

## Development

- [Setup](development/setup.md): locked Nix/uv/Just workflow and platform prerequisites.
- [Local files and retention](development/local-files.md): environment, persistence, private evidence, and scratch cleanup.
- [Conventions](development/conventions.md): ownership, typed boundaries, and SDK-first implementation.
- [Testing](development/testing.md): quality, isolated agents, pending language-native selections, and package gates.
- [Debugging](development/debugging.md): attributable failures and safe diagnostics.
- [Contributing](development/contributing.md): bounded changes, reviews, handoffs, and delivery.
- [Claude Code/Codex workflows](development/coding-agent-workflows.md): shared development/evaluation skills and commands.

Root [AGENTS.md](../AGENTS.md) is the repository instruction entrypoint; [CONTRIBUTING.md](../CONTRIBUTING.md) is the human contribution entrypoint.

## Guides

- [Recipe-free investigations](guides/investigations.md): automatic intake gates, pinned sandbox images, test plans, categorical audit and process evidence.

Guides explain tasks; exact fields/defaults remain in reference.

- [Configuration](guides/configuration.md).
- [Language recipes and qualification](guides/languages.md): Python and the narrow Node/Java candidate ABIs, image tasks, paired outcomes, and pending gates.
- [Pilot deployment](guides/deployment.md).
- [Python integration](guides/integration.md).
- [Advanced usage](guides/advanced-usage.md).
- [Extend safely](guides/extensions.md): concrete implementation/qualification checklist, not a promise of extra runtimes.

## Operations

- [Overview](operations/overview.md): prerequisites and daily operating boundaries.
- [Monitoring](operations/monitoring.md): CLI progress, sanitized lifecycle logs, and unknown metrics.
- [Troubleshooting](operations/troubleshooting.md): admission, provider, native execution, and cleanup failures.
- [Disaster recovery](operations/disaster-recovery.md): worker restart versus missing artifact storage or uncertain effects.
- [Pilot runbook](operations/runbooks/pilot.md): the supported operating procedure.

## Reference

- [Python API](reference/api.md): implemented library functions; no separate HTTP server.
- [CLI](reference/cli.md): commands, switches, output contracts, and exits.
- [Configuration](reference/configuration.md): canonical settings, recipe-image selection, and baseline-doctor limits.
- [Schemas](reference/schemas.md): Pydantic recipe/result/evidence models and schema inspection.
- [Glossary](reference/glossary.md): domain terms and result meanings.
- [Platforms](reference/platforms.md): platform support and native qualification boundaries.

## Agents

- [Issue intake](agents/intake.md): bounded issue normalization, available-image recommendations, categorical admission and frozen evaluation.

- [Overview](agents/overview.md): producer and outcome-blind auditor roles.
- [Development](agents/development.md): bounded changes and native structured output.
- [Tools and skills](agents/tools-and-skills.md): source capabilities versus private procedural loaders.
- [Role-local packages and runtime skills](guides/agent-packages.md): ADK composition, packaged guidance, and finite admission.
- [Evaluations](agents/evaluations.md): frozen role improvement, versioned outcome cohorts, and scorer limits.
- [Safety](agents/safety.md): data-only proposals, oracle separation, and operator policy.

## Plans, policy, and history

[Current work](plans/README.md) links active plans/issues and latest evidence. [Archives](plans/archive/README.md) preserve historical plans, handoffs, and reviews without presenting old commands as current guidance.

See [SECURITY.md](../SECURITY.md) for reporting and safe operation, [CHANGELOG.md](../CHANGELOG.md) for unreleased changes, and [LICENSE](../LICENSE) for the current absence of a project-wide license grant. The [packaged risk assessment](../src/corsair/policies/risk.md) remains part of the implementation capability identity.
