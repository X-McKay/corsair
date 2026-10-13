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
- [x] Live on RIG0, each once, no retries: development × v7 (2 repeats); third held-out × final candidate (3 repeats). Not qualified (below).
- [x] Review fixes (PR #44): the composition requests the operator envelope only when the plan's security witness is a `file_open` whose subject is exactly the envelope's file (a directory-prefixed alias is another path and is refused), so an unrecorded kind or another subject stays inconclusive; `file_open` subjects must be written canonically so the distinct-subject rule compares files, not spellings (`ca8c689`, exact subject `cc4ce39`).
- [x] Review fixes, second round: `no_file_open` maps to the gate's safe behavior for an attributed absence (`d7b413f`, Codex finding); the probe counts planned-file opens on other threads (`offstack_planned`), which make the effect `unknown`; the mapping applies only on the candidate until control calibration, so a vacuous baseline absence stays inconclusive; `safe_behavior` must be named as a whole identifier in `required_behavior`. Regressions: a worker-thread open, the test body's own sentinel reads, a substring identifier. The probe bytes changed, so the evidence-assessment dataset was regenerated with its builder and its held-out manifest refrozen (`python -m evals.evidence_assessment.build --freeze-held-out`); only artifact and probe digests differ, no case content.
- [ ] Composition binding from the plan and control calibration (SPEC-0040): not started; the interim refusal above stands in for it.
- [x] Records, `CURRENT.md`, HANDOFF-0062.

## Pre-registered criteria

As PLAN-0038: provider profile (8192 cap, 2048 thinking, 180 s), budgets (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s). The final candidate is qualified for the third held-out scope only if all 18 attempts pass every deterministic check (including `typed_witness` and contract admission) with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property. Development runs qualify nothing.

## Validation and progress

Base: PR #38 head `89fbe80` (not yet merged). `tests/agents/test_test_planning.py` 45 passed (11 new admission cases, retired-set checks); `make test-config` 855 passed before the admission tests were added.

### Live results (2026-10-13, RIG0, each once, no retries)

Worktree `/home/al/git/corsair/.worktrees/planner-typed-witness-abcjvt`, evidence under `/home/al/git/corsair/.runs/` (git-ignored).

| Run | Commit | Profile | Passed | Unknown tools | Wall | Requests / input / output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| development v7, 2 repeats | `192a3be` | 16384 cap, no thinking budget (not pre-registered) | 10/12 | 0 | 443 s | 30 / 152,520 / 58,522 |
| development v7, 2 repeats | `192a3be` | pre-registered (8192 cap, 2048 thinking, 180 s) | 11/12 | 0 | 285 s | 36 / 182,775 / 34,323 |
| development v7 + baseline admission, 2 repeats | `e0fc490` | pre-registered | 11/12 | 0 | 241 s | 33 / 169,958 / 28,580 |
| third held-out (`heldout3`), 3 repeats | `e0fc490` | pre-registered | 17/18 | 0 | 575 s | 57 / 306,342 / 65,994 |

The first run used the saved fixture E2E provider file by mistake; both of its failures were the response cap reached during reasoning before any output (injection case and unsupported-observation case, one repeat each). It is kept as a record, not a criterion. On the pre-registered profile every attempt completed with provider usage; the one failure was a ready plan on the no-baseline case (status, implementation call, adversarial input, witness and grounding checks), which the new baseline admission now refuses. Every ready plan named the listed `file_open` facility with a benign control subject that occurs and the outside sentinel absent; subjects were written both scratch-relative to `tmp_path` and to the call root, and `fixture_setup` was sometimes prose. Neither is checked deterministically yet.

The candidate is `test-planning-v7` with the baseline admission (`e0fc490`); the later review fixes (`ca8c689`) change composition and refuse non-canonical subjects, and no ready plan in either run had a non-canonical subject. On development the baseline admission refused a ready plan on the no-baseline case; the model's single correction returned `unsupported` without the required citation, ending the attempt. On the held-out set every completed attempt passed every deterministic check with provider usage and no unknown tools; one attempt on a no-baseline case returned `ready` twice (an empty fixture list, then the baseline refusal) and exhausted the one output correction.

Independent review of the 12 ready held-out plans and 5 unsupported results (by an agent that wrote neither the prompt nor the cases; no case details here): status correct in all 17 completed attempts with the right missing capability; `safe_behavior` consistent in all 12. Defects: one plan's relative payload resolves against the process working directory, not the scratch location, so its absent witness is vacuous and the payload would write outside scratch on vulnerable code; one inert markup payload where a plain sentinel would do; outcome forecasts in limitations in 3; the development traversal-target file name carried into 2; a specific exception type the issue never requires in 3 (the test would measure the exception type, not the property); test ids without the approved file prefix in 2 (one duplicating the baseline test name); an implementation object never constructed in fixture setup in 1.

**Result: not qualified** under the pre-registered criteria (17/18, and review found defects that would make authored tests measure the wrong property). Compared with PLAN-0038 (fresh held-out 13/18), status errors and facility-contradicting witnesses dropped to one vacuous witness; the remaining defects are in prose fields no gate reads.

## Decisions and next action

- `process_start` and `socket_connect` are admitted kinds although the SPEC-0033 probe records only `file_open`; such witnesses stay unbound at execution until the probe records them, so they cannot raise a verdict.
- The earlier held-out sets stay frozen and disjointness-checked but cannot run again; both are exposed.

- The third held-out set is now exposed; any further candidate needs a fourth set written and reviewed apart from its author.
- Candidate deterministic checks from the review (not implemented, each needs its own evidence): test ids prefixed by their approved test path and distinct from the baseline test; a security `failure_type`/`safe_behavior` exception only when the issue or source names one, else `no_<effect>`; adversarial file inputs anchored at the scratch location; correction messages for the baseline refusal that say to cite the read source.

Next: composition binding from the plan and control calibration (SPEC-0040), and the deterministic checks above, before another planner candidate.

Merged unqualified on Al's decision (2026-10-13 12:16Z): the plan-based witness binding, the four text-defect checks and a fourth held-out set move to a follow-up; the planner on main stays unqualified at development 11/12 and held-out 17/18 (prompt v7). The merge with main makes the prompt `test-planning-v7-grounding-3` (config v6), checked offline only (HANDOFF-0062).
