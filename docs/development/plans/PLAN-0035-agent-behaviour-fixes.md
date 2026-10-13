---
id: PLAN-0035
kind: plan
title: Planner and author budget discipline, author blocked status, assessor witness grounding
status: complete
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
- [x] Before/after live measurement on RIG0 against llm.almckay.io (below).
- [x] Fix the two regressions the after runs found: assessment prompt count line (v4, `a2393e2`); assessment thinking budget 2048 in the stage profile (`31f503f`, live rerun pending).
- [x] Authoring skill keeps the security test's planned direction (`test-authoring-v3`, `7c4f855`), after PLAN-0034 live-1's inverted security test; not measurable here because the reviewed workspace refuses live-authored tests.
- [x] Review, CURRENT.md, HANDOFF-0053.

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

After (RIG0 worktree `/home/al/git/corsair-pr34` at `8d45105`, `make test-config` 788; same base provider configuration plus `--stage-profiles evals/fixture_e2e/stage-profiles.json`; planner evals with the base config at cap 8192 and thinking budget 2048, and separately with the unchanged base config to isolate the prompt). Every attempt counted, none retried:

| Stage (live) | Before | After | Notes |
| --- | --- | --- | --- |
| Planning (E2E) | 0/4 plans, 4/4 cap | 4/4 ready plans, 0 cap | 3-5 requests, 31-60 s, 3.5k-7.3k output tokens, 1-3 thinking-budget stops per run. All four then stop at the scripted author, whose reviewed test ids differ from the live plan's (harness limit, as PLAN-0031 ip-1) |
| Authoring (E2E) | 0 patches; 2/3 cap, 1/3 blocked after 4 write/run cycles | 2/3 blocked/`sandbox` after one write and one refused run (5 requests, 13-20 s), 1/3 no output | The failed attempt reasoned correctly to `blocked`, then called an invented tool `result` with stringified JSON; zero tool retries made it fatal. Tool definitions are not in the receipt, so that the write/run tools were hidden at that point is inferred from the code |
| Assessment v3 (E2E) | 3/3 over-claimed `reproduced`/`verified`, 0 admitted | 0/3 output | All three read the prompt's new "Witness items: baseline 0, candidate 0" line as an item id, requested a nonexistent item and ended under zero tool retries. The line was removed in `a2393e2` (v4) |
| Assessment v4 (E2E, at `7c4f855`) | as above | 1/3 admitted `completed`/`inconclusive`/`not_verified` (equal to the gate), 2/3 response cap | The admitted run cited JUnit explicitly as claims and named the missing witness. The two cap runs drafted the same correct answer repeatedly in reasoning (16384 tokens, ≈186 s) without emitting it. Every v4 run read only the seven listed items; the witness-rule retry never fired. Another thread's planner eval shared the server, so latency may be inflated |
| Planner evals, budget profile | 6/12 completed (6 cap) | 12/12 completed, 0 cap, 10/12 pass every assertion | `unsupported_observation` 0/2: returns ready for the SSRF case (status, call, input, witness and grounding checks fail); every other case 2/2 |
| Planner evals, prompt only (16384, no budget) | as above | 10/12 completed (2 cap), 8/12 pass every assertion | The prompt alone cuts cap hits 6 to 2; the budget takes them to 0. `path_traversal_guarded` failed grounding once; `unsupported_observation`'s completed attempt returned ready |
| Full chain, all stages live (reviewed workspace) | not run | 0/2 reached assessment | chain-1: ready plan after 9 requests and 155 s (the same two files re-read 7 times, 5 thinking-budget stops, one `safe_behavior` pattern correction); authoring then correctly returned blocked/`sandbox`. chain-2: planning hit the 8192 cap after its thinking budget closed, reasoning on in visible text (≈27k characters); the corrected plan's control id names `test_existing.py` while its path is `test_documents.py`, which the planner accepts and authoring input refuses |

Assessment v4 with the 2048 thinking budget (`31f503f`, asm-7..9, server shared with another thread's eval): 2/3 admitted `completed`/`inconclusive`/`not_verified` equal to the gate, both treating JUnit as a claim and naming the missing witness; 1/3 exceeded the 10 tool-call limit re-reading already-read items after thinking-budget stops; 0 cap hits; no invented ids; the witness-rule retry never fired. Across versions: v3 0/3 output, v4 1/3 admitted (2/3 cap), v4 with budget 2/3 admitted (1/3 tool limit).

Codex review of `12cd57a` (two findings, both fixed in the next commit): run_tests calls batched in one response would each run, so a workspace failure in the first could be blindly repeated before `prepare` hides the tool; now only the first run_tests call in a response runs and later ones return `not_run` (they would repeat the same files). And the authoring skill forced `blocked`/`sandbox` for every workspace or report failure; it now says `sandbox` only for a sandbox refusal, otherwise `unknown`, quoting the observed reason (`test-authoring-v4`). The batched-run test was confirmed to fail on the previous tools. `make test-config` 827, scripted authoring evals 12/12.

Merging main brought witness capture (SPEC-0033, PR #35): the scripted assessor in `evals/fixture_e2e/case.py` now cites a revision's witness item when one is listed, so a witnessed reproduced/verified proposal satisfies this plan's grounding rule.

Private evidence: `.runs/behaviour-20261013/after*/` (with `SUMMARY.md`) in `/home/al/git/corsair-pr34` on RIG0.

Behaviour change in composition: a live assessor that over-claims twice without a witness now fails the assessment stage on its output retries instead of reaching `admit()`; the rejected proposals stay in the attempt messages and the gate verdict is still computed.

## Decisions and next action

- Reasoning budgets are per-stage provider configuration selected by the operator, not set inside agent factories, because `thinking_token_budget` is a vLLM request field.
- Only `workspace_failure` hides authoring tools deterministically; `report_failure` stays skill guidance because a missing report could come from test code.
- The thinking budget has side effects seen live: repeated re-reads of already-read files after a budget stop, and reasoning continuing in visible text until the response cap. The re-read guidance did not prevent the former in chain-1.
- Not changed here, for their owners: the planner accepts a test id whose file differs from its test path (authoring input refuses it; the node-id shape stays an authoring check per PLAN-0025, so a planner check needs a decision); `unsupported_observation` returns ready (planner live qualification); an invented output-tool name in prompted output mode ends authoring under zero tool retries (decide whether output-shaped hallucinations deserve one retry).
- Next: steer the assessor (and planner) away from re-reading after a thinking-budget stop, or give headroom; inverted-polarity check on the sandbox runner (PR #33) once both land; freeze held-out cases before more prompt tuning.
