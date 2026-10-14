---
name: corsair-development
description: Use when planning, implementing, debugging or resuming Corsair development. Define one bounded change, prefer pinned native SDK features, validate the changed boundary and leave honest work records.
---

# Corsair development

Resolve paths from the repository root. Read `AGENTS.md`, `docs/development/README.md` and `docs/development/CURRENT.md` first. Follow current user authorization; this skill adds no approval gate.

## Resume and scope

1. Inspect branch, working tree and relevant source. Read the active plan and latest handoff; verify their claims against actual source and receipts.
2. Use `docs/development/specs/SPEC-0082-corsair-v2-architecture.md` as the v2 architecture authority. Do not restore retired v1 roles, paths, protocols or migration plans from historical records.
3. State one failing behavior or measurable acceptance criterion. Preserve unrelated work. Reuse a record for small corrections; create a spec/plan from `docs/development/templates/` for substantial boundaries. Do not create every record type automatically.
4. Verify the installed, pinned native SDK API before adding a wrapper. Record the concrete upstream gap and retained domain requirement for bespoke code.

## Implement and evaluate

1. Change one independently testable component. Keep schemas, restricted tools, current-run validators and policy authority explicit; use native PydanticAI/Harness/Temporal facilities where they fit.
2. Use typed fixtures or native overrides for host-only agent development. Do not execute model-authored tests on the host or replace a blocked live gate with mocks.
3. Preserve the root two-probe, independent-author and outcome-blind review rules. Keep exactly the benign control and PoV through the real application seam. Do not change probe polarity, marker interface or disposition rules in an unrelated refactor.
4. For an agent change, run `make eval AGENT=<name> SET=<set> EVAL_LANGUAGE=<language>` on its frozen set. Compare the same input, model, prompt/skill/tool identities, budgets, mode and repeat count. No provider config means scripted plumbing, not model accuracy; missing telemetry stays unknown.
5. Respect current gate deferral in `CURRENT.md` and the development guide. Record failures and unrun qualification; continue independent work when a dependency is blocked. Do not weaken policies, pins or budgets for a pass.

## Finish

Run `make test-config`, affected unit/eval checks, then the relevant broader suite (`make test-v2`). Use `corsair-review`, clean up and re-test changed behavior. Update the living work record and `CURRENT.md`; use `corsair-handoff` for substantial work. Keep `.runs/`, credentials and private diagnostics out of Git. Publish only within the user's scope.
