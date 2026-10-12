---
id: PLAN-0025
kind: plan
title: Read-only test planning agent
status: in_progress
updated: 2026-10-12
related: [SPEC-0022, IDEA-0004, SPEC-0024, SPEC-0018, SPEC-0023, ISSUE-0007]
---

# Read-only test planning agent

## Objective and dependencies

Implement [SPEC-0022](../specs/SPEC-0022-test-planning-agent.md), steps 1 and 2 of accepted [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md): move the shared saved-source contracts, `read_source` toolsets and `LocalModelConfig` to their second consumer's shared location, then build the isolated planner with deterministic tests and native evals. No durable stage, graph connection or live qualification is in scope for the offline deliverable. The live provider smoke needs the local model endpoint, reachable only from RIG0. Identification admission (ISSUE-0007) and the authoring/assessment stages do not block this work.

## Steps

- [x] Move `Contract`, `confined_path`, `SourceFile`, `SourceReference`, `SourceExcerpt`, `SourceLine`, `SourceRead`, `Fact`, `Citation` and the inventory bound to `agents/source/contracts.py`; the confined reader and both native toolset shapes (ranged, windowed) to `agents/source/tools.py`; the provider seam to `agents/provider.py`. Issue analysis re-exports its names and keeps toolset ids `issue_analysis_source` and `issue_identification_source`. Check: 194 agent/Temporal-fixture checks unchanged.
- [x] Add `agents/test_planning/` (contracts, factory, trusted output function, `plan-two-tests` skill) and `evals/test_planning/` (six frozen cases, curated evaluators, receipts).
- [x] Add `tests/agents/test_test_planning.py`: reference plan admitted; unsupported without test details, refused with them or uncited; refusal of non-ready identification, third test, duplicate ids, unapproved path, altered discovery tokens, uncited, unread and stale-run citations, scope expansion, verdict field and a call not naming the target; unknown tool; skill/tool/schema on the native wire; native eval receipts and failure denominator; move identity.
- [ ] Freeze source/corpus/config and run the bounded local-provider smoke on RIG0 (`--provider-config`), then review actual outputs independently. Requires the local endpoint.
- [x] Review, records, `CURRENT.md` and handoff.

## Validation and progress

Base: main `83dec61`. `make test-config` passed 390 before any change, and 417 after (27 new planner checks; one existing event-loop deprecation warning). Scripted native evals: 12/12 attempts (6 cases × 2 repeats) passed every assertion with zero unknown tools, evidence written only to a scratch directory. Each parametrized refusal was checked to fail for its intended reason (extra field, distinct ids, approved path, discovery tokens, minimum citations, current-run read coverage, scope, target call). No provider, Temporal or OpenShell check ran; no live qualification is claimed.

Live001 (RIG0, exact head `e041021`, prompt v1, provider config copied from the identification run: vLLM `Qwen3.6-35B-A3B-NVFP4` at llm.almckay.io, response cap 8192, server-default thinking, timeout 120s; input/config SHA256 manifest in `.runs/test-planning-20261012/manifest.txt`, git-ignored): exit 1, one run, no retries, 12m20s wall. Only 3/12 attempts produced a plan. Eight attempts exhausted the 8192 response cap with reasoning only (finish_reason=length) after correct reads: both repeats of the unguarded, injection and unsupported-observation cases and one no-baseline repeat. Both implementation-absent repeats read the unlisted `documents.py` first and ended at once under zero tool retries. Both guarded repeats passed every check (one after a cap hit and one fenced-JSON correction); the one completed no-baseline repeat returned ready instead of unsupported. Zero unknown tools, provider usage present in every attempt. Totals: 31 requests, 112,054 input and 81,366 output tokens. Review of the guarded plan: semantics correct (`relative_to` raises `ValueError`), but its security fixture writes to `tmp_path.parent`, outside the scratch location. The planner is not qualified.

Prompt v2 responds to the two attributable failures without case facts: the skill now checks preconditions first (null baseline test, target path not in the inventory, unlisted observation facility) and says an unlisted read ends the run, and asks for one object matching the schema. Zero tool retries stay, because an invented path is still an authority failure. Live002 pairs prompt v2 with a native `thinking_token_budget` of 2048 inside the unchanged 8192 response cap, the profile PLAN-0018 found enforced on this server. Two variables change together, so live002 compares profiles rather than attributing a cause; corpus, budgets and evaluators are unchanged.

## Decisions and next action

- The draft discriminated union reaches the native output function as one `plan` argument (PydanticAI wraps a non-model parameter); the model sees `{"plan": {...}}`. Separate output functions were rejected because prompted mode would add a second wrapper.
- Approved-path and discovery-token checks live in the contract validator and run under native `validation_context` (the run's `TestPlanningInput`); structure and distinct ids are checked without context.
- `EnvironmentEvidence` adds `observation_facilities` (needed for the spec's unsupported-witness case) and `BaselineTest{test_id, path}`; the baseline file must be in the inventory. `observation_facilities` is operator/sandbox configuration, not something the environment agent discovers (PR #27); whoever assembles `EnvironmentEvidence` supplies it from the sandbox profile. The planner uses the windowed reader (tool-computed end), which fixed the identification v2 failure.
- Evaluation uses a native `cases.yaml` with oracles in metadata (SPEC-0023 convention) instead of the spec's earlier `fixtures/*.json` and `oracles.json` layout.
- `ReadyTestPlan.security_expectation{failure_type, safe_behavior}` gives the SPEC-0027 disposition gates typed identifiers (pattern `^[A-Za-z0-9_.:-]+$`) instead of prose, as the gates work requested. The security test path and function come from `test_path` and `test_id`; planned assertion lines exist only in the frozen patch, so the authoring output must carry them.
- Approved test paths may not overlap saved source paths (refused at input construction), as the authoring stage (PR #28) requires. Its stricter pytest node-id shape (`path.py::name`) stays an authoring check, because the planner contract is framework-neutral.
- The fixture discovery tokens `python -m pytest --collect-only -q` are evaluation data, not a runnable command: real pytest needs operator flags such as `-c /dev/null --rootdir .` (pytest 9 prints node ids with an empty file part without `--rootdir`). The corpus stays frozen for the live run; a real environment supplies its own tokens.
- Read collection from current-run messages stays inline per stage; only what SPEC-0022 names is shared.

Next: run the frozen provider smoke on RIG0 and record it here; keep the planner disconnected until identification and authoring are admitted.
