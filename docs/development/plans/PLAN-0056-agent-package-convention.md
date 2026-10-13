---
id: PLAN-0056
kind: plan
title: Agent package convention and cascade
status: in_progress
updated: 2026-10-13
related: [SPEC-0052, IDEA-0006, SPEC-0044, HANDOFF-0076]
---

# Agent package convention and cascade

## Objective and dependencies

Implement [SPEC-0052](../specs/SPEC-0052-environment-agent-package-convention.md) on the environment agent, then move each other agent to the [convention](../../agent-packages.md) without behaviour change. Base: main `a9ba2b0` (#48 merged). Planning, authoring, assessment and identification wait: #49 changes all four and held #44 changes planning. #51 changes `environment/frameworks.py` and the environment skill, which this plan does not touch.

## Steps

- [x] Capture what the environment agent offers the model on main (`2a8af2f`; #48 did not change the package).
- [x] Split the environment package into `prompts.py`, `dependencies.py`, `validation.py`, `tools/<tool>.py` and `tools/toolset.py`; keep old imports.
- [x] Export `TOOLSET_SHA256`; pin it in `tests/agents/test_environment_toolset.py`; write it to the environment eval configuration; add it to `evals/run.py` identity.
- [x] Write `docs/agent-packages.md` and the `corsair-agent-scaffold` skill with its Codex symlink; link both from the development guide and architecture.
- [x] Validate (below) and open a draft PR.
- [ ] Assessment (`evidence_assessment`), after #49 merges: split `agent.py`/`tools.py`; promote `toolset_sha256` to a shared helper (second consumer); add `toolset_sha256` to its eval identity.
- [ ] Authoring (`test_authoring`), after #49 merges: move dependencies out of `tools.py`, prompts and finalizer out of `agent.py`; `static.py` and `admission.py` keep their names.
- [ ] Planning (`test_planning`), after #49 and #44 merge or #44 is closed.
- [ ] Identification: create the active `issue_identification/` package with compatibility exports from `issue_analysis/`, after #49 merges; historical analyst/reviewer code stays where it is until a retention decision.
- [ ] Chain eval: report the per-stage toolset digests under `versions` once every stage exports one.

Each follow-on move is its own PR and repeats the capture, byte-equality, toolset test and before/after `make eval` steps.

## Validation and progress

Environment move, 2026-10-13, cloud container, host only:

- Offered-surface capture (recording `FunctionModel`, scratch script, not committed): identical before (`2a8af2f`) and after the split.
- Pre-split digest computed on a `a9ba2b0` worktree: `cdaf4dcd…dd0a1`, equal to the post-split `TOOLSET_SHA256`.
- `uv run --locked python -m pytest -q tests/agents/test_environment.py tests/agents/test_environment_evals.py tests/agents/test_environment_toolset.py tests/unit/test_runtime_environment.py`: 66 passed.
- `make eval AGENT=environment` scripted: before `20261013T105956Z-development-scripted` (on `2a8af2f`) 16/16 clean; after `20261013T110234Z-development-scripted` 16/16 clean, every assertion and case unchanged, identity change only `toolset_sha256: null -> cdaf4dcd…`. Results under `.runs/evals/environment/` in the cloud container (not retained).
- `make test-config` on `a9ba2b0` plus this change: 1230 passed.

Unrun: live-provider environment eval (not needed for a no-behaviour move; the offered surface is byte-identical), any sandbox or durable run (the agent is unconnected, SPEC-0029).

## Decisions and next action

- The owner adopted the recommended variant on 2026-10-13 and asked to cascade across all agents once it succeeds.
- Next: after #49 merges, move `evidence_assessment` as the second package and promote the digest helper.
