---
id: PLAN-0044
kind: plan
title: Typed planned witness for the test planner
status: in_progress
updated: 2026-10-13
related: [SPEC-0040, PLAN-0038, SPEC-0022, SPEC-0023, SPEC-0033]
---

# Typed planned witness for the test planner

## Objective and dependencies

Implement [SPEC-0040](../specs/SPEC-0040-typed-planned-witness.md) so the planner's witnesses are checked deterministically instead of by review, then decide qualification on a third held-out set the prompt author never sees. Al chose this over continuing with the planner unqualified (decision card, 2026-10-13). Builds on PLAN-0038 (prompt v6, read guard, PR #38). Inference only on RIG0 (worktree under `/home/al/git/corsair/.worktrees/`, evidence under `/home/al/git/corsair/.runs/`); no kind cluster.

## Steps

- [x] Contract: `WitnessFacility` and `EnvironmentEvidence.witness_facilities`; `PlannedWitness` required on each test; admission (`planned_witnesses`) refuses an unlisted facility, a kind mismatch, wrong expectations, a `file_open` subject outside the scratch location, equal subjects, a security subject the input or fixture never names, and a `safe_behavior` that is neither `no_<effect>` nor named in `required_behavior`.
- [x] Prompt `test-planning-v7`: steps 6, 9 and 10 describe facility kinds, sentinel payloads, typed subjects and `no_<effect>`.
- [x] Evaluator: `typed_witness` check from oracle `witness_effect`; development cases, authoring cases and fixture E2E environments carry typed facilities and witnesses; the two earlier held-out sets are retired (`RETIRED`), because their frozen environments list no typed facility.
- [x] Third held-out set (`--cases heldout3`) written by one agent and independently reviewed and corrected by another, neither the prompt author nor the person running it; frozen by manifest before any provider run (the earlier planner thread's writer stopped before writing a case; this set was written fresh).
- [x] Admission: a ready plan is refused when `environment.baseline_test` is null (the SPEC-0022 precondition, previously a prompt rule only), after development showed a ready plan on the no-baseline case.
- [ ] Live on RIG0, each once, no retries: development × v7 (2 repeats); third held-out × final candidate (3 repeats).
- [ ] Composition binding and control calibration (SPEC-0040), after the planner result.
- [ ] Records, `CURRENT.md`, HANDOFF-0062.

## Pre-registered criteria

As PLAN-0038: provider profile (8192 cap, 2048 thinking, 180 s), budgets (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s). The final candidate is qualified for the third held-out scope only if all 18 attempts pass every deterministic check (including `typed_witness` and contract admission) with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property. Development runs qualify nothing.

## Validation and progress

Base: PR #38 head `89fbe80` (not yet merged). `tests/agents/test_test_planning.py` 45 passed (11 new admission cases, retired-set checks); `make test-config` 855 passed before the admission tests were added.

### Live development results (2026-10-13, RIG0, each once, no retries)

Worktree `/home/al/git/corsair/.worktrees/planner-typed-witness-abcjvt`, evidence under `/home/al/git/corsair/.runs/` (git-ignored).

| Run | Commit | Profile | Passed | Unknown tools | Wall | Requests / input / output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| development v7, 2 repeats | `192a3be` | 16384 cap, no thinking budget (not pre-registered) | 10/12 | 0 | 443 s | 30 / 152,520 / 58,522 |
| development v7, 2 repeats | `192a3be` | pre-registered (8192 cap, 2048 thinking, 180 s) | 11/12 | 0 | 285 s | 36 / 182,775 / 34,323 |

The first run used the saved fixture E2E provider file by mistake; both of its failures were the response cap reached during reasoning before any output (injection case and unsupported-observation case, one repeat each). It is kept as a record, not a criterion. On the pre-registered profile every attempt completed with provider usage; the one failure was a ready plan on the no-baseline case (status, implementation call, adversarial input, witness and grounding checks), which the new baseline admission now refuses. Every ready plan named the listed `file_open` facility with a benign control subject that occurs and the outside sentinel absent; subjects were written both scratch-relative to `tmp_path` and to the call root, and `fixture_setup` was sometimes prose. Neither is checked deterministically yet.

## Decisions and next action

- `process_start` and `socket_connect` are admitted kinds although the SPEC-0033 probe records only `file_open`; such witnesses stay unbound at execution until the probe records them, so they cannot raise a verdict.
- The earlier held-out sets stay frozen and disjointness-checked but cannot run again; both are exposed.

Next: third held-out set, then development × v7 on RIG0.
