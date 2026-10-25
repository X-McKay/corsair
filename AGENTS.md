# Corsair development instructions

Follow current user authorization. This branch implements the accepted durable-round ADK + Temporal redesign and supersedes v2's retired framework/negative-count rules here only. Read README.md and docs/development/CURRENT.md before work. Preserve unrelated changes and inspect the branch/status.

## Ownership and organization

Google ADK owns agent execution; Temporal owns durable coordination. Workflows must perform no filesystem, model, network or Docker I/O. Ordinary activities own those boundaries. Private factories, instructions, declarative metadata and tools stay under agents/<role>. Shared contracts have one definition in contracts.py. Shared runtime and security tools are owned by the Corsair maintainer; do not add generic ports/backends or empty folders without a real second consumer.

Use installed, pinned native SDK APIs first. Do not implement a second agent loop, graph, scheduler, retry broker, tracing stack, checkpoint engine, or duplicate schema. Keep the requested playbook directory mapping. Runtime resources must be loaded from the built package, not the checkout working directory. Development skills, if added later, belong under .agents/skills; runtime skills do not.

## Evidence and security

The initial recipe admits JSON payload proposals, never model-authored execution/assertions. Only trusted evidence code can produce observations. Untrusted target code runs only in the configured Docker sandbox, never on the host. Keep source/tooling read-only, credentials/socket outside containers, network and resource limits enforced, and cleanup bound to immutable container identity.

Failed reproduction never permits REFUTED/non-exploitable. Missing evidence, native reports, coverage, unexpected exceptions, provider errors, lost hosts, and uncertain completion must remain explicit. Scope is component unless an admitted application recipe proves otherwise. An outcome-blind auditor can veto semantic validity, not create factual evidence or authorize publication. Oracles never reach agent, tool or workflow inputs.

Do not claim generic hostile-source observation integrity, exactly-once execution, full host-loss continuation, broad patch verification, or production readiness based on mocks or configuration. New recipes, permissions, languages, backend/runtime or model changes require affected conformance/evaluation and a new configuration identity.

## Development workflow

Implement a bounded component; test it and its consumers. Evaluate producer/auditor independently with genuine ADK and frozen fixture cases before calling composition qualified. Distinguish scripted, live-model fixture, real Docker, real Temporal and full live-chain results.

Before delivery: test end to end, review concrete boundaries, remove dead code/generated private artifacts, re-test, build the wheel, load its resources outside the checkout, and update the current plan/handoff with actual commands/results and failed/unrun gates. Publish only within user authorization. Never commit .runs, .state, credentials, private diagnostics or raw reasoning. Missing usage/cost stays unknown, not zero.

Use `make check` before delivery: pinned Ruff lint/format plus pinned ty, with type warnings failing CI. No broad typing ignores. Frozen fixtures retain declared hashes/line numbers and are not Ruff style targets; typing and native conformance still cover them. Keep functions named for one ownership boundary and prefer concrete composition over speculative mixins. Treat dead-code scans as candidates: verify SDK callback/schema usage before deletion. Re-run the affected unit/native tests and a final frozen evaluation after refactoring; report narrow performance measurements without claiming overall agent speedup.
