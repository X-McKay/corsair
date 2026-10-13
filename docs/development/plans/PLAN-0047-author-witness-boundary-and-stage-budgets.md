---
id: PLAN-0047
kind: plan
title: Authored tests stay out of the witness; per-stage tool budgets
status: complete
updated: 2026-10-13
related: [SPEC-0043, PLAN-0039, HANDOFF-0057, HANDOFF-0065, SPEC-0033, SPEC-0035, SPEC-0038]
---

# Authored tests stay out of the witness; per-stage tool budgets

## Objective and dependencies

Implement SPEC-0043 on main `edaea39` (after #38, #43, #41, #40): authoring prompt v6 (v7 after review) and a deterministic authored-test admission check, and per-stage tool budgets derived from the task with typed exhaustion. Then rerun the profiled three-run fully live chain on RIG0 with the operator witness, as PLAN-0039 did, and compare. The live run needs the kind cluster, held by the "Path to running all benchmarks" thread; it is requested by cross-session handover.

## Steps

- [x] Admission check (`agents/test_authoring/admission.py`), typed `RefusedWrite`, refusal budget, `admission` layer; skill v6; E2E-0 environment without the test-installed audit facility.
- [x] `StageLimits`/`stage_limits`/`BudgetExhausted`/`exhaustion` in `composition/direct.py`, both modes; native `PrepareTools` tool budget on the chain agents and repository identification; receipts and chain outcomes record limits and exhaustion; assessment evals derive per-case caps; repository identification live budget derived from repository limits.
- [x] Authoring `read_source` serves the author's own admitted writes; absent paths and past-end starts return a typed `UnreadSource` instead of ending the stage; eval case `reads_own_file_after_collection_error` and `unread_sources` count.
- [x] Offline checks, native Temporal checks, scripted evals.
- [x] Owner deferred (2026-10-13 12:16Z, merged without it), unrun: live `make qualify-fixture-e2e` with `CORSAIR_E2E_RUNS=3`, `CORSAIR_E2E_LIVE=identification,planning,authoring,assessment`, `CORSAIR_STAGE_PROFILES=evals/fixture_e2e/stage-profiles.json`, once, from a worktree under `/home/al/git/corsair/.worktrees/`, now a follow-up run on main.
- [x] Records, `CURRENT.md`, HANDOFF-0065.

## Validation and progress

Cloud container, 2026-10-13, branch `claude/author-witness-boundary-el02vx`:

- `make test-config`: 854 passed on main `b5f5faf` before the change; 965 passed after merging `edaea39` with the change; 1009 after merging main at `8c29e16` (2d1c476); 1070 at 236bdab; 1076 at 23d2ee4; 1286 at 2d7f009; 1288 after merging #64 (083acf5); 1331 after merging main `759b016` (87b8e20).
- Native Temporal (pinned CLI 1.9.1 dev server on loopback, archive and binary hashes checked against `deploy/temporal/runtime-lock.yaml`): `pytest tests/temporal --temporal-address 127.0.0.1:7233` 47 passed; the over-budget and timed-out stage now closes as the same typed exhaustion in both modes.
- Scripted chain dataset (`evals.fixture_chain.evaluate`), direct and durable: 5/5 cases pass in each; derived caps per stage identification 4 tools / 7 requests, planning 4/7, authoring 14/17, assessment 11/14 (slack 2 at that point; slack 3 gives 12/15); scripted usage 1, 2, 4 and 9 tool calls.
- Scripted assessment dataset (`evals.evidence_assessment.evaluate`, development split): 51/51 attempts pass all evaluators with per-case derived caps.
- Scripted authoring dataset: 16/16 attempts (8 cases × 2), including the two new admission cases. After the read fix: 18/18 (9 cases × 2), the new read case answered one absent path typed and finished as a patch.
- At 87b8e20 (main `759b016` merged): native Temporal 47 passed; scripted `make eval` identification 16/16, planning 12/12, authoring 18/18, assessment 51/51, chain 5/5; CI green.
- Scripted fixture E2E (`evals.fixture_e2e.run`): complete, gate completed / reproduced / verified with the reviewed bytes admitted by digest.

All eval results above are scripted. No live isolated `make eval` baseline exists yet for any version this PR changes: authoring `test-authoring-v7`/config-v3, planning `test-planning-config-v6` (with #54 grounding; fixture tool cap 8 to 4), identification `issue-identification-config-v4-grounding-3`, repository identification `issue-identification-repository-config-v3-grounding-3`, assessment config-v2. The host-only authoring v5 run on RIG0 (pre-2d1c476 head) shared the model server with the per-agent baselines from about 09:44Z and is not comparable.

Before (PLAN-0039 v5 live rerun): authoring self-made audit hooks 2/3 (one vacuous inverted security test, one broken control); tool-call cap ended authoring 1/3 and assessment 1/3; admitted fully live verdict 1/3. After: unmeasured; the owner merged without the live rerun, which stays a follow-up on main. Host-only authoring A/B on RIG0 (local model, REPEAT=3, v5 sharing the model, so indicative only): clean attempts v5 5/18, v6 5/24; witness hooks per attempt 1.56 to 0; output tokens 6557 to 2657; wall time 71.9 s to 29.7 s. Of v6's failures, 10 were the `read_source` re-read and 3 the eval harness crash, both fixed afterwards; no refusal fired live, so the live refusal rate is unknown.

## Decisions and next action

- The reviewed SPEC-0018 bytes are admitted by exact digest rather than by a composition flag, so no consumer of the scripted control needed new plumbing and no other bytes can use the exemption.
- `monkeypatch` itself stays allowed (environment and working-directory changes are legitimate); only its patches of observed facilities are refused.
- The authoring and planning eval budgets (`evals/test_authoring`, `evals/test_planning`) still use their own fixed caps; the "Per-agent evals outside the cluster" thread is building the authoring harness and was told about these files.
- Owner, 2026-10-13 12:16Z: merge #49 now; the live three-run chain and live baselines for the changed agent versions move to follow-up runs on main (HANDOFF-0065).
