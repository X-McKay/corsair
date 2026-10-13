---
id: HANDOFF-0077
kind: handoff
title: Evidence assessment on the agent package convention
status: recorded
updated: 2026-10-13
related: [PLAN-0056, SPEC-0052, IDEA-0006, HANDOFF-0076]
---

# Evidence assessment on the agent package convention

## Verified state

Branch `claude/project-thread-gzpz1j` from main `0ad9900` (#62 merged). `evidence_assessment` is split into `prompts.py`, `dependencies.py`, `validation.py`, `tools/read_evidence.py` and `tools/toolset.py`; `agent.py` keeps `CONFIG_VERSION` and the factory and re-exports moved names. `toolset_sha256` now lives in `corsair.agents.toolset_identity`, used by environment and assessment. The assessment eval reports `toolset_sha256`. No prompt, tool, budget, contract, durable activity name or chain behaviour changed.

## Validation and blockers

Recorded in PLAN-0056: identical offered-surface capture, pinned digest equal to the pre-split digest, 95 focused tests, scripted assessment evals 51/51 and 21/21 before and after with no changed row, environment eval unchanged. Unrun: live provider evals, durable worker run beyond the offline Temporal suites in `make test-config`.

#49 (open) changes four factory lines in `evidence_assessment/agent.py`; they remain in `agent.py`, so its merge needs only that hunk re-applied. #49 and #55 each add lines to `evals/evidence_assessment/evaluate.py`, near but not on the line this change adds.

## Decisions and next steps

Owner asked to cascade across all agents (2026-10-13). Next: identification into an active `issue_identification/` package with compatibility exports (#49 touches only its factory lines); authoring after #49 merges; planning after #44.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0056, SPEC-0052, docs/agent-packages.md and this handoff. Inspect git/source state and open PRs touching src/corsair/agents. Use the corsair-agent-scaffold skill. Move the next agent in PLAN-0056 order that no open PR rewrites, with an identical offered-surface capture, a pinned toolset digest and make eval before and after. Run make test-config, update PLAN-0056 and CURRENT.md, and write a new handoff.
```
