---
id: PLAN-0032
kind: plan
title: OpenShell test workspace adapter
status: complete
updated: 2026-10-12
related: [SPEC-0032, SPEC-0028, PLAN-0027, ISSUE-0006]
---

# OpenShell test workspace adapter

## Objective and dependencies

Implement [SPEC-0032](../specs/SPEC-0032-openshell-test-workspace.md): an OpenShell `TestWorkspace` so the [PLAN-0027](PLAN-0027-test-authoring-agent.md) runner executes tests inside a sandbox, qualified live with the reviewed SPEC-0018 pair. Depends on the qualified lifecycle, execution and source-arrival recipes. General source delivery stays blocked under ISSUE-0006 and SPEC-0025; the parallel fixture-chain work consumes this adapter later and is not touched here.

## Steps

- [x] `adapters/openshell_workspace.py`: `WorkspaceConfig`, `DirectoryUpload`/`CliUpload`, fixed verifier, `OpenShellTestWorkspace` with exact host admission and discard on refusal.
- [x] Runner wrapper uses absolute `/bin/sh`; affected runner and authoring assertions updated.
- [x] Offline unit tests, including the real runner composed over the adapter for both SPEC-0018 variants.
- [x] Live gate `tests/qualification/test_test_workspace.py`, marker `test_workspace`, target `make qualify-test-workspace`.
- [x] Live qualification on a fresh RIG0 kind node; results here and in the [report](../../qualification/openshell-test-workspace.md).
- [x] Review, CURRENT.md row and [HANDOFF-0050](../handoffs/HANDOFF-0050-openshell-test-workspace.md).

## Validation and progress

2026-10-12, cloud container from main `102fbef`: `make test-config` 766 passed (747 before; 19 new workspace checks), one existing pydantic_graph deprecation warning. The live gate collects (`-m test_workspace --collect-only`: 1 selected).

2026-10-12, RIG0, one fresh kind node, worktree at PR head `aca85a4`: network (3 passed), admission (1 passed), gateway install, toolchain image build/load and `make qualify-test-workspace` all exited 0; JUnit 1 passed in 148.6 s. Four fresh sandboxes: vulnerable twice with control passed and security failed at `test_documents.py:64` (exit 1), fixed twice with both passed (exit 0); every run discovered exactly the two ids, had no failure layer, confirmed cleanup and no remaining Sandbox resource or boundary pod; staging empty; `make kind-down` confirmed. No reruns. Limits: one node, not two; native upload internal retries unobserved; fixture envelope only.

## Decisions and next action

Delivery reuses the qualified CLI upload with in-sandbox inventory admission instead of a new transfer mechanism; the verifier reports and the host decides. Two execution adapters are wired, one at `/tmp` for the verifier and one at the workspace root for the runner. Next: the fixture chain consumes this adapter; a second fresh node would strengthen the qualification; real repositories wait on SPEC-0025 fetch and the storage quota.
