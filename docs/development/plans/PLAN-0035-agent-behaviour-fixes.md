---
id: PLAN-0035
kind: plan
title: Planner and author budget discipline, author blocked status, assessor witness grounding
status: in_progress
updated: 2026-10-13
related: [PLAN-0031, PLAN-0025, PLAN-0027, PLAN-0029, PLAN-0030, SPEC-0022, SPEC-0028, SPEC-0030, ISSUE-0007]
---

# Planner and author budget discipline, author blocked status, assessor witness grounding

## Objective and dependencies

Fix three agent behaviours found live on the E2E-0 smoke (PLAN-0031) and earlier isolated runs (PLAN-0025, PLAN-0029, PLAN-0030), without changing the disposition gates (SPEC-0027) or any contract shape:

1. Test planning ran out of the 16384 response cap in 2 of 4 composition attempts, all reasoning. The composition used one provider configuration for every stage with no thinking budget; PLAN-0025 live002 had already shown a 2048 thinking budget inside an 8192 cap removes reasoning runaway, with re-reads of already-read ranges as the remaining budget loss.
2. Test authoring kept rewriting its test after every development run was a `workspace_failure` (the workspace refused before any test ran) and then exhausted the cap instead of returning `blocked`.
3. Evidence assessment proposed `reproduced`/`verified` 2/2 over evidence with no witness item, treating the test's own audit print as a witness, and in PLAN-0029 case (c) proposed a verified fix when the witness's safe behaviour differed from the plan's.

Independent of witness capture (SPEC-0033/PLAN-0033) and the fully live chain (PLAN-0034); both consume these agents, so prompt and budget changes are reported to them.

## Steps

- [x] Planning: skill step 10 asks for each needed range once (an earlier read stays in context), then the plan, deciding fields rather than deliberating (`test-planning-v3`). The fixture E2E CLI takes `--stage-profiles` (per-stage `response_token_limit`, `thinking_mode`, `thinking_token_budget`, `timeout_seconds` layered on the base `LocalModelConfig` and revalidated); `evals/fixture_e2e/stage-profiles.json` gives identification 8192, planning and authoring 8192 with a 2048 thinking budget, assessment 16384 (the PLAN-0030 choice). Budgets stay operator-owned configuration, not agent code, so agent factories stay provider-neutral.
- [x] Authoring: native tool `prepare` hides `write_test_file` and `run_tests` once the latest executed development run is a `workspace_failure` or the run budget is dispatched, leaving only the output contract; a final `workspace_failure` gets a retry message naming `blocked`/`sandbox`; skill steps 8 and 9 say a workspace or report failure is not a test-code problem and to return at once when the tools disappear (`test-authoring-v2`, `test-authoring-config-v2`). The `persistent_collection_error` eval case no longer scripts a fourth run past the budget (now an unknown tool); its expected result is unchanged.
- [x] Assessment: the output function requires a cited `witness` item of the baseline revision for `reproduced`/`not_reproduced`, and of both revisions for `verified`; with no witness item for that revision the retry names the weaker value. The prompt states per-revision witness counts; the skill says test-process output is a claim, a witness's safe behaviour must equal `expected_safe_behavior`, never compare source digests with the frozen patch digest, and to take the weaker value instead of deliberating (`evidence-assessment-v3`). This is an agent-side citation rule; the gates are unchanged and the gate's ruling is not fed back.
- [ ] Before/after live measurement on RIG0 against llm.almckay.io.
- [ ] Review, CURRENT.md, handoff.

## Validation and progress

2026-10-13, branch `claude/agent-behaviour-fixes-f1h06f` from main `0d9bb5a`. `make test-config`: 788 passed (one existing pydantic_graph deprecation warning). New checks were confirmed to fail on the old agent code: authoring tool hiding after a workspace failure and after a spent budget (3), assessment witness grounding and prompt line (5, including the composition over-claim test). Scripted authoring evals 12/12. Scripted checks only so far; no live claim.

Before (RIG0, worktree at main `0d9bb5a`, `make test-config` 781 there; vLLM Qwen3.6-35B-A3B-NVFP4 at llm.almckay.io, the PLAN-0031 provider configuration: cap 16384, server-default thinking, timeout 180 s, temperature 0, no retries; fixture E2E with one live stage, others scripted). A first pass with relative `--evidence` paths raised in `LocalArtifacts` before any model call and is kept aside, not counted.

| Stage (live) | Attempts | Outcome | Notes |
| --- | --- | --- | --- |
| Planning | 4 | 0/4 plans | Each: two reads, then one response spending the whole 16384 cap on reasoning (≈16.7k reasoning tokens, ≈120 s), no answer |
| Authoring | 3 | 0 patches, 1 blocked | auth-1/2: two reads then the cap, before any write. auth-3: four write/run pairs, runs 1-3 `workspace_failure` (reviewed workspace refusal), run 4 `not_run` (budget spent) after an identical rewrite, then `blocked`/`sandbox` with an accurate reason (11 requests, 7025 output tokens) |
| Assessment | 3 | 3/3 proposed `completed`/`reproduced`/`verified`, 0/3 admitted | Gate permitted `completed`/`inconclusive`/`not_verified` (`witness_missing` both revisions). Every application observation cited only JUnit items; one run called the JUnit content "the witness". 8 requests, ≈3.4k output tokens, ≈31 s each |
| Planning evals (6 cases × 2, eval budget 5 requests/4 tools/48k tokens) | 12 | 6/12 completed, all passing every assertion | The other 6 hit the 16384 cap after two reads; injection and unsupported-observation 0/2 each, unguarded and guarded 1/2, no-baseline and implementation-absent 2/2 |

14 of 20 live planning and authoring attempts ended in a single all-reasoning response at the provider cap right after reading source: the provider cap, not the agent budget, stopped them. Private evidence: `.runs/behaviour-20261013/before/` in `/home/al/git/corsair-behaviour` on RIG0.

Behaviour change in composition: a live assessor that over-claims twice without a witness now fails the assessment stage on its output retries instead of reaching `admit()`; the rejected proposals stay in the attempt messages and the gate verdict is still computed.

## Decisions and next action

- Reasoning budgets are per-stage provider configuration selected by the operator, not set inside agent factories, because `thinking_token_budget` is a vLLM request field.
- Only `workspace_failure` hides authoring tools deterministically; `report_failure` stays skill guidance because a missing report could come from test code.
- Next: live before/after measurement, then review and handoff.
