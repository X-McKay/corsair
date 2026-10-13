---
id: PLAN-0056
kind: plan
title: Agent package convention and cascade
status: in_progress
updated: 2026-10-13
related: [SPEC-0052, IDEA-0006, SPEC-0044, HANDOFF-0076, HANDOFF-0077, HANDOFF-0078]
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
- [x] Authoring (`test_authoring`), after #49 merged: `tools.py` became `dependencies.py` (budget and dependencies) plus `tools/_history.py` (run-history reads shared by tools and finalizer), `tools/_preparation.py` (`while_edits_can_help`), `tools/{read_source,write_test_file,run_tests}.py` and `tools/toolset.py` with both toolset ids unchanged; prompts and skill into `prompts.py`, finalizer into `validation.py`; `agent.py` keeps `CONFIG_VERSION` and the factory; `static.py` and `admission.py` keep their names. One digest over both toolsets in offered order (`toolsets_sha256`).
- [ ] Planning (`test_planning`), after #49 and #44 merge or #44 is closed.
- [x] Identification: active `issue_identification/` package holding both source modes (inline SPEC-0024, repository SPEC-0038): `contracts.py` (with `RepositoryIdentity`, `RepositoryIssueInput`), `dependencies.py`, `prompts.py`, `validation.py` (shared `finalize_draft` plus one output function per mode), `skills/` (moved byte-identical), `tools/toolset.py` binding the shared `window_source_tools` and `repository_source_tools` under their unchanged ids, and `agent.py` with both factories and config versions. `issue_analysis/identification.py`, `repository_identification.py`, `identification_contracts.py` and `tools/identification.py` are re-export shims; historical analyst/reviewer code stays where it is until a retention decision. `toolset_identity` now also digests a wrapped toolset (the repository mode's budget-withdrawal `PreparedToolset`), recording the wrapper type and its rule's qualified name; unwrapped digests are unchanged.
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

Authoring and identification moves, 2026-10-13, cloud container, host only, first on main `759b016` plus #49:

- Offered-surface capture for authoring (instructions, prompt, both toolsets with prepare and sequential flags, output tools) and for both identification modes: identical before and after.
- Pinned digests equal the pre-split digests: authoring `6ffc0788…2b57`, inline identification `de138f51…8c61`, repository identification `67947c2d…e2c1`.
- Agent, composition and chain tests: `pytest -q tests/agents tests/temporal/test_chain_composition.py` 574 passed.
- `make eval AGENT=authoring` scripted, development: `20261013T121904Z` 18/18 before, `20261013T122112Z` 18/18 after. `make eval AGENT=identification` scripted, development: `20261013T122216Z` 16/16 before, `20261013T122756Z` 16/16 after. No assertion or case changed; identity change only `toolset_sha256` appearing. The repository identification eval (git capture plus live provider) also writes `toolset_sha256` and was not run.
- Rebased onto main `af4d22d` (#49 merged): captures still identical to the pre-move surfaces; scripted reruns authoring `20261013T124248Z` 18/18, identification `20261013T124253Z` 16/16, assessment `20261013T124256Z` 51/51, environment `20261013T124304Z` 16/16, no changed row. `make test-config`: 1361 passed.

## Decisions and next action

- The owner adopted the recommended variant on 2026-10-13 and asked to cascade across all agents once it succeeds.
- Next: planning after #44 merges or is closed; then the chain eval reports per-stage digests.
