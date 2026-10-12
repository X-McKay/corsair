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
- [ ] Validate against the six retained SPEC-0018 runs in `.runs/benchmark-admission-20261012/` on RIG0 (blocked from this session, below).
- [ ] Typed `ObservationPlan` source: agree with the planner thread whether SPEC-0022 exposes these fields or a reviewed builder derives them.
- [ ] Report renderer, as its own step.

## Validation and progress

2026-10-12, cloud session on branch `claude/evidence-assessment-checks-e694q5` from main `83dec61`:

- `uv run --locked python -m pytest tests/unit/test_disposition.py -q`: 50 passed. The first draft let one baseline timeout coexist with `fix: verified`; corrected to require every baseline run to reproduce, per the contract's "it still cannot verify the fix".
- Local fixture check (repository-owned SPEC-0018 bytes only, scratch directory outside the repository, not retained): pytest on the vulnerable variant exited 1 with the JUnit failure ending `test_documents.py:64: AssertionError`, the first planned assertion line; the fixed variant exited 0 and its security witness recorded `ValueError` with no opens. A scratch mapping of that actual JUnit and witness stdout into `RunEvidence` gave `completed`/`reproduced`/`verified` with no limitations. One run per variant, host Python 3.12.3; this is a shape check, not a repeat of the SPEC-0018 qualification, and the mapping script is not the runner adapter.
- Retained-run validation: unrun. Access to the RIG0 checkout was refused by this session's permission classifier; it needs a session on RIG0 or the user's permission.
- `make test-config`: see the handoff for the recorded result.

## Decisions and next action

Defaults recorded in SPEC-0027. Next: run the six retained runs through the gate on RIG0, then settle the `ObservationPlan` source with the planner. Stop condition: none of this connects to an agent until the assessment agent's own spec exists.
