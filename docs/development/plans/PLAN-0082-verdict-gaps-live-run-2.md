---
id: PLAN-0082
kind: plan
title: Verdict gaps from live end-to-end run 2
status: complete
updated: 2026-10-13
related: [SPEC-0027, SPEC-0033, SPEC-0040, SPEC-0043, SPEC-0030]
---

# Verdict gaps from live end-to-end run 2

## Objective and dependencies

Live run 2 of the fixture case (OpenShell sandbox on RIG0, main 666d496, every stage live except runtime and environment) completed and ended `inconclusive`/`not_verified`, while the scripted control on the same cluster gave `reproduced`/`verified`. Records: `live-1/` and `control-scripted/` in the run 2 evidence archive (`/mnt/project-files/e2e-run2.tar.gz`, provider fields redacted). Three gaps, diagnosed from those records:

1. **The security test could not distinguish the revisions.** The plan was `no_file_open` on `outside.txt` with failure type `AssertionError`. The author called the target, then asserted `(tmp_path / "outside.txt").read_text() == "outside"` (line 16): a read never changes the file, so the assertion holds on both revisions. On the fixed candidate the target's own `ValueError` escaped the call at line 15 and failed the test. Cause: step 5 of the authoring skill offered "an outside file that must keep its content" as the example of an absent effect, which only holds for writes and deletes, and nothing told the author how a test survives a rejection under an absence plan. Nothing downstream named the outcome: the gate reported `witness_missing` and `unplanned_failure`.
2. **`witness_missing` on the baseline.** Not a `..` normalization problem: the probe matched `allowed/../outside.txt` by basename and recorded it `planned: true` on the target's stack. The record also had `offstack_planned: 1`, from the test's own line 16 re-read on the test thread after the target returned. SPEC-0040 counted every such open as a possible deferred effect, so the mapping made the effect `unknown` and the gate said `witness_missing`.
3. **Assessment proposed `not_reproduced`.** The gate permitted `inconclusive` and admission rejected the proposal ("finding not_reproduced exceeds permitted inconclusive"), so the reported verdict was already right. The skill never said what `not_reproduced` needs; the agent read "baseline security passed" as not reproduced while citing the witness that showed the open.

4. **Gap 9, Docker fixture run live-002** (run thread worktree `.worktrees/docker-route-live`, `.runs/fixture-e2e-docker/live-002`, reported by the coordinator): the author's security test wrote `allowed/note.txt` without creating `allowed/`, so it raised `FileNotFoundError` on both revisions before reaching the call. Authoring accepted it because acceptance refused only a setup error or skip, and the run's security outcome (withheld from the author) was never checked for an error before the assertion.

5. **Gap 6b, Docker fixture run live-005** (`.runs/fixture-e2e-docker/live-005`, reported by the coordinator): the security test asserted the resolved path stays inside the allowed folder but left the call bare, so the fix's `ValueError` failed it on the candidate (`reproduced`/`not_verified`). Same skill cause as gap 1: nothing said that under an absence plan a raising fix must let the test pass.

Approach unchanged (stage order, runner core, witness required, matrix rows); nothing per language outside the Python probe and the Python static facts that already exist.

## Steps

- [x] Probe (`nodes/witness_probe.py`): a planned open on the test thread after the first call whose stack, from the open outward, holds only standard-library file-I/O frames (`io`, `_pyio`, `codecs`, `os`, `pathlib`, identified by module identity) and then the running test function's own code is the test's read, counted as `body_planned`, never as `offstack_planned`. Helpers, the event loop and application callbacks stay off-stack (fail-closed). Record field added as optional (`corsair-witness-v2` unchanged).
- [x] Gate (`core/disposition.py`): with a witness that reached the path, a security pass while the effect was observed is `security_passed_with_effect`, and a security failure while the witness shows the effect absent with the planned safe behavior is `security_failed_with_safe_witness`; both `unusable`. They name "this security test cannot distinguish the revisions" with the reason, instead of `witness_missing`/`witness_unsupported`/`unplanned_failure`.
- [x] Authoring skill (`test-authoring-v9`): assert through something that differs between the unsafe and safe outcome; a read changes no file, so assert on what the call returned; under an absence plan (`no_<effect>`) catch around the planned call only, keep the returned value and assert on it, whatever the assertion checks (gap 6b), so a raising fix passes. The eval's static fact allows that one broad handler only inside the security test of an absence plan.
- [x] Authoring acceptance (gap 9): a development run's security failure of another type than the plan's `failure_type` is shown to the author (it broke before its planned assertion, which is not a verdict), and finalization refuses a patch whose last run shows one, with the type and line, once correctable like a control error. The pass/fail verdict of the planned assertion stays withheld.
- [x] Assessment skill (`evidence-assessment-v6`): a security outcome that contradicts its witness supports neither value; `not_reproduced` needs every baseline security pass with the effect absent and the planned safe behavior.
- [x] Evals: authoring case `absence_plan_realization` (dataset `test-authoring-development-v4`); assessment development case `security_pass_with_observed_open` (regenerated, held-out manifest refrozen because the probe digest is in every record; held-out cases otherwise unchanged).
- [x] Host replay of run 2 (`tests/unit/test_security_test_distinguishes.py`): real pytest, real probe and gate on both fixture variants. Live run 2's test bytes give `inconclusive`/`not_verified` with both new codes (before this change: `witness_missing`, `unplanned_failure`); the skill's absence-plan shape gives `reproduced`/`verified`.

## Validation and progress

- `make test-config`: 1797 passed.
- Scripted evals, `make eval AGENT=...` on the host, before (main 184e609) and after; results under `.runs/evals/<agent>/` in the working checkout (not committed):

| Suite | Before | After |
| --- | --- | --- |
| authoring development | 18/18 clean (9 cases × 2) | 20/20 clean (10 cases, new absence-plan case) |
| assessment development | 51/51 clean (17 × 3) | 54/54 clean (18 × 3, new case) |
| assessment held_out | 21/21 clean | 21/21 clean (record digests only) |
| chain fixture | 5/5 clean | 5/5 clean |

Scripted evals prove plumbing and evaluator sensitivity, not prompt quality. No live eval was run (the model is reserved for end-to-end runs). The probe digest changed and is unqualified until `make qualify-witness` passes on it (main's previous digest was not gated either).

## Decisions and next action

- Gap 3 moves the agent, not the gate: the gate's `inconclusive` was correct and already authoritative.
- Fail-closed kept for deferred effects: only the test function itself, through standard file-I/O frames, is the test body.
- Next: the next live run uses this branch; live authoring/assessment baselines for v9/v6 when the model is free; `make qualify-witness` at the next milestone gate.
