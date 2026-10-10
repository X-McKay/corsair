---
name: corsair-development
description: Use when planning, implementing, debugging, or resuming development in the Corsair repository. Follow the shared principles, bounded component workflow, standard work records, progressive qualification, and proportionate validation.
---

# Corsair development

Resolve paths from the repository root. Read `AGENTS.md`, `docs/development/README.md` and `docs/development/CURRENT.md` first. Skills guide work; they do not add authority or approval requirements.

## Resume and define the change

1. Inspect the branch, working tree and relevant source. Read the active plan, linked issue/spec and latest handoff. Reconcile stale context with actual files and evidence before acting.
2. State the bounded objective and failing behavior or acceptance criterion. Locate the current milestone gate and affected component. Preserve unrelated edits.
3. Reuse an existing work record where possible. For substantial behavior/boundary changes, create a spec and implementation plan from `docs/development/templates/`. Ideas are optional and do not authorize implementation. Small corrections can update an existing plan/issue without new paperwork.
4. Verify SDK capabilities and pinned versions before designing a wrapper. Record why native functionality is insufficient if bespoke code is necessary. Keep contract changes, authority, mode/provider differences, failure attribution and validation explicit.

## Implement progressively

1. Make the smallest independently reviewable change. Keep the current plan's ordered steps, decisions and validation notes up to date.
2. Exercise the component alone first. Use native test/override facilities for contracts and real qualification for external boundaries. Do not hide an unavailable live prerequisite with a mock or fallback.
3. For agent changes, select relevant evaluation dimensions from `docs/evaluation-and-acceptance.md`. Use saved inputs, frozen cases and native instrumentation; record modes, repeat counts, usage/trace coverage and regression evidence.
4. When blocked, retain the command/native error and evidence reference, open/update the repository issue, and mark the plan blocked. Continue useful authorized work that does not depend on the missing gate. Do not add undocumented environment patches or weaken acceptance.

## Validate and record

- Run `make test-config` for fast repository guards. Run affected component/live/replay/evaluation checks when their boundary changes. Do not rerun Docker qualification for a documentation-only change.
- Use `corsair-review` for the final review. Record actual commands and outcomes, including blocked, failed and unrun checks; preserve supported limits.
- Update the affected spec/plan/issue and `CURRENT.md`. A completed implementation plan can still leave runtime qualification outstanding if that limit is explicitly part of its scope.
- Use `corsair-handoff` before ending substantial work. Include concrete next actions and stop conditions. Commit/push only within the user's authorization; never publish raw run/state evidence.

Examples: qualify the current platform gate; implement one sandbox adapter method; change one agent prompt and compare its isolated evaluations; investigate a native build failure without altering sandbox policy.
