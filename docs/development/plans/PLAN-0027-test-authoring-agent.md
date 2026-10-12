---
id: PLAN-0027
kind: plan
title: Test authoring agent and native pytest runner
status: in_progress
updated: 2026-10-12
related: [SPEC-0028, IDEA-0004, SPEC-0022, PLAN-0025, ISSUE-0006]
---

# Test authoring agent and native pytest runner

## Objective and dependencies

Implement [SPEC-0028](../specs/SPEC-0028-test-authoring-agent.md) offline. Builds on the planner contracts of [PLAN-0025](PLAN-0025-test-planning-agent.md) (this branch is based on its branch) and supplies the assertion lines that the SPEC-0027 disposition gates (drafted on the evidence assessment branch) need. Live use is blocked on an OpenShell `TestWorkspace` adapter, which needs source delivery (SPEC-0025) and approved test-file delivery (narrower than ISSUE-0006). Independent work can continue meanwhile.

## Steps

- [x] Vendor-free `ports/test_runner.py`.
- [x] `reports/junit.py` and `adapters/pytest_runner.py` with fake-port tests and a real pytest run of the reviewed SPEC-0018 bytes.
- [x] `agents/test_authoring/` (contracts, tools, trusted output function, static checks, `write-native-tests` skill).
- [x] `evals/test_authoring/` (six frozen cases, scripted runner, curated evaluators) and `tests/agents/test_test_authoring.py`, including composition with the real runner over reviewed bytes.
- [ ] OpenShell `TestWorkspace` adapter: fresh sandbox, captured source, one approved test file, identity-checked cleanup. Blocked on SPEC-0025 and approved test-file delivery qualification.
- [ ] Live-provider evaluation with the real runner on RIG0, then independent review of actual patches.
- [x] Review, records, `CURRENT.md` row and handoff.

## Validation and progress

Base: planner branch `e041021` over main `83dec61`. `make test-config`: 494 passed (one existing pydantic_graph deprecation warning); the planner branch alone reports 416. New checks: 18 JUnit, 35 runner, 25 authoring. Scripted native evals: 12/12 attempts (6 cases × 2 repeats) passed every assertion, zero unknown tools, zero revealed security outcomes. Real pytest over reviewed SPEC-0018 bytes: vulnerable gives control passed and security `AssertionError` at `test_documents.py:64` in `test_security_rejects_outside_read`, exit 1; fixed gives both passed, exit 0. First eval run failed 6/12 because fixture models were keyed by input digest and four cases share inputs; corrected by a `fixture_id` wrapper kept out of the prompt. One static check initially missed `from unittest import mock`; fixed. No provider, Temporal or OpenShell check ran.

Review of `ec73e0b` (Al) reproduced two defects, now fixed with regressions: a skipped security test was shown as `withheld` and admitted as a patch, and several `run_tests` calls in one model response all saw the same history, exceeded the run budget and shared one operation identity. Budget reservation now counts dispatched calls, operations use the tool call id, duplicate call ids are refused, and skips are shown like setup errors. The branch was merged with the planner head `3d95ec9`, keeping both CURRENT rows. `make test-config` after the fix: 497 passed. Re-review of `f794f24` found the `TestPatch` validator compared the patch with the last run entry, so a budget-refused `not_run` after a successful run invalidated the patch; it now compares with the last executed run, with a regression that fails without the fix.

Codex review of `0669f59` raised three findings, all reproduced and fixed with regressions that fail on the old source: authoring input now checks every plan excerpt against the supplied inventory, so a plan made over another revision of same-named files is refused; planned and patch node ids share the runner's 128-character bound (`MAX_TEST_ID`); and security assertion lines count only checks the test body itself runs (not nested functions, classes or lambdas) and only `pytest.raises` bound by a module-level pytest import. `make test-config`: 502 passed; scripted evals 12/12.

## Decisions and next action

- The patch is rebuilt from current-run write calls, so deps stay immutable and durable-safe.
- `security_assertion_lines` is declared by the model and verified structurally; deriving all asserts would include fixture preconditions such as line 52 of the reference test, which the gates must not accept as the planned failure.
- The runner's operator prefix needs `-c /dev/null --rootdir .`; without `--rootdir`, pytest 9 emits node ids with an empty file part.
- Evaluation is scripted-only until a sandbox runner exists; no live provider flag is offered, so a live run cannot execute model code on the host.

Next: build the OpenShell `TestWorkspace` adapter once source fetch and test-file delivery qualify, then run the live evaluation.
