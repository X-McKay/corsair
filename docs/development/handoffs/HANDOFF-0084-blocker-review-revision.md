---
id: HANDOFF-0084
kind: handoff
title: Setup blocker review revision
status: recorded
updated: 2026-10-13
related: [SPEC-0053, PLAN-0057, HANDOFF-0080]
---

# Setup blocker review revision

## Verified state

PR63, branch codex/actionable-blockers, managed worktree actionable-blockers/corsair. Started at bd27ca8 and integrated main 759b016 with a merge preserving review history. Resolve the revision containing this handoff with Git. Diagnostics now follow PR62's one-file-per-tool layout. The refused extra budget call regression remains fixed.

User requested opportunities to correct minor mistakes. The setup tool now permits up to two explicitly attributed changed invocations for narrow missing-mvn and pytest-unrecognized-argument symptoms. The operator can reduce or disable the allowance. Failed receipts remain; pending correction prevents ready/unsupported; all usual successful setup evidence is still required. Identical failed invocations cannot be dispatched again. Execution uncertainty, cleanup, policy/infrastructure and recognized dependency/network/TLS blockers remain terminal. This is not proof of side-effect freedom or a generic repair mechanism. See SPEC-0053 for exact limits.

## Validation and blockers

Full offline `make test-config`: 1321 passed before the final repeat-after-recovery guard and two regressions. Final affected environment/diagnostic/runtime/eval tests: 114 passed, including that guard. One existing SDK event-loop deprecation warning. Frozen `make eval AGENT=environment` candidate 20261013T121409Z-development-scripted: 16/16, previous 20261013T112748Z-development-scripted: 16/16; unchanged request/tool/command counts. Those eight frozen cases have zero correction attempts, not an observed recovery rate. Additional production FunctionModel trajectories cover correction boundaries. PLAN-0057 retains failed attempts and identities. No live provider, sandbox, network or durable qualification; G12 stays unchanged.

## Decisions and next steps

Publish this revision to the existing draft PR63 and update its description/review response; do not merge without authorization. Recheck exact-head CI. Next live environment evaluation should use held-out wrong-wrapper/discovery mistakes and measure attempts, successful recovery, over-refusal, calls/tokens/latency and actual sandbox effects. A usage error can happen after plugins execute; stop if effects are uncertain. Expand admitted correction classes only with evidence. Do not change policies, credentials, pins or images to obtain a pass.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0053, PLAN-0057 and HANDOFF-0084. Inspect PR63 and its actual head/CI, and verify the split environment implementation. Address concrete review findings within existing scope. Keep the bounded correction contract and uncertain-execution stops distinct. Before live qualification claims, measure correction behavior on held-out invocation mistakes in an admitted sandbox. Run affected checks and update records; no merge authorization is implied.
```
