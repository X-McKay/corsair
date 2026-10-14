---
id: PLAN-0097
kind: plan
title: Build Corsair v2 with native libraries
status: in_progress
updated: 2026-10-14
related: [SPEC-0082, SPEC-0081, ISSUE-0009]
---

# Build Corsair v2 with native libraries

## Objective and dependencies

Implement [SPEC-0082](../specs/SPEC-0082-corsair-v2.md) on `manus-test`, from main `14715eab1ca4b9ff778636987601d48a443779cc`, with no website, placeholder tools, fake production adapters, or silently downgraded qualification. Official native API research precedes vendor-dependent implementation. Core contracts, evidence storage, and CLI/report semantics can proceed while that research runs.

## Steps

- [x] Resolve exact native PydanticAI/Harness, Temporal, OpenShell, Pydantic Evals/telemetry and open-source dataset APIs; source-cited choices are recorded in [native-upstream decisions](../../v2/newupstream-decisions.md) and [architecture](../../v2/newarchitecture.md).
- [x] Implement versioned v2 contracts, immutable source/artifact identities, durable append-only evidence and deterministic dispositions. The parent owns its current frozen-code validation; this doc lane did not rerun tests.
- [x] Compose native agents/Harness tools/skills and independent frozen probe author/reviewer roles, with operator-owned limits and per-role observable usage. Model/tool quality remains provider-specific.
- [x] Implement the OpenShell lifecycle/workspace boundary, bounded transfers/commands and identity-aware cleanup/reconciliation. **Qualification remains gated**; the selected local Docker profile is explicitly unqualified, and no host fallback is admitted.
- [x] Implement one native Temporal workflow, worker, durable submission/status/cancel/history replay wiring, and operation-specific retry/cancellation handling. **Live service execution/recovery/replay evidence remains pending the parent validation record.**
- [x] Implement benchmark imports and native Pydantic Evals tasks/evaluators, report projections, compatible comparisons and baseline-reference controls. A prior public-development pilot is not a holdout or production result.
- [ ] Parent: complete the authorized frozen-policy live validation for model/provider, OpenShell target host/workload, Temporal execution/recovery and actual outputs; retain actual logs/results and write [docs/v2/validation.md](../../v2/validation.md). This docs lane asserts no final counts/results.
- [x] Deliver CLI/operator docs, packaged-asset code, and this plan/spec/current/handoff update. Parent still owns end-of-run record checks, live-results documentation and any final retest/publication decision.

## Validation and progress

2026-10-14: refreshed origin; requested branch did not exist and was created from main. `uv sync --frozen` installed the existing pinned core2.55.0/Harness0.55.0/Evals2.55.0/Temporal1.34.0/OpenShell0.1.3 environment. This is installation, not integration qualification.

Baseline `uv run pytest tests/configuration -q -n 4`: **292 passed in 47.23s**. No legacy source changed at this checkpoint.

Sandbox prerequisite checks: Ubuntu kernel6.18.38+, unprivileged namespace creation succeeded, administrative capabilities are available. Installed Docker and started a project-specific daemon/socket/data directory outside the repository. Docker29.1.3 created a real capability-dropped, network-denied BusyBox container; the command returned `corsair-container-admission-ok`. This proves container execution only, not OpenShell confinement or gateway behavior. Native upstream research is completed and the selected paths are summarized in the v2 ADRs. Prior model trials remain preliminary; the current frozen-policy validation is parent-owned.

## Decisions and next action

Use `src/corsair/v2/` as one cohesive new implementation inside the existing distribution. Preserve v1 source and historical evals without routing new commands to them automatically. Reuse tested immutable storage/source principles and existing framework report parsers where their contracts fit; do not add another scheduler, graph library, custom provider protocol or tracing system. User requires both agent-local iteration and language-stratified system evaluation.

Do not count unit doubles, model mocks, installed packages, or Docker smoke as OpenShell/Temporal/model end-to-end success. A native API/permission failure stops dependent qualification, not independent implementation. Preserve LocalArtifacts+POSIX CAS/SQLite-WAL as a single-host execution domain; no PostgreSQL/S3/multi-host storage adapter is delivered. Parent next records actual frozen-policy live evidence, leaves unknowns/failures explicit, then runs record/docs guards. A local OpenShell profile remains unqualified until the exact target host/profile is admitted.
