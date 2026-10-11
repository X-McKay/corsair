---
id: HANDOFF-0012
kind: handoff
title: Native readiness budget attribution corrected
status: recorded
updated: 2026-10-11
related: [PLAN-0009, SPEC-0008, ISSUE-0004, HANDOFF-0011]
---

# Native readiness budget attribution corrected

## Verified state

Branch codex/openshell-1f-recovery; clean base 4aacc8a75e85f42531bdb03791a3f2e0fc1aff4d matched open draft PR8 and successful exact-head CI38171748213. This correction updates that authorized draft. Resolve its committed source with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0012-readiness-budget-corrected.md, then verify remote identity and exact-head CI; this precommit snapshot does not invent those future results or claim a clean precommit tree.

The user asked where the 120-second readiness gate originated, then authorized correcting it before discussing next steps. Git history locates the first override in 1C commit cc97b88, tests/qualification/test_lifecycle.py. The upstream SDK example and higher-level Sandbox wrapper use 120; the actual SandboxClient.wait_ready method defaults to 300. No user requirement, startup SLO or measured rationale established 120 as a mandatory runtime criterion. That attribution was overstated.

Four explicit readiness overrides are removed from lifecycle, policy and recovery probes; future calls inherit the pinned native 300-second default. Actual Ready identity, security admission, immutable pins and cleanup remain mandatory. Kubernetes gateway rollout deadlines and command/output/resource/cleanup budgets are unchanged. ISSUE-0004 remains open as an uncharacterized latency observation; exceeding the local 120-second budget alone does not establish an upstream defect or automatically block Milestone 2 planning.

## Validation and blockers

Baseline 94 offline guards passed. Final 94 offline guards pass in 0.12s; all nine qualification tests collect without dispatch in 0.04s; compilation and whitespace checks pass. One prior run retained 93 passed/one failed on required issue headings; the headings were restored without changing runtime evidence. Final review checks that only the four native readiness arguments change; no policy/TLS/kernel/artifact requirement changes. Raw proof remains ignored under .runs/readiness-budget-correction/. No deployment, new runtime attempt, application adapter, agent or Temporal work is performed here.

The [recovery report](../../qualification/openshell-recovery.md) preserves bounded native 1A–1F qualification at source 4aacc8a and the original 120-second test budget. Runs 010/011 passed 247.858s/222.096s; all four cases, exact-node native prerequisites and original resource/process/storage/private/cluster cleanup were audited. All eight failed runs and coverage-incomplete008 retain their original results and source hashes. Runs 002/009 missed the local budget; their eventual readiness is unobserved, and no claim is made that they would pass at 300 seconds. Verify those historical source hashes against git show 4aacc8a:<path>, rather than rebinding the frozen receipts to the edited harness. HANDOFF-0011 remains an unchanged historical snapshot; its mandatory 120-second interpretation is superseded by this correction.

The corrected harness is offline-checked without a fresh 300-second live baseline. Neither 120 nor 300 is an upstream readiness guarantee or product latency SLO. Startup cause and general reliability remain unknown. No live OpenShell/Agent Sandbox installation or owned cluster remains. Production tenancy, arbitrary-output SDK memory, CPU throttling performance and subsequent application milestones remain unqualified.

## Decisions and next steps

[PLAN-0009](../plans/PLAN-0009-openshell-recovery.md) records this correction separately from historical qualification; [ISSUE-0004](../issues/ISSUE-0004-native-admission-readiness.md) has corrected attribution and characterization criteria. Existing authorization covers tracked correction publication on draft PR8; do not merge, close external issues or message others. Update the PR description so it no longer presents 120 seconds as an upstream requirement.

Proposed next steps for discussion: collect a bounded fresh-native readiness sample using the actual API default and original-ID cleanup, then implement only the narrow Milestone 2 Sandbox/artifact adapter with native SDK/CLI and typed vendor-free domain results. Require actual native prerequisites and readiness before any workload. A failed 300-second attempt would require investigation before using that runtime, without replay or speculative repair. Do not infer a product SLO or fleet reliability from a small sample. Neither proposed component is begun by this correction; PydanticAI and Temporal remain later separately scoped work.

## Continuation prompt

```text
Read AGENTS.md, README, CURRENT, Corsair development/review/handoff skills,
HANDOFF-0012, PLAN-0009, SPEC-0008, ISSUE-0004 and the recovery report/runbook.
Inspect source/git and actual published draft/exact-head CI. Verify the pinned
SandboxClient.wait_ready default 300 and four removed local overrides; retain
historical qualification at 4aacc8a under its original 120-second budget.
Do not relabel old failures or infer an upstream defect from 120 seconds alone.
The corrected harness has no fresh 300-second live baseline.
Discuss/select the next bounded component: a fresh-native readiness sample,
then the narrow Sandbox/artifact adapter. Do not treat either as implemented.
Every fresh runtime requires real native prerequisites, actual Ready and
original-ID cleanup. Preserve all attempts and unknown delivery; do not weaken
security or blindly replay work. Use proportionate checks, update records,
append a new handoff and publish only authorized tracked changes. Never commit
.runs/.state, credentials or raw logs; do not merge or close external issues.
```
