---
id: HANDOFF-0002
kind: handoff
title: CI cache correction and continuation
status: recorded
updated: 2026-10-10
related: [HANDOFF-0001, PLAN-0002, PLAN-0001, ISSUE-0001, ISSUE-0002]
---

# CI cache correction and continuation

## Verified state

Branch: `main`. Workflow feature revision: `b0d9f2d934970f5f2af9d276f05f7e5e2668b3b2`. This follow-up and handoff are committed together; inspect current git state for their published revision. [HANDOFF-0001](HANDOFF-0001-development-workflow.md) preserves the earlier snapshot, shared skills and platform continuation. The user-authorized workflow/publication scope is unchanged.

## Validation and blockers

All ten guards pass locally and in a fresh staged-index checkout. The [first hosted CI run](https://github.com/X-McKay/corsair/actions/runs/38082789713) also passes all ten, but its overall result is failure: setup-uv's post-job cache path is empty because Make overrode the action-provided cache location. Make now defaults its cache only when none is supplied, using the native SDK configuration. Check subsequent results in [workflow history](https://github.com/X-McKay/corsair/actions/workflows/development.yml); the correction's hosted rerun is unobserved at this snapshot's creation.

The platform remains blocked by [ISSUE-0001](../issues/ISSUE-0001-nested-container-runtime.md); client smoke coverage remains open in [ISSUE-0002](../issues/ISSUE-0002-native-client-discovery.md). Neither is resolved by offline CI. Private failure artifacts remain outside Git, and no model turns were made.

## Decisions and next steps

Honor explicit configuration before repository defaults; keep SDK functionality instead of adding cache orchestration. Treat test execution and post-job setup failure separately. Preserve native CI history and use it as the current CI authority. The next runtime step remains the existing platform qualification on a compatible host, followed by a second clean run; do not connect unqualified OpenShell components.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md and HANDOFF-0002, then the linked plan/issues and HANDOFF-0001's detailed platform continuation. Inspect git/source state and native GitHub Actions history; do not assume a local pass or handoff proves client/runtime qualification. Use the Corsair development skill.

If CI has a new failure, attribute it using its actual step/logs and make the smallest native configuration correction. Otherwise, resume PLAN-0001 on a compatible Linux Docker host, using the existing qualification commands, fresh evidence directories and confirmed cleanup. Require a second clean cluster/run before dependent OpenShell work. Keep ISSUE-0001 open if host/CNI evidence is still blocked and ISSUE-0002 open until actual client discovery is observed. Continue authorized independent work, review changes, record actual results, update CURRENT.md and append a new handoff.
```
