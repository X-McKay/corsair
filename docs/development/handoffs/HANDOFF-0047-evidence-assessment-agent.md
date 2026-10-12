---
id: HANDOFF-0047
kind: handoff
title: Evidence assessment agent implemented offline
status: recorded
updated: 2026-10-12
related: [SPEC-0030, PLAN-0029, SPEC-0027, PLAN-0026, HANDOFF-0043]
---

# Evidence assessment agent implemented offline

## Verified state

Built on the [HANDOFF-0043](HANDOFF-0043-disposition-gates.md) gates, on the same branch `claude/evidence-assessment-checks-e694q5`; resolve the commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0047-evidence-assessment-agent.md`. Added `src/corsair/agents/evidence_assessment/` (contracts, `read_evidence` toolset, `assess-evidence` skill, factory whose output function enforces current-run citations and runs `assess`/`admit`) and draft [SPEC-0030](../specs/SPEC-0030-evidence-assessment-agent.md) with [PLAN-0029](../plans/PLAN-0029-evidence-assessment-agent.md). SPEC-0027 now records the typed-expectation sources agreed with the planner thread (its PR #26). Nothing is connected to other stages.

## Validation and blockers

`tests/agents/test_evidence_assessment.py`: 17 passed. `make test-config`: 457 passed with the existing deprecation warnings. A six-attempt live smoke of prompt v1 on llm.almckay.io and the gates' retained-run validation ran on RIG0; results and limits are in PLAN-0029 and PLAN-0026. Prompt v2 (skill clarifications from that smoke) was rerun: it fixed neither error, and the gate rejected every over-claim in both rounds. Unrun and not claimed: Pydantic Evals and durable mode.

## Decisions and next steps

Rejected proposals are recorded, not retried; `read_source` deferred until `agents/source/` is on main. Next: an unconfounded sandbox-denial case, then native Evals cases for this stage.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0030, PLAN-0029, SPEC-0027 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Add native Pydantic Evals cases for the evidence assessment agent (SPEC-0018 runs and IDEA-0004 negatives, oracles outside inputs), then a bounded live baseline on the local provider. Do not connect the stage to others before that. Run make test-config, update records/CURRENT.md and write a new handoff.
```
