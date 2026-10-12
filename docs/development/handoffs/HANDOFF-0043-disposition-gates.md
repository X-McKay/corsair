---
id: HANDOFF-0043
kind: handoff
title: Deterministic disposition gates implemented
status: recorded
updated: 2026-10-12
related: [SPEC-0027, PLAN-0026, IDEA-0004, SPEC-0018, SPEC-0022]
---

# Deterministic disposition gates implemented

## Verified state

Work began on main `83dec61` on branch `claude/evidence-assessment-checks-e694q5`; resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0043-disposition-gates.md`. Added `src/corsair/core/disposition.py`, the first `core/` module from [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md): typed per-run evidence contracts, `assess` (strongest permitted `execution`/`finding`/`fix` plus coded per-run limitations) and `admit` (accepts a proposal equal to or weaker than the permitted triple; never `refuted_in_scope`). Draft [SPEC-0027](../specs/SPEC-0027-disposition-gates.md) and [PLAN-0026](../plans/PLAN-0026-disposition-gates.md) record the rules and the defaults chosen. No agent, runner adapter, renderer, workflow or runtime changed; nothing connects to the gates yet. Record numbers SPEC-0027, PLAN-0026 and HANDOFF-0043 were picked to avoid colliding with the concurrent planner thread.

## Validation and blockers

`tests/unit/test_disposition.py`: 50 passed. `make test-config`: 440 passed with the existing warning, after one earlier run failed only because this handoff did not yet exist. Local shape check: actual pytest JUnit for the reviewed SPEC-0018 vulnerable variant fails at `test_documents.py:64: AssertionError`, a planned assertion line, and a scratch mapping of one actual run per variant gave `completed`/`reproduced`/`verified` (details and limits in PLAN-0026). Retained-run validation later ran on RIG0 and is recorded in PLAN-0026: literal ids fail on a path base mismatch, and with an explicit rebase both retained sets give the expected dispositions. No provider, Temporal or OpenShell checks were needed.

## Decisions and next steps

Defaults: a failed control blocks a conclusive finding; `not_reproduced` needs every baseline run safe; fix verification needs every run on both revisions valid and in one environment; unknown-reach test-phase sandbox events are attributed. Open: the typed `ObservationPlan` fields (expected exception, path, function, assertion lines, safe-behavior token) are not in SPEC-0022's free-text plan and need an owner. Next: the report renderer or the native runner adapter that produces `RunEvidence`.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0027, PLAN-0026 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. On RIG0, map the six retained SPEC-0018 runs in .runs/benchmark-admission-20261012/ into RunEvidence and record the gate results in PLAN-0026 without publishing raw evidence. Agree the ObservationPlan source with the SPEC-0022 planner work. Do not connect the gates to an agent before the assessment agent has its own spec. Run make test-config, update records/CURRENT.md and write a new handoff.
```
