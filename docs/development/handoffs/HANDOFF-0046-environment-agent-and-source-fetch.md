---
id: HANDOFF-0046
kind: handoff
title: Environment agent and sandbox source fetch, offline
status: recorded
updated: 2026-10-12
related: [SPEC-0029, PLAN-0028, SPEC-0025, SPEC-0026, IDEA-0004, ISSUE-0006]
---

# Environment agent and sandbox source fetch, offline

## Verified state

Branch `claude/environment-agent-n93amx` from main `83dec61`. Adds draft [SPEC-0029](../specs/SPEC-0029-environment-agent.md), [PLAN-0028](../plans/PLAN-0028-environment-agent-and-source-fetch.md) (blocked on live gates), `src/corsair/nodes/` (`source_fetch`, `phase_policy`, `dependency_inventory`), `src/corsair/agents/environment/` (contracts, tools, agent, `prepare-environment` skill) and their tests. Nothing is connected to a workflow, and nothing is qualified live.

## Validation and blockers

`make test-config`: 538 passed (390 baseline, 124 node tests, 24 agent tests). No OpenShell, provider or Temporal run. Live use is blocked by the absence of a qualified quota-enforcing storage volume for the sandbox workspace (SPEC-0025), and private repositories additionally by the unconfirmed OpenShell 0.1.3 credential placeholder substitution. Script tool availability in the toolchain images and OpenShell acceptance of the upload-pack rule glob are unverified.

## Decisions and next steps

Decisions are listed in PLAN-0028. The agent imports source contracts from `corsair.agents.issue_analysis.contracts`; the test-planning branch moves them to `corsair.agents.source` while keeping old paths working, so whichever merges second should switch imports. Next bounded actions: per-ecosystem inventory scripts, a policy-control adapter, the setup-replay node, then live qualification once storage is qualified.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0029, PLAN-0028, SPEC-0025, SPEC-0026 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Implement the next unchecked offline step in PLAN-0028 (per-ecosystem dependency inventory scripts, starting with Python). Do not run the fetch or the agent against a live sandbox while no quota-enforcing storage volume is qualified, and do not use a private repository until the 0.1.3 credential placeholder is confirmed. Run make test-config, update PLAN-0028 and CURRENT.md, and write a new handoff.
```
