---
id: HANDOFF-0041
kind: handoff
title: End-to-end agent plan proposed
status: recorded
updated: 2026-10-12
related: [IDEA-0004, IDEA-0003, SPEC-0022, SPEC-0024, ISSUE-0006, ISSUE-0007, PLAN-0021]
---

# End-to-end agent plan proposed

## Verified state

Work began on clean main `95effd3` and was written on branch `claude/project-thread-ahp7lq`; resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0041-end-to-end-agent-plan.md`. This change is documentation only: [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md) proposes purpose, input/output contracts, skills, tools and evaluation dimensions for the environment, test planning, test authoring and evidence assessment agents, the deterministic nodes on the critical path, a fixture-first E2E-0/1/2 sequence, and an assessment of the PydanticAI graph builder (not adopted; optional later spike). No source, agent, runtime or evaluation changed. No qualification state changed.

## Validation and blockers

`make test-config` passed 390 checks with the existing event-loop deprecation warning. No live, provider, Temporal or OpenShell checks were run or needed. ISSUE-0006, ISSUE-0007 and PLAN-0021 gates are unchanged.

## Decisions and next steps

IDEA-0004 is proposed, not accepted. Its defaults: operator-supplied environment evidence until the first real case, assessment before authoring, the security outcome withheld from authoring development runs, no graph library. Next bounded action, if the user accepts the order: move shared source contracts/toolset/provider for the planner as SPEC-0022 describes, then implement the planner.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, IDEA-0004, SPEC-0022, SPEC-0024 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. If the user accepted IDEA-0004's order, extract the shared source contracts/read_source toolset/provider for the planner and implement SPEC-0022 with its deterministic tests and evals. Do not connect unqualified stages; ISSUE-0006/0007 and PLAN-0021 gates remain. Run make test-config, update records/CURRENT.md and write a new handoff.
```
