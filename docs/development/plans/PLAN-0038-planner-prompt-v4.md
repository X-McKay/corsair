---
id: PLAN-0038
kind: plan
title: Test planner prompt v4 and read guard
status: in_progress
updated: 2026-10-13
related: [PLAN-0036, PLAN-0035, PLAN-0025, SPEC-0022, SPEC-0023]
---

# Test planner prompt v4 and read guard

## Objective and dependencies

Respond to the PLAN-0036 findings so the SPEC-0022 planner can be qualified: re-reads that exhaust the tool-call budget, reads of the approved (to-be-created) test path, fixtures in `tmp_path.parent`, ready plans for concerns no listed facility observes, `safe_behavior` contradicting `required_behavior`, and witnesses claiming events the facility never records. This is the first step toward running every example and benchmark end to end; the planner stays disconnected from other stages until it is qualified. Inference only (local model at llm.almckay.io from RIG0); no kind cluster.

## Steps

- [x] Prompt `test-planning-v4` (skill and rendered prompt): approved test paths are listed separately as files to create and are not readable; read-once wording with a stop condition; a step deciding whether a listed facility observes the sensitive operation itself (a test outcome, exception or return value never shows that an operation did not happen), with unsupported as a correct result and no substitution of an observable property; a scratch example that keeps the outside file inside the scratch location; `safe_behavior` must identify the behavior `required_behavior` states; witnesses only for events the facility actually records for that call (in-process audit hooks do not see what a launched shell does); no forecast of test outcomes on current source; source references cover the whole implementation. v3's "decide each field instead of weighing alternatives" is removed.
- [x] Structural read guard (`test-planning-config-v2`): native tool preparation (`FunctionToolset.prepared`) withdraws `read_source` once every inventory line has been returned in the current run, so a re-read of a fully read inventory cannot be requested and the output tool is the only call left. Scoped to the planner; the shared window reader and other stages are unchanged.
- [x] Offline tests: the reader is offered until the inventory is covered and withdrawn after; prompt lists approved paths as unreadable.
- [ ] Fresh held-out cases (second held-out set) written and independently reviewed by agents other than the prompt author, then frozen by manifest before any provider sees them.
- [x] Live development × v4 (2 repeats): 12/12; review found a root/fixture mismatch, fixed in v5.
- [x] Live development × v5 (2 repeats): 11/12; over-abstention on absence witnesses, fixed in v6.
- [x] Live development × v6 (2 repeats): 12/12; final candidate.
- [ ] Live on RIG0, sequential, each once, no retries, on v6: the exposed first held-out set × the final candidate (3 repeats, comparison only); the fresh held-out set × the final candidate (3 repeats, qualification decision). The held-out sets run only on the final candidate.
- [ ] Review of every actual plan and error; records, `CURRENT.md`, handoff.

## Pre-registered criteria

Provider profile as PLAN-0036: saved RIG0 provider configuration, `response_token_limit` 8192, `thinking_token_budget` 2048, timeout 180 s. Budgets unchanged (5 requests, 4 tool calls, 48000 tokens, one output correction, 240 s). Evaluator checks unchanged, so the development and first held-out numbers compare directly with PLAN-0036.

The pre-registered criteria apply to the final candidate (the last prompt version after development review). The first held-out set is exposed: the new prompt's audit-hook and abstention wording draws on PLAN-0036's review of it, so its result is comparison only. Qualification is decided only on the fresh held-out set: the candidate is qualified for that scope only if every attempt passes every deterministic check with zero unknown tools and provider usage on every attempt, and independent review of the actual ready plans finds no defect that would make the authored test measure the wrong property (including `safe_behavior` contradicting `required_behavior` and witnesses for events the facility does not record). Anything less is reported as not qualified with failures attributed.

## Validation and progress

Base: main `334aa03`. `tests/agents/test_test_planning.py`: 33 passed (32 existing, 1 new). `make test-config`: 854 passed (853 on main plus 1).

### Live results (2026-10-13)

Worktree `/home/al/git/corsair-pr38` on RIG0, provider as pre-registered (vLLM `Qwen3.6-35B-A3B-NVFP4`, 8192 cap, 2048 thinking, 180 s). Evidence `.runs/planner-v4-20261013/` there (git-ignored). Each run once, no retries.

| Run | Source | Prompt | Passed every check | Errors | Wall | Requests / input / output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| development, 2 repeats | `5ed852b` | v4 | 12/12 | 0 | 463 s | 34 / 141,245 / 30,413 |
| development, 2 repeats | `6aa77ca` | v5 | 11/12 | 0 | 331 s | 34 / 144,254 / 27,667 |
| development, 2 repeats | `29ca9db` | v6 | 12/12 | 0 | 266 s | 34 / 149,778 / 30,766 |

PLAN-0036's v3 development run was 4/12. Under v4 every ready plan read exactly the target and the baseline test once (two calls), no attempt re-read a file or read an unlisted path, no response reached the length cap, both unobservable-network attempts abstained, and every ready plan kept fixtures inside `tmp_path`; two attempts needed one output correction. Review of the actual plans found one defect the checks miss: 2/8 ready plans passed `tmp_path` itself as the root while creating `tmp_path/outside.txt`, so `'../outside.txt'` names a file in `tmp_path`'s parent rather than the fixture and the witness watches the wrong path (the test would pass on vulnerable code); one further plan used a different root in control and security. `safe_behavior` matched `required_behavior` in all eight (`no_outside_open` for absence, `ValueError` where a rejection is required). Prompt v5 (`6aa77ca`) adds to the scratch step: never pass the scratch location itself as the root, resolve the adversarial input from the root and check that it names the created fixture, use that path in the witness, and use the same root in both tests.

Under v5 every ready plan resolved `'../outside.txt'` from `tmp_path/allowed` to the created fixture (5/5), with no re-reads, no length cap and two single output corrections. One guarded-traversal attempt abstained, arguing that the absence of an `open` event cannot be observed: v5's new sentence that outcomes never show an operation did not happen overreached. One plan still used different roots in control and security, and one limitation forecast the security outcome on current source. Prompt v6 (`29ca9db`) says that a facility recording every occurrence of an operation observes both its occurrence and its absence during the call, and forbids outcome forecasts in limitations.

Under v6 both guarded attempts planned absence-of-`open` witnesses, every ready plan (6/6) resolved the adversarial path to the created fixture, no limitation forecast a test outcome, and no witness claimed an unrecorded event; two attempts needed one output correction. Remaining review notes, none of which changes what the test measures: one plan used `tmp_path` as the control root and `tmp_path/allowed` as the security root; one wrote `required_behavior` as the bare token `no_outside_open`; one wrote "must reject" alongside the absence requirement. v6 (`29ca9db`) is the final candidate for the held-out runs.

## Decisions and next action

- Re-reads are handled structurally where that is exact (whole inventory returned) and by prompt otherwise; a per-window refusal would end the run under the shared zero tool-retry policy, and a short-circuit result would still spend the tool budget.
- The evaluator is not extended for `safe_behavior` consistency or witness truth; both stay review findings, so results remain comparable with PLAN-0036.

The fresh held-out set is frozen at `82d2c76` (SHA256 `7daba5a5…484e`): six cases (four ready, two unsupported) written by one agent and reviewed by another, neither the prompt author; the reviewer fixed marker fairness (one adversarial-marker false positive, missing valid spellings in four cases, one over-broad forbidden marker) and empirically confirmed every witness event. Recorded caveats in generic terms: one ready case is a near-transfer of a first-set family; both unsupported cases reuse development-set rules, and one admits a weak alternative ready plan the oracle would mark wrong; markers remain substring heuristics.

Next: both held-out sets once on v6 (fresh set first).
