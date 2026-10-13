---
id: PLAN-0047
kind: plan
title: Authored tests stay out of the witness; per-stage tool budgets
status: in_progress
updated: 2026-10-13
related: [SPEC-0043, PLAN-0039, HANDOFF-0057, SPEC-0033, SPEC-0035, SPEC-0038]
---

# Authored tests stay out of the witness; per-stage tool budgets

## Objective and dependencies

Implement SPEC-0043 on main `edaea39` (after #38, #43, #41, #40): authoring prompt v6 and a deterministic authored-test admission check, and per-stage tool budgets derived from the task with typed exhaustion. Then rerun the profiled three-run fully live chain on RIG0 with the operator witness, as PLAN-0039 did, and compare. The live run needs the kind cluster, held by the "Path to running all benchmarks" thread; it is requested by cross-session handover.

## Steps

- [x] Admission check (`agents/test_authoring/admission.py`), typed `RefusedWrite`, refusal budget, `admission` layer; skill v6; E2E-0 environment without the test-installed audit facility.
- [x] `StageLimits`/`stage_limits`/`BudgetExhausted`/`exhaustion` in `composition/direct.py`, both modes; native `PrepareTools` tool budget on the chain agents and repository identification; receipts and chain outcomes record limits and exhaustion; assessment evals derive per-case caps; repository identification live budget derived from repository limits.
- [x] Offline checks, native Temporal checks, scripted evals.
- [ ] Live: `make qualify-fixture-e2e` with `CORSAIR_E2E_RUNS=3`, `CORSAIR_E2E_LIVE=identification,planning,authoring,assessment`, `CORSAIR_STAGE_PROFILES=evals/fixture_e2e/stage-profiles.json`, once, from a worktree under `/home/al/git/corsair/.worktrees/`.
- [ ] Records, `CURRENT.md`, HANDOFF-0065.

## Validation and progress

Cloud container, 2026-10-13, branch `claude/author-witness-boundary-el02vx`:

- `make test-config`: 854 passed on main `b5f5faf` before the change; 965 passed after merging `edaea39` with the change.
- Native Temporal (pinned CLI 1.9.1 dev server on loopback, archive and binary hashes checked against `deploy/temporal/runtime-lock.yaml`): `pytest tests/temporal --temporal-address 127.0.0.1:7233` 47 passed; the over-budget and timed-out stage now closes as the same typed exhaustion in both modes.
- Scripted chain dataset (`evals.fixture_chain.evaluate`), direct and durable: 5/5 cases pass in each; derived caps per stage identification 4 tools / 7 requests, planning 4/7, authoring 14/17, assessment 11/14 (slack 2 at that point; slack 3 gives 12/15); scripted usage 1, 2, 4 and 9 tool calls.
- Scripted assessment dataset (`evals.evidence_assessment.evaluate`, development split): 51/51 attempts pass all evaluators with per-case derived caps.
- Scripted authoring dataset: 16/16 attempts (8 cases × 2), including the two new admission cases.
- Scripted fixture E2E (`evals.fixture_e2e.run`): complete, gate completed / reproduced / verified with the reviewed bytes admitted by digest.

Before (PLAN-0039 v5 live rerun): authoring self-made audit hooks 2/3 (one vacuous inverted security test, one broken control); tool-call cap ended authoring 1/3 and assessment 1/3; admitted fully live verdict 1/3. After: pending the live rerun.

## Decisions and next action

- The reviewed SPEC-0018 bytes are admitted by exact digest rather than by a composition flag, so no consumer of the scripted control needed new plumbing and no other bytes can use the exemption.
- `monkeypatch` itself stays allowed (environment and working-directory changes are legitimate); only its patches of observed facilities are refused.
- The authoring and planning eval budgets (`evals/test_authoring`, `evals/test_planning`) still use their own fixed caps; the "Per-agent evals outside the cluster" thread is building the authoring harness and was told about these files.
- Next: cluster handover, gateway reinstall if needed, the three-run live chain, then records and handoff.
