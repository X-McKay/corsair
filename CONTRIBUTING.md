# Contributing to Corsair

Read [AGENTS.md](AGENTS.md), the [documentation index](docs/index.md) and [current work](docs/plans/README.md) before changing this repository. Check your branch and working tree; preserve unrelated changes. The project currently has no project-wide license grant—see [LICENSE](LICENSE)—and no release or production support commitment is implied by a contribution.

Start with [development setup](docs/development/setup.md), [conventions](docs/development/conventions.md) and the detailed [contribution workflow](docs/development/contributing.md). Make one bounded change, keep its plan current, and prefer existing ADK, Temporal, Pydantic and Docker SDK patterns over new infrastructure.

For every change, run the smallest meaningful checks and affected consumers. `just check` enforces Ruff, formatting and ty; `just test` is the offline gate. Prompt, schema, budget and tool changes also require the relevant frozen isolated-agent evaluation. Real Docker, Temporal and model checks qualify those boundaries separately; fixtures and skipped tests do not replace them. See [testing](docs/development/testing.md).

Before delivery: implement, test end to end at the affected boundary, clean up, retest, build/package the result and leave a self-contained handoff under [plans](docs/plans/README.md). Report failed and unrun checks, missing telemetry and remaining security limits. Include neither private logs nor credentials, raw source/evidence exports, model reasoning, `.state/` or `.runs/` in commits or shared packages.

Do not modify operator policies or weaken TLS, sandboxing, evidence gates or labels to obtain a pass. Security-sensitive findings follow [SECURITY.md](SECURITY.md), not a public issue with reproduction secrets. Publication, deployment and issue closure follow the user's current authorization.
