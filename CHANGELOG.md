# Changelog

This file describes unreleased work in the current redesign. It is not a declaration that the working tree has been committed, published or released. Dated implementation/qualification records live in [plans and archives](docs/plans/README.md).

## Unreleased

### Documentation

- Organize documentation into getting-started, architecture and decisions, development, guides, operations and runbooks, reference, agents, and active/archived plans.
- Add concise root contribution, security and license-status entrypoints, with a single documentation index.
- Preserve historical plans, failed attempts, handoffs and review evidence separately from current guidance.

### Implementation in the current local redesign

- Use native ADK Pydantic structured producer output with nested `PlanRevision`; remove custom submit state and strict-validation string repair temptations.
- Separate domain contracts, actual typed ports, SDK adapters, entrypoints, pure policies, durable workflows, steps, logs and evaluation.
- Share native Temporal submission between CLI and the typed Python API; remove retired runtime/security namespaces instead of shipping compatibility shims.
- Retain Just tasks, locked Nix tooling for Linux amd64/macOS arm64, pinned Ruff and ty, native evidence/cleanup gates and frozen isolated-agent evaluation.

### Known limitations

The live three-case model/native batch is partially qualified at 2/3. An invalid safe-case follow-up probe remains an explicit execution error under [ISSUE-0010](docs/plans/active/ISSUE-0010-live-safe-case-probe.md). No population accuracy, general hostile-target integrity, remote SCM support, HTTP service, additional languages or production artifact-host-loss recovery is claimed.


### Boundary and local-state consolidation

Private/generated data and deliverables are Git-ignored. The worker explicitly composes concrete adapters; shared source normalization no longer depends on CLI code, and agent factories use native SDK model types directly. Local documentation/import/privacy checks are maintained gates. A canonical root environment and verified private state/history locations replace dated task environment/persistence dependencies. Expanded AI-authored diagnostic candidates expose retained producer exact-payload failures; qualification receipts remain separate from promoted baselines. No release or production qualification is asserted.

### Role-local agents and native procedural resources

- Added producer/auditor controlled factories, native toolsets, canonical contract views and packaged runtime procedure skills; source tools have separate modules.
- Guaranteed core procedure context through native ADK loading before generation, with separate preload and actual model-requested load accounting.
- Bound runtime resource bytes to capability/evaluation identity, preserved remaining-root auditor budget admission and old-history command compatibility via a native Temporal patch.
- Recorded209 passing physical-Mac native tests and the still-unpromoted frozen/full-live quality misses; no release or production-readiness claim is made.
