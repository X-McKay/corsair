---
id: PLAN-0026
kind: plan
title: Deterministic disposition gates
status: in_progress
updated: 2026-10-12
related: [SPEC-0027, IDEA-0004, SPEC-0018, SPEC-0022]
---

# Deterministic disposition gates

## Objective and dependencies

Implement [SPEC-0027](../specs/SPEC-0027-disposition-gates.md), step 3 of the accepted [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md) order (gate half; the report renderer is separate). No dependency on the planner, runner adapter or any runtime. Runs in parallel with the planner thread, which owns `agents/source/`, `agents/provider.py` and the planner's own records; this plan touches only `src/corsair/core/`, `tests/unit/test_disposition.py` and its records.

## Steps

- [x] Typed gate contracts and `assess`/`admit` in `src/corsair/core/disposition.py`.
- [x] Table-driven unit tests over SPEC-0018-shaped synthetic evidence, including every same-outcome negative IDEA-0004 lists.
- [x] Local check that the gate's failure-location contract matches actual pytest JUnit output for the reviewed pair.
- [x] Validate against the retained SPEC-0018 runs on RIG0 (both retained sets; results below).
- [x] Typed `ObservationPlan` source agreed with the planner thread (SPEC-0027 decisions).
- [ ] Builder from `ReadyTestPlan` and `TestPatch` to `ObservationPlan`, once both are on main.
- [ ] Report renderer, as its own step.

## Validation and progress

2026-10-12, cloud session on branch `claude/evidence-assessment-checks-e694q5` from main `83dec61`:

- `uv run --locked python -m pytest tests/unit/test_disposition.py -q`: 50 passed. The first draft let one baseline timeout coexist with `fix: verified`; corrected to require every baseline run to reproduce, per the contract's "it still cannot verify the fix".
- Local fixture check (repository-owned SPEC-0018 bytes only, scratch directory outside the repository, not retained): pytest on the vulnerable variant exited 1 with the JUnit failure ending `test_documents.py:64: AssertionError`, the first planned assertion line; the fixed variant exited 0 and its security witness recorded `ValueError` with no opens. A scratch mapping of that actual JUnit and witness stdout into `RunEvidence` gave `completed`/`reproduced`/`verified` with no limitations. One run per variant, host Python 3.12.3; this is a shape check, not a repeat of the SPEC-0018 qualification, and the mapping script is not the runner adapter.
- Retained-run validation, RIG0 at `acf07a8` (worktree `make test-config` 457 passed). Both retained sets, `.runs/benchmark-admission-20261012/` and `.runs/pr-review-20261012/pytest-pair/`, three vulnerable and three fixed fresh runs each, all with the expected shape: controls passed, vulnerable security failed with `AssertionError` at `test_documents.py:64` in `test_security_rejects_outside_read` with the outside open in its witness, fixed security passed with witness exception `ValueError` and no opens, patch digest `c9ce0621…7673` everywhere. Mapped literally, all runs are `unusable` with `discovery_mismatch`, because the runs record ids relative to the fixture copy (`::test_benign_control`, classname empty) and the plan uses repository ids; result `failed`/`inconclusive`/`not_verified` in both directions. With one explicit rebase (the workspace is a copy of `benchmarks/fixtures/path-traversal`), vulnerable as baseline gives `completed`/`reproduced`/`verified` with no limitations in both sets; swapped gives `completed`/`not_reproduced`/`not_verified` with `baseline_not_reproduced`. Mapping inferences: the witness came from the security test's captured stdout inside the JUnit XML (a workload claim; see SPEC-0027 on operator witnesses), `path_reached` was inferred from the witness being emitted, and host-run environment identity used the uv.lock digest, runner script and interpreter path with named placeholders for policy and limits, identical within each set but different between sets. SPEC-0028 now makes the workspace root the repository root, which removes the rebase for future runs. Mapping script and output are retained privately under `.runs/evidence-assessment-live-20261012T213319Z/` on RIG0.
- `make test-config`: 457 passed in the cloud session and on RIG0.

## Decisions and next action

Defaults recorded in SPEC-0027. Next: add the `ObservationPlan` builder when the planner and authoring contracts merge. The assessment agent consumes these gates under SPEC-0030.
