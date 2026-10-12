---
id: HANDOFF-0041
kind: handoff
title: End-to-end agent plan proposed
status: recorded
updated: 2026-10-12
related: [IDEA-0004, SPEC-0025, SPEC-0026, IDEA-0003, SPEC-0022, SPEC-0024, ISSUE-0006, ISSUE-0007, PLAN-0021]
---

# End-to-end agent plan proposed

## Verified state

Work began on clean main `95effd3` and was written on branch `claude/project-thread-ahp7lq`; resolve the published commit with `git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0041-end-to-end-agent-plan.md`. This change is documentation only: [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md) proposes purpose, input/output contracts, skills, tools and evaluation dimensions for the environment, test planning, test authoring and evidence assessment agents, the deterministic nodes on the critical path, a fixture-first E2E-0/1/2 sequence, and an assessment of the PydanticAI graph builder (not adopted; optional later spike). The user then accepted the plan and selected in-sandbox source fetch for real projects; draft [SPEC-0025](../specs/SPEC-0025-sandbox-source-fetch.md) defines it and ISSUE-0006 records it as the proposed narrower route. The user then directed: assume Azure DevOps fetch by exact commit, allow private repositories with the PAT supplied to OpenShell's credential proxy, and use standard public registries; SPEC-0025 now covers private repositories and draft [SPEC-0026](../specs/SPEC-0026-sandbox-dependency-fetch.md) covers dependency fetch. The provider placeholder behavior comes from current secondary documentation and is unverified against pinned OpenShell 0.1.3; private repositories stay blocked if the pinned release would expose the raw token. No source, agent, runtime or evaluation changed. No qualification state changed.

## Validation and blockers

`make test-config` passed 390 checks with the existing event-loop deprecation warning. No live, provider, Temporal or OpenShell checks were run or needed. ISSUE-0006, ISSUE-0007 and PLAN-0021 gates are unchanged.

## Decisions and next steps

IDEA-0004 is accepted (selected for specification); SPEC-0025 and SPEC-0026 are drafts. Its defaults: operator-supplied environment evidence until the first real case, assessment before authoring, the security outcome withheld from authoring development runs, no graph library. Next bounded action: move shared source contracts/toolset/provider for the planner as SPEC-0022 describes, then implement the planner.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, IDEA-0004, SPEC-0022, SPEC-0024 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Following accepted IDEA-0004, extract the shared source contracts/read_source toolset/provider for the planner and implement SPEC-0022 with its deterministic tests and evals. Verify provider placeholder substitution in pinned OpenShell 0.1.3 source; SPEC-0025/0026 live qualification can proceed independently on fresh admitted nodes. Do not connect unqualified stages; ISSUE-0006/0007 and PLAN-0021 gates remain. Run make test-config, update records/CURRENT.md and write a new handoff.
```
