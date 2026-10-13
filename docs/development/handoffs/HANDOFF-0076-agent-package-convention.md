---
id: HANDOFF-0076
kind: handoff
title: Agent package convention on the environment agent
status: recorded
updated: 2026-10-13
related: [IDEA-0006, SPEC-0052, PLAN-0056, SPEC-0044]
---

# Agent package convention on the environment agent

## Verified state

Branch `claude/project-thread-gzpz1j` from main `a9ba2b0`. IDEA-0006 accepted with changes; SPEC-0052 and PLAN-0056 record the selected variant. The environment agent is split into the convention's files with old imports kept; `TOOLSET_SHA256` is exported, pinned in a toolset test, written by the environment eval and compared by `make eval`. `docs/agent-packages.md` and the `corsair-agent-scaffold` skill (Claude folder plus Codex symlink) are added. No other agent package, prompt, tool, budget, contract or chain path changed.

## Validation and blockers

- Offered-surface capture before and after the split: byte-identical. Pre-split digest on `a9ba2b0` equals the pinned digest.
- Environment, toolset and runtime hand-off tests: 66 passed.
- `make eval AGENT=environment` scripted: 16/16 before (`20261013T105956Z`) and after (`20261013T110234Z`), only identity change `toolset_sha256` appearing; evidence stayed in the cloud container.
- `make test-config` on `a9ba2b0` plus this change: 1230 passed.
- Unrun: live environment eval, sandbox, durable. Skill discovery in the actual Claude Code and Codex clients is not smoke-tested.

## Decisions and next steps

The owner asked to cascade across all agents once this succeeds. Next bounded action: after #49 merges, move `evidence_assessment` and promote the digest helper to a shared module; then authoring, then planning after #44, then identification into an active `issue_identification/` package. Do not move a package an open PR changes.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0056, SPEC-0052, docs/agent-packages.md and this handoff. Inspect git/source state and verify recorded facts. Use the corsair-agent-scaffold and corsair-development skills. Confirm #49 has merged, then move src/corsair/agents/evidence_assessment to the convention with no change to what the model is offered: capture before and after, pin its toolset digest, promote toolset_sha256 to a shared helper, and compare make eval AGENT=assessment before and after. Stop if an open PR still changes that package. Run make test-config, update PLAN-0056 and CURRENT.md, and write a new handoff.
```
