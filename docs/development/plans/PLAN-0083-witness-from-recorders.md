---
id: PLAN-0083
kind: plan
title: Witness requests from the framework table's recorders
status: in_progress
updated: 2026-10-13
related: [SPEC-0073, PLAN-0079]
---

# Witness requests from the framework table's recorders

## Objective and dependencies

Implement SPEC-0073 so `corsair run` requests a witness for frameworks whose table entry lists a recorder. Depends
on PR #109 (the framework table, `corsair run`); coordinate with PLAN-0082, which amends SPEC-0033/SPEC-0040 on
witness attribution and subject binding.

## Steps

- [x] `witness_request(..., recorders)` binds the identified target and planned subject under the recorder rules;
  envelope behaviour unchanged.
- [x] `FixtureCase.witness_from_recorders`; `build` sets it for issue requests.
- [ ] A live corpus run with the witness (after the first corpus case run on RIG0).

## Validation and progress

2026-10-13, cloud container: `tests/unit/test_witness_from_recorders.py` (binding, refusals, envelope precedence)
and the issue-entry tests pass; full suite result in the PR. Earlier Docker check of the pytest route on the corpus
case: with a request of this shape (`app.py`, `read_doc`, `outside.txt`) the probe captured a witness on both
revisions.

## Decisions and next action

Rules, not per-case approval: the table names what each framework can witness; the chain binds the concrete request
from admitted outputs. Next: PR after #109 merges; then the live run.
