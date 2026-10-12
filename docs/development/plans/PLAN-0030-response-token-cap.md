---
id: PLAN-0030
kind: plan
title: Per-caller 16384 response-token cap for the local model
status: in_progress
updated: 2026-10-12
related: [ISSUE-0007, SPEC-0016, SPEC-0024]
---

# Per-caller 16384 response-token cap for the local model

## Objective and dependencies

On 2026-10-12 live runs lost attempts to the per-request response cap tracked by ISSUE-0007: 3 of 15 evidence-assessment attempts (PLAN-0029, PR #25) stopped with the 8192-token cap exceeded before any answer was produced, and 2 of 12 test-planning attempts (PLAN-0025, PR #26) failed on the cap before a 2048-token thinking budget was added. The model is served locally at llm.almckay.io, so a higher cap costs latency, not money. The user asked whether raising the caps is worthwhile.

The cap is a single `LocalModelConfig.response_token_limit` field (`src/corsair/agents/issue_analysis/provider.py` on main, moved to `src/corsair/agents/provider.py` by PR #26 and PR #28). It is not global: every caller (eval CLI, provider-config JSON, agent smoke harness) selects its own value from an allowed set whose maximum was 8192. Thinking budgets (`thinking_token_budget`, at most 2048) are a separate field and are unchanged.

## Steps

- [x] Allow 16384 in the typed set and the issue-analysis live CLI choices; keep the 2048 default, the thinking-budget bound and every other limit. Request-body test covers 16384 with a 2048 thinking budget; 32768 stays refused.
- [x] Probe the served model length and decode throughput, so the 120 s client timeout ceiling is checked against a full 16384-token response. Result below: 120 s cannot hold it, so the client timeout ceiling rises to 240 s (default stays 60 s).
- [ ] Rerun the evidence-assessment cases that hit the cap (b and c, three repeats each) at 16384 with every other setting unchanged.
- [ ] Rerun the issue-identification development corpus (16 attempts) at 16384 against its 8192 baseline.
- [ ] Record results here and in ISSUE-0007; per-agent selections recorded below.

## Per-agent selection

| Agent | Cap | Reason |
| --- | --- | --- |
| Evidence assessment (PR #25) | 16384, subject to the rerun below | All three cap failures exhausted 8192 before answering |
| Test planning (PR #26) | unchanged: 8192 with 2048 thinking budget | The thinking budget fixed its cap failures; its remaining failures were request/tool allowances |
| Test authoring (PR #28) | 4096 when it first runs live | Emits whole test files; 4096 was already allowed |
| Environment (PR #27) | none of its own | Takes limits from the caller |
| Issue identification | measured below | Baseline 16/16 at 8192 |

Each agent records its selection with its own config/prompt version on its own branch; this plan only widens the allowed set.

## Validation and progress

- `make test-config`: 391 passed (390 on main plus the new 16384 request-body case). The first CI run failed the work-record check on a mistyped plan status (`in-progress`); corrected to `in_progress`, and PLAN-0025/PLAN-0029 dropped from `related` because they exist only on their PR branches.

Server probe on RIG0, one request, no retry (evidence `.runs/token-cap-20261012/probe-*` on RIG0, private): `max_model_len` 131072; temperature 0, `max_tokens` 16384, a 77-token long-proof prompt returned HTTP 200, `finish_reason` `length`, 16384 completion tokens all reported as reasoning with empty content, in 125.94 s wall clock (about 130 tokens/s including prefill and network). Server load at the time is unknown. A full 8192 response therefore takes about 63 s and fits the 120 s client timeout used in earlier smokes; a full 16384 response does not.

## Decisions and next action

Raising the cap alone would turn every full-cap response into a transport timeout, so the `LocalModelConfig.timeout_seconds` ceiling rises from 120 to 240 s and the reruns use 180 s. This is a second changed variable and is reported as such. The probe also shows the model can spend the whole budget reasoning without answering, so a larger cap is not expected to help every case; a thinking budget remains the separate control.


PR #26 and PR #28 replace the main-branch provider module with a re-export shim, so whichever merges second resolves one conflict: keep the shim and apply the one-line `Literal` change to `src/corsair/agents/provider.py`. PR #25 and PR #27 merge cleanly.
