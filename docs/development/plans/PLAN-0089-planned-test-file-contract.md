---
id: PLAN-0089
kind: plan
title: Planned test ids must name a test in their approved file
status: complete
updated: 2026-10-13
related: [PLAN-0087, SPEC-0022, SPEC-0068, SPEC-0071, HANDOFF-0116]
---

# Planned test ids must name a test in their approved file

## Objective and dependencies

PLAN-0087 lane 2: resolve the environment-approved path versus planner/author exact-file contract mismatch as one general contract. Base: main `1815f75`. PR #120 (`24029c3`) already fixed the producer side: the environment stage admits only new test files the selected framework discovers by its default convention and refuses folders, existing files and the smoke test. The pre-#120 corpus replay (`ih-python-pathtraversal` attempt 2, environment output `approved_test_paths: ["tests"]`) is refused by current validation, so that form of the mismatch is not reproduced on main.

## Mechanism reproduced on main

The remaining mismatch is between planning and authoring. Planning admitted a ready plan when each `test_path` was approved, without relating the `test_id` to that path. Authoring's handoff (`TestAuthoringInput`) then required `test_id.startswith(test_path + "::")`. A plan whose id names another file (for example approved `tests/test_a.py` and `tests/test_b.py`, path `tests/test_a.py`, id `tests/test_b.py::test_security`) therefore passed planning, spent the whole planning stage, and stopped the run at `authoring input refused`, a stage the model could no longer correct. The authoring prefix rule also only expresses pytest/Minitest ids; Java (`[module/]pkg.Class#method`) and TAP (`file.t#subtest`) ids never start with their file path.

Reproduction: a host script validating the frozen planning case `path_traversal_unguarded`'s reference plan with two approved files and the security id moved to the other file printed `ADMITTED` on main. The new parametrized planning test fails on main for all five runner grammars (5 failed) and passes after the change.

## Change

One rule, owned by the port that already defines every runner's id grammar: `corsair.ports.test_runner.names_test_in(test_id, path)` is true when the id, under any runner's native grammar (pytest, Minitest, Jest, TAP, JUnit at Maven's conventional class location), names a test in exactly that file. Planning applies it beside the approved-path check under its validation context, so a mismatch is a normal output correction inside the planning stage. Authoring's handoff replaces its `startswith` prefix test with the same rule; its separate list of id grammars the authoring checks can read (`AUTHORED_TEST_ID`: pytest, Minitest) is unchanged.

Why it is general: the rule is the existing id grammars, not any case, path, repository or verdict. It adds no prompt text, mapping or branch; prompts, skills and output schemas are byte-identical (`PROMPT_VERSION` unchanged), so frozen live baselines remain comparable.

## Steps

- [x] Reproduce on current main (host script; failing planning test on main).
- [x] Shared rule in the test-runner port; planning admission and authoring handoff use it.
- [x] Transfer: the same planning test over five distinct runner layouts (pytest under `tests/`, Minitest `test/*_test.rb`, Jest `__tests__/*.test.js`, TAP `t/*.t`, JUnit in a Maven module); only the pytest root-level layout appeared in the original evidence.
- [x] Scripted isolated evals before and after; offline suite.
- [x] Live planning comparison through the campaign owner (merged as `bfc4e52` from head `890d9e8`).
- [x] Diagnosed `ih-python-pathtraversal` successor on Docker (campaign slot attempt-0001 of `m1-python-7b0b724`: main `bfc4e52` + campaign entry `0d9890f` + pytest environment skill line `3cc5896`).

## Validation and progress

Before (main `1815f75`, this container, scripted): planning 12/12, authoring 20/20, environment 16/16, chain fixture 5/5 clean attempts. After: planning 12/12, authoring 20/20, environment 16/16, chain 5/5, every assertion row identical (only `task_seconds` differs); planning `heldout3` scripted 12/12 (reference plans only; nothing tuned on it). `TERM=xterm TEST_WORKERS=4 make test-config`: 1971 passed, 11 warnings. `git diff --check` passed. No frozen eval case, oracle or manifest changed. No live model, Docker or corpus run in this lane.

Live planning development set (campaign owner on RIG0, model not shared, development cases only; evidence under the owner's worktree `.runs/evals/planning/`, not published): reference main `1815f75` run `20261013T214309Z-development-live` 11/12 clean (failure `path_traversal_unguarded` [2/2]); candidate `890d9e8` run `20261013T215409Z-development-live` 10/12 clean (failures `no_baseline_test` [1/2] and [2/2]). In both failures the model first answered ready, was refused by the existing `environment.baseline_test is null` check, then answered unsupported without citing source read in the run, and the single output correction was already spent. That refusal is raised before the approved-path loop, so `names_test_in` never ran in either failure; neither run had an id/path mismatch. Read as sampling variance on n=12 rather than a regression of this change; the pattern "a second refusal arrives after the single output correction is spent" is logged by the campaign owner as a separate cross-stage hypothesis. The live eval shows no case where the new rule fired, so its live benefit is still unmeasured.

Live product successor (campaign slot attempt-0001 of `m1-python-7b0b724`, positive pair, model not shared, 218 s, cleanup confirmed; evidence in the owner's worktree, not published): INCONCLUSIVE, admitted, every stage completed. Environment listed tests with `--collect-only -q` after one order refusal; planning returned a ready absence plan with an `audit_open` witness and passed `names_test_in`; authoring completed; both tests passed on both revisions and the witness was null, so the gate gave completed / inconclusive / not_verified against the evaluator oracle completed / reproduced / verified (no match, no false claim). Cause, outside this plan: the authored test copied `app.py` into `tmp_path` and imported the copy, so the witness probe never saw the identified target and the second test's import reused the cached copy. The campaign owner tracks "author runs a copy of the code under test rather than the identified target" as the next general authoring hypothesis. For this plan: the planning-to-authoring path handoff held in a live product run, which it did not reach before.

## Decisions and next action

Planning output exhaustion (`planning produced no output: Exceeded maximum output retries`) remains a separate hypothesis; this change cannot fix it and may move a mismatch from an authoring-input refusal to a spent planning correction, both stopping before execution. Found, not changed here: the authoring handoff admits only pytest and Minitest ids although `static.py` reads Jest assertion lines, and TAP/JUnit have no authoring reader; that belongs to the non-Python path lane. Next: the live comparison above.
