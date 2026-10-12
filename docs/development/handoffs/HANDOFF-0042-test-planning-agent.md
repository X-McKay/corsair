---
id: HANDOFF-0042
kind: handoff
title: Test planning agent implemented offline
status: recorded
updated: 2026-10-12
related: [PLAN-0025, SPEC-0022, IDEA-0004, SPEC-0024, ISSUE-0007]
---

# Test planning agent implemented offline

## Verified state

Work began on clean main `83dec61` on branch `claude/test-planning-agent-mpdk0y`; resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0042-test-planning-agent.md`. Delivered under [PLAN-0025](../plans/PLAN-0025-test-planning-agent.md): shared saved-source contracts and the ranged/windowed `read_source` toolsets moved to `src/corsair/agents/source/`, the provider seam to `src/corsair/agents/provider.py`, with issue-analysis re-exports and unchanged toolset ids; the isolated planner in `src/corsair/agents/test_planning/` (contracts, factory, trusted output function, `plan-two-tests` skill); [evals](../../../evals/test_planning/README.md) with six frozen cases; and `tests/agents/test_test_planning.py`. The planner is not connected to identification, authoring or any workflow. [SPEC-0022](../specs/SPEC-0022-test-planning-agent.md) is accepted with its implementation refinements recorded.

## Validation and blockers

`make test-config`: 390 passed before the change, 417 after (one existing deprecation warning). Scripted native evals: 12/12 attempts passed every assertion, zero unknown tools. No provider, Temporal or OpenShell check ran. The local-provider smoke is unrun: it needs the local model endpoint, reachable only from RIG0. ISSUE-0007 still blocks end-to-end admission of the identification the planner consumes.

## Decisions and next steps

See PLAN-0025 decisions: `plan` argument wrapping of the draft union, contract validation under native validation context, `observation_facilities` and `BaselineTest` in the environment evidence, windowed reader, `cases.yaml` layout. The test authoring thread consumes these contracts. Next bounded action: freeze source/corpus/config and run the provider smoke on RIG0, then review actual outputs; stop before connecting the planner to any other stage.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0022, PLAN-0025 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. On RIG0, freeze source, evals/test_planning/cases.yaml and the provider config, then run `PYTHONPATH=src:. .venv/bin/python -m evals.test_planning.evaluate --evidence .runs/test-planning-<date>/live-001 --provider-config <config>`. Retain every attempt, review actual plans independently, and record results in PLAN-0025 without rewriting failures. Do not connect the planner to other stages; ISSUE-0007 remains. Run make test-config, update records/CURRENT.md and write a new handoff.
```
