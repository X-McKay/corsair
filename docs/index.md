# Corsair documentation

Corsair is a personal-use security-investigation pilot built on Google ADK and Temporal. These pages describe **implemented behavior**, not a generic agent platform. Begin with native reference replay, then explicitly configure a provider before running a durable investigation. [Current work and qualification](plans/README.md) records both passing and failed gates.

## Getting started

- [Installation](getting-started/installation.md): supported platforms and prerequisites.
- [Quickstart](getting-started/quickstart.md): establish the trusted no-model native path.
- [First project](getting-started/first-project.md): run a first durable investigation with a real worker and provider.

## Architecture

- [Overview](architecture/overview.md): design goals, boundaries and non-goals.
- [System context](architecture/system-context.md): operator, model provider, Temporal, source and sandbox relationships.
- [Components](architecture/components.md): where implemented code lives and who owns each responsibility.
- [Data flow](architecture/data-flow.md): requests, kernel gates, differential runs, coverage, blind audit and the verdict table.
- [Deployment architecture](architecture/deployment.md): process/storage boundaries and their durability limits.
- [Security architecture](architecture/security.md): trust boundaries, evidence gates and residual risk.

Recorded architecture decisions describe implemented choices:

1. [SDK-owned durable rounds](architecture/decisions/0001-sdk-owned-durable-rounds.md).
2. [Canonical Pydantic contracts and narrow ports](architecture/decisions/0002-pydantic-contracts-and-ports.md).
3. [Immutable native evidence](architecture/decisions/0003-immutable-native-evidence.md).
4. [Payload pair, coverage-gated kernel, and six labels](architecture/decisions/0004-payload-pair-and-coverage-gated-verdict.md).
5. [Outcome-blind retry feedback carries no role-attributed run fact](architecture/decisions/0005-outcome-blind-retry-feedback.md) (proposed).

## Development

- [Setup](development/setup.md): locked Nix/uv/Just workflow and native platform prerequisites.
- [Local files and retention](development/local-files.md): environment, persistence, private evidence and safe scratch cleanup.
- [Conventions](development/conventions.md): ownership, naming, typed boundaries and SDK-first implementation.
- [Testing](development/testing.md): quality, isolated agents, native dependencies and package gates.
- [Debugging](development/debugging.md): attributable failures and safe diagnostics.
- [Contributing](development/contributing.md): bounded changes, reviews, handoffs and final delivery.
- [Claude Code/Codex workflows](development/coding-agent-workflows.md): shared development and evaluation skills with concrete commands.

Root [AGENTS.md](../AGENTS.md) is the repository instruction entrypoint; [CONTRIBUTING.md](../CONTRIBUTING.md) is the human contribution entrypoint.

## Guides

These pages explain how to perform a task; exact signatures/defaults live in reference.

- [Configuration](guides/configuration.md).
- [Pilot deployment](guides/deployment.md).
- [Python integration](guides/integration.md).
- [Advanced usage](guides/advanced-usage.md).
- [Add a language, framework, recipe or image](guides/extensions.md): a consistent implementation and qualification checklist, not currently supported runtimes.

## Operations

- [Overview](operations/overview.md): prerequisites and daily operating boundaries.
- [Monitoring](operations/monitoring.md): CLI progress, sanitized lifecycle logs and unknown metrics.
- [Troubleshooting](operations/troubleshooting.md): distinguish admission, provider, native execution and cleanup failures.
- [Disaster recovery](operations/disaster-recovery.md): worker restart versus missing artifact storage or uncertain effects.
- [Pilot runbook](operations/runbooks/pilot.md): the actual supported operating procedure, not a generic example.

## Reference

- [Python API](reference/api.md): implemented library functions; there is no separate HTTP server.
- [CLI](reference/cli.md): commands, switches, output contracts and exits.
- [Configuration](reference/configuration.md): canonical settings and constraints.
- [Schemas](reference/schemas.md): canonical Pydantic models and schema inspection.
- [Ruby corpus survey](reference/corpus-ruby.md): the Ruby rows, their properties, and the one migrated, qualified row.
- [Python corpus map](reference/corpus-python.md): which recipe each Python corpus row's property needs.
- [Glossary](reference/glossary.md): domain terms and result meanings.
- [Platforms](reference/platforms.md): Linux amd64/macOS arm64 support and native qualification boundaries.
- [JavaScript corpus survey](reference/corpus-javascript.md): the JavaScript rows and why the prototype-pollution recipe is qualified first.
- [Perl corpus survey](reference/corpus-perl.md): the Perl rows, their properties, and the qualified `perl.html_injection/1` row.

## Agents

- [Overview](agents/overview.md): producer and outcome-blind auditor roles.
- [Development](agents/development.md): bounded changes and native structured output.
- [Tools and skills](agents/tools-and-skills.md): source capabilities versus private procedural loaders.
- [Role-local packages and runtime skills](guides/agent-packages.md): native ADK composition, packaged guidance and finite admission.
- [Evaluations](agents/evaluations.md): frozen isolated-agent improvement before composition.
- [Safety](agents/safety.md): data-only proposals, oracle separation and operator policy.

## Plans, project policy and history

[Current work](plans/README.md) links the project plan, its open decisions and the latest evidence.

See [SECURITY.md](../SECURITY.md) for reporting and safe operation, [CHANGELOG.md](../CHANGELOG.md) for unreleased changes, and [LICENSE](../LICENSE) for the current absence of a project-wide license grant. The [packaged risk assessment](../src/corsair/policies/risk.md) remains part of the implementation's capability identity.
