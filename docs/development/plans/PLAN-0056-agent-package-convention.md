---
id: PLAN-0056
kind: plan
title: Agent package convention and cascade
status: in_progress
updated: 2026-10-13
related: [SPEC-0052, IDEA-0006, SPEC-0044, HANDOFF-0076, HANDOFF-0077]
---

# Agent package convention and cascade

## Objective and dependencies

Implement [SPEC-0052](../specs/SPEC-0052-environment-agent-package-convention.md) on the environment agent, then move each other agent to the [convention](../../agent-packages.md) without behaviour change. Base: main `a9ba2b0` (#48 merged). Planning, authoring, assessment and identification wait: #49 changes all four and held #44 changes planning. #51 changes `environment/frameworks.py` and the environment skill, which this plan does not touch.

## Steps

- [x] Capture what the environment agent offers the model on main (`2a8af2f`; #48 did not change the package).
- [x] Split the environment package into `prompts.py`, `dependencies.py`, `validation.py`, `tools/<tool>.py` and `tools/toolset.py`; keep old imports.
- [x] Export `TOOLSET_SHA256`; pin it in `tests/agents/test_environment_toolset.py`; write it to the environment eval configuration; add it to `evals/run.py` identity.
- [x] Write `docs/agent-packages.md` and the `corsair-agent-scaffold` skill with its Codex symlink; link both from the development guide and architecture.
- [x] Validate (below) and open a draft PR (#62, merged as `0ad9900`).
- [x] Assessment (`evidence_assessment`): split into `prompts.py`, `dependencies.py`, `validation.py`, `tools/read_evidence.py`, `tools/toolset.py`; `CONFIG_VERSION` and the factory stay in `agent.py`; `toolset_sha256` promoted to `corsair.agents.toolset_identity` (second consumer); digest pinned and reported by the assessment eval. Moved before #49 merges because #49 changes only four factory lines there (`tool_budget()` import and capability, config version), which stay in `agent.py` (owner asked to cascade, 2026-10-13); the merge with #49 also conflicts in `CURRENT.md` and `composition/direct.py` (see HANDOFF-0077).
- [ ] Authoring (`test_authoring`), after #49 merges: move dependencies out of `tools.py`, prompts and finalizer out of `agent.py`; `static.py` and `admission.py` keep their names.
- [x] Planning (`test_planning`), after #49 and #44 merged: split into `prompts.py`, `dependencies.py`, `validation.py`, `tools/_history.py`, `tools/_preparation.py` and `tools/toolset.py`. The planner has one tool, the shared `window_source_tools` reader, bound under its own `test_planning_source` id (no copied `read_source` module, as for identification); `offered_tools()` wraps it in the native `PreparedToolset` with `withdraw_when_read`. `CONFIG_VERSION` and the factory stay in `agent.py`, which re-exports the moved names; digest pinned in `tests/agents/test_test_planning_toolset.py` and reported by the planning eval.
- [ ] Identification: create the active `issue_identification/` package with compatibility exports from `issue_analysis/`; #49 changes only four factory lines there; historical analyst/reviewer code stays where it is until a retention decision.
- [ ] Chain eval: report the per-stage toolset digests under `versions` once every stage exports one.

Each follow-on move is its own PR and repeats the capture, byte-equality, toolset test and before/after `make eval` steps.

## Validation and progress

Environment move, 2026-10-13, cloud container, host only:

- Offered-surface capture (recording `FunctionModel`, scratch script, not committed): identical before (`2a8af2f`) and after the split.
- Pre-split digest computed on a `a9ba2b0` worktree: `cdaf4dcd…dd0a1`, equal to the post-split `TOOLSET_SHA256`.
- `uv run --locked python -m pytest -q tests/agents/test_environment.py tests/agents/test_environment_evals.py tests/agents/test_environment_toolset.py tests/unit/test_runtime_environment.py`: 66 passed.
- `make eval AGENT=environment` scripted: before `20261013T105956Z-development-scripted` (on `2a8af2f`) 16/16 clean; after `20261013T110234Z-development-scripted` 16/16 clean, every assertion and case unchanged, identity change only `toolset_sha256: null -> cdaf4dcd…`. Results under `.runs/evals/environment/` in the cloud container (not retained).
- `make test-config` on `a9ba2b0` plus this change: 1230 passed.

Assessment move, 2026-10-13, cloud container, host only, on `0ad9900`:

- Offered-surface capture (instructions, prompt, tool and output definitions, retries, toolset id): identical before and after; environment capture still identical after the digest helper moved.
- Pre-split assessment digest `b488713d…e802` equals the pinned `TOOLSET_SHA256`.
- Assessment and environment tests: 95 passed.
- `make eval AGENT=assessment` scripted, development: `20261013T112928Z` 51/51 before, `20261013T113108Z` 51/51 after; held_out: `20261013T112936Z` 21/21 before, `20261013T113116Z` 21/21 after; no assertion or case changed; identity change only `toolset_sha256` appearing. Environment rerun `20261013T113121Z` 16/16 with no change.
- `make test-config`: 1232 passed; configuration guards rerun after the record edits: 151 passed.

Unrun: live-provider environment eval (not needed for a no-behaviour move; the offered surface is byte-identical), any sandbox or durable run (the agent is unconnected, SPEC-0029).

Planning move, 2026-10-13, cloud container, host only, on `311d8cd` (#44 merged), rebased onto `497db9f` (#74, no agent change):

- Offered-surface capture (scratch script, not committed): a recording `FunctionModel` over a three-request run (two reads, then the output tool) records instructions, function tools, output tools, text-output flag and model settings on every request, including the third request where the reader is withdrawn; plus agent name, the rendered prompt for all six development cases, the admitted plan, prompt/config versions, toolset id, tool retries and the digest. Identical before and after.
- Pre-split digest `80bdf242…c1c9` (of `window_source_tools("test_planning_source")`; the `PreparedToolset` rule is outside the digest on main, as for authoring's per-tool prepare) equals the pinned `TOOLSET_SHA256`.
- `uv run --locked pytest -q tests/agents tests/temporal/test_chain_composition.py`: 597 passed.
- `make eval AGENT=planning` scripted, development: `20261013T130900Z` 12/12 before, `20261013T131155Z` 12/12 after; no assertion, case or token mean changed; identity change only `toolset_sha256: null -> 80bdf242…`. Results under `.runs/evals/planning/` in the cloud container (not retained).
- `make test-config`: 1383 passed; configuration guards rerun after the record edits: 177 passed.

Unrun: live-provider planning eval (model server held by another thread; not needed for a no-behaviour move with a byte-identical offered surface), held-out planning sets, durable worker run beyond the offline Temporal suites in `make test-config`.

## Decisions and next action

- The owner adopted the recommended variant on 2026-10-13 and asked to cascade across all agents once it succeeds.
- Next: identification and authoring in #82; planning moved here. Then the chain eval reports per-stage toolset digests.
