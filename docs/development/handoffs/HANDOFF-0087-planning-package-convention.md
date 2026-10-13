---
id: HANDOFF-0087
kind: handoff
title: Test planning on the agent package convention
status: recorded
updated: 2026-10-13
related: [PLAN-0056, SPEC-0052, IDEA-0006, HANDOFF-0077, HANDOFF-0062]
---

# Test planning on the agent package convention

## Verified state

Branch `claude/planning-layout-k5v8wa` from main `497db9f` (#44 and #74 merged), merged with main `462306a` (#82). `test_planning` is split into `prompts.py` (prompt version, instructions, skill exports, `planning_prompt`), `dependencies.py` (`PlanningDependencies`), `validation.py` (`finalize_plan`, `_symbol_occurs`), `tools/_history.py` (this run's reads), `tools/_preparation.py` (`withdraw_when_read`) and `tools/toolset.py` (`planning_tools`, `offered_tools`, `TOOLSET_ID`, `TOOLSET_SHA256`). The only tool is the shared `window_source_tools` reader under the planner's own id, so there is no `tools/read_source.py` copy. `agent.py` keeps `CONFIG_VERSION` and the factory and re-exports the moved names; `evals/test_planning/evaluate.py`, `composition/direct.py` and the planning test import from the new modules, and the eval reports `toolset_sha256`. No prompt, tool, budget, contract, durable activity name or chain behaviour changed; the planner stays unqualified as recorded in HANDOFF-0062.

## Validation and blockers

Recorded in PLAN-0056: identical offered-surface capture (including the request after the reader is withdrawn), reader digest pinned to the pre-split value and `TOOLSET_SHA256` over the offered `PreparedToolset` (`68bfbba4…`, after Codex's review), 597 agent and chain-composition tests, scripted planning eval 12/12 before and after with no changed row, `make test-config` 1383 passed, and 1387 passed after merging #82. Unrun: live-provider and held-out planning evals, durable worker run beyond the offline Temporal suites.

#82 (identification and authoring) merged as `462306a` while this PR was open; the branch merged main, keeping #82's `issue_identification` and authoring `dependencies` imports beside this change's planning imports and both record entries. #82's `toolset_identity` wrapper support lets `TOOLSET_SHA256` digest the offered `PreparedToolset` (done after Codex's review); the reader digest stays pinned to its pre-split value. Captures and checks were rerun after the merge.

## Decisions and next steps

Owner asked to migrate the remaining agents once #49 and #44 merged (2026-10-13). With this change every active agent is on the convention; the remaining PLAN-0056 step is the chain eval reporting per-stage toolset digests under `versions`.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0056, SPEC-0052, docs/agent-packages.md and this handoff. Inspect git/source state and open PRs touching src/corsair/agents and evals/. Report each stage's toolset digest under `versions` in the chain eval (the last PLAN-0056 step), without changing any stage's offered surface. Run make test-config and the affected make eval runs, update PLAN-0056 and CURRENT.md, and write a new handoff.
```
