---
id: HANDOFF-0078
kind: handoff
title: Test authoring and issue identification on the agent package convention
status: recorded
updated: 2026-10-13
related: [PLAN-0056, SPEC-0052, IDEA-0006, HANDOFF-0077]
---

# Test authoring and issue identification on the agent package convention

## Verified state

Branch `claude/project-thread-gzpz1j` from main `af4d22d` (#49 merged). `test_authoring` is split into `dependencies.py`, `prompts.py`, `validation.py`, `tools/{read_source,write_test_file,run_tests}.py`, internal `tools/_history.py` and `tools/_preparation.py`, and `tools/toolset.py` exporting one digest over both toolsets. Issue identification now lives in `src/corsair/agents/issue_identification/` with both source modes; the old `issue_analysis` modules re-export what callers imported. The authoring and both identification evals report `toolset_sha256`. No prompt, tool, budget, contract, toolset id, agent name, durable activity name or chain behaviour changed.

## Validation and blockers

Recorded in PLAN-0056: identical offered-surface captures for authoring and both identification modes, pinned digests equal to the pre-split digests, 574 agent and chain tests, scripted authoring eval 18/18 and identification eval 16/16 before and after with no changed row, and again on `af4d22d`; `make test-config` 1361 passed. Unrun: live provider evals, the repository identification eval (needs a git capture and live provider), durable worker runs beyond the offline Temporal suites in `make test-config`.

## Decisions and next steps

Planning waits for #44 (held, rewrites the planner). Then the chain eval reports per-stage digests under `versions`. Historical analyst and reviewer code in `issue_analysis/` stays until a retention decision.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0056, SPEC-0052, docs/agent-packages.md and this handoff. Check whether #44 has merged or closed. If so, use the corsair-agent-scaffold skill to move test_planning with an identical offered-surface capture, a pinned toolset digest and make eval AGENT=planning before and after. Run make test-config, update PLAN-0056 and CURRENT.md, and write a new handoff.
```
