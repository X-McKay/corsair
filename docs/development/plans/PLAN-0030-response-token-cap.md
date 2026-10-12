---
id: PLAN-0030
kind: plan
title: Per-caller 16384 response-token cap for the local model
status: complete
updated: 2026-10-12
related: [ISSUE-0007, SPEC-0016, SPEC-0024, HANDOFF-0048]
---

# Per-caller 16384 response-token cap for the local model

## Objective and dependencies

On 2026-10-12 live runs lost attempts to the per-request response cap tracked by ISSUE-0007: 3 of 15 evidence-assessment attempts (PLAN-0029, PR #25) stopped with the 8192-token cap exceeded before any answer was produced, and 2 of 12 test-planning attempts (PLAN-0025, PR #26) failed on the cap before a 2048-token thinking budget was added. The model is served locally at llm.almckay.io, so a higher cap costs latency, not money. The user asked whether raising the caps is worthwhile.

The cap is a single `LocalModelConfig.response_token_limit` field (`src/corsair/agents/issue_analysis/provider.py` on main, moved to `src/corsair/agents/provider.py` by PR #26 and PR #28). It is not global: every caller (eval CLI, provider-config JSON, agent smoke harness) selects its own value from an allowed set whose maximum was 8192. Thinking budgets (`thinking_token_budget`, at most 2048) are a separate field and are unchanged.

## Steps

- [x] Allow 16384 in the typed set and the issue-analysis live CLI choices; keep the 2048 default, the thinking-budget bound and every other limit. Request-body test covers 16384 with a 2048 thinking budget; 32768 stays refused.
- [x] Probe the served model length and decode throughput, so the 120 s client timeout ceiling is checked against a full 16384-token response. Result below: 120 s cannot hold it, so the client timeout ceiling rises to 240 s (default stays 60 s).
- [x] Rerun the evidence-assessment cases that hit the cap (b and c, three repeats each) at 16384 and a 180 s client timeout, every other setting unchanged.
- [x] Rerun the issue-identification development corpus (16 attempts) at 16384 and 180 s against its 8192 baseline.
- [x] Record results here and in ISSUE-0007; per-agent selections recorded below.

## Per-agent selection

| Agent | Cap | Reason |
| --- | --- | --- |
| Evidence assessment (PR #25) | 16384 with a 180 s client timeout | Removes most cap failures (below); its verified-fix defect remains |
| Test planning (PR #26) | unchanged: 8192 with 2048 thinking budget | The thinking budget fixed its cap failures; its remaining failures were request/tool allowances |
| Test authoring (PR #28) | 4096 when it first runs live | Emits whole test files; 4096 was already allowed |
| Environment (PR #27) | none of its own | Takes limits from the caller |
| Issue identification | 8192 is enough | Largest response 1283 tokens; 16/16 at both caps |

Each agent records its selection with its own config/prompt version on its own branch; this plan only widens the allowed set.

## Validation and progress

- `make test-config`: 394 passed (390 on main plus the 16384 request-body case, the 241 s timeout refusal and two live-CLI cases). Review found the issue-analysis live CLI offered 16384 but always built a 60 s client; it now takes `--timeout-seconds` (default 60, bounded by `LocalModelConfig`). The first CI run failed the work-record check on a mistyped plan status (`in-progress`); corrected to `in_progress`, and PLAN-0025/PLAN-0029 dropped from `related` because they exist only on their PR branches.

Server probe on RIG0, one request, no retry (evidence `.runs/token-cap-20261012/probe-*` on RIG0, private): `max_model_len` 131072; temperature 0, `max_tokens` 16384, a 77-token long-proof prompt returned HTTP 200, `finish_reason` `length`, 16384 completion tokens all reported as reasoning with empty content, in 125.94 s wall clock (about 130 tokens/s including prefill and network). Server load at the time is unknown. A full 8192 response therefore takes about 63 s and fits the 120 s client timeout used in earlier smokes; a full 16384 response does not.

### Reruns at 16384 / 180 s (2026-10-12, RIG0, no retries)

Private evidence: `.runs/token-cap-20261012/` on RIG0 (`SUMMARY.md`, per-attempt messages and source hashes). Evidence assessment ran PR #25 head `9501174` with this branch (`bc22332`) merged locally, prompt `evidence-assessment-v2`, request limit 12, tool calls 10, one output retry, the harness's 300 s task deadline, concurrency one, and the exact frozen inputs (b from `215151Z`, c from `213319Z`).

| Attempt | Outcome | Gate | Requests / tools | Output tokens (largest response) | Elapsed |
| --- | --- | --- | --- | --- | --- |
| b-1 | blocked/reproduced/not_verified | admitted | 7 / 6 | 9300 (7743) | 75.8 s |
| b-2 | failed: 16384 cap, all reasoning | n/a | 7 / 6 | 17896 (16384) | 131.4 s |
| b-3 | blocked/reproduced/not_verified | admitted | 8 / 7 | 4796 (2910) | 43.5 s |
| c-1 | completed/reproduced/verified | rejected: verified exceeds not_verified | 6 / 5 | 6750 (5843) | 54.1 s |
| c-2 | completed/reproduced/verified | rejected | 6 / 5 | 11065 (10322) | 84.7 s |
| c-3 | completed/reproduced/verified | rejected | 6 / 5 | 10410 (9597) | 81.6 s |

Before and after for the same cases: cap failures went from 3 of 7 attempts at 8192 (b 1/3, c 2/4) to 1 of 6 at 16384; there were no client timeouts or deadline hits. Two of the five completions needed more than 8192 tokens in their final response. Admitted results are unchanged at 2 (b 2/3 at 8192, b 2/3 at 16384; c 0 at both). Every c completion, at either cap, proposes a verified fix that the gate rejects, so the higher cap converts c's cap failures into rejected proposals; the PLAN-0029 semantic defect is untouched. b-2 spent its budget alternating between the application and sandbox readings, which a larger cap is not expected to fix.

Issue identification (this branch, defaults otherwise: 8 cases x 2, request limit 4, tool limit 3, total 32000, 180 s task deadline): 16/16 passed every check, as at 8192/120 s. Requests 30 vs 31, tokens in/out 43005/11043 vs 44730/10163, summed task latency 92.7 s vs 92.1 s; the largest single response was 1283 tokens. The cap does not matter for this agent. Its 180 s task deadline now equals the client timeout used in this run, so one slow request would hit both at once; not exercised and not changed.

## Decisions and next action

Raising the cap alone would turn every full-cap response into a transport timeout, so the `LocalModelConfig.timeout_seconds` ceiling rises from 120 to 240 s and the reruns use 180 s. This is a second changed variable and is reported as such. The probe also shows the model can spend the whole budget reasoning without answering, so a larger cap is not expected to help every case; a thinking budget remains the separate control. The reruns confirm this: 16384 removes most cap failures at a latency cost of up to about two minutes per response, but does not change what the model concludes. Next: evidence assessment's verified-fix defect and b-2's indecision belong to its own prompt/evals work on PR #25; this plan stops here.


PR #26 and PR #28 replace the main-branch provider module with a re-export shim, so whichever merges second resolves one conflict: keep the shim and apply the one-line `Literal` change to `src/corsair/agents/provider.py`. PR #25 and PR #27 merge cleanly.
