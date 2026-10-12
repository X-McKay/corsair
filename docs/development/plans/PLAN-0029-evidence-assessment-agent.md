---
id: PLAN-0029
kind: plan
title: Evidence assessment agent
status: in_progress
updated: 2026-10-12
related: [SPEC-0030, SPEC-0027, IDEA-0004]
---

# Evidence assessment agent

## Objective and dependencies

Implement [SPEC-0030](../specs/SPEC-0030-evidence-assessment-agent.md), step 4 of the IDEA-0004 order, over the [SPEC-0027](../specs/SPEC-0027-disposition-gates.md) gates. Independent of the planner, authoring and environment threads; touches only `src/corsair/agents/evidence_assessment/`, its test and records.

## Steps

- [x] Contracts, `read_evidence` toolset, `assess-evidence` skill and factory with gate-backed output function.
- [x] Deterministic `FunctionModel` tests.
- [ ] Native Pydantic Evals cases (SPEC-0018 runs plus the IDEA-0004 negatives), development and held-out splits.
- [ ] Add `read_source` once `agents/source/` is on main, if evaluation shows it is needed.
- [ ] Live provider repeats on llm.almckay.io; durable stage.

## Validation and progress

2026-10-12, on branch `claude/evidence-assessment-checks-e694q5` (PR #25), after the gates: `uv run --locked python -m pytest tests/agents/test_evidence_assessment.py -q` 17 passed. Full `make test-config` result is in HANDOFF-0047. No provider, Temporal or OpenShell checks were run; none are claimed.

## Decisions and next action

Rejected proposals are kept, not retried. `read_source` deferred to avoid importing paths the planner thread is moving. Next: the Evals dataset. Stop condition: no connection to other stages before evals and a live baseline exist.
