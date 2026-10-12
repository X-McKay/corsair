---
id: PLAN-0029
kind: plan
title: Evidence assessment agent
status: in_progress
updated: 2026-10-12
related: [SPEC-0030, SPEC-0027, IDEA-0004]
---

# Evidence assessment agent

## Objective and dependencies

Implement [SPEC-0030](../specs/SPEC-0030-evidence-assessment-agent.md), step 4 of the IDEA-0004 order, over the [SPEC-0027](../specs/SPEC-0027-disposition-gates.md) gates. Independent of the planner, authoring and environment threads; touches only `src/corsair/agents/evidence_assessment/`, its test and records.

## Steps

- [x] Contracts, `read_evidence` toolset, `assess-evidence` skill and factory with gate-backed output function.
- [x] Deterministic `FunctionModel` tests.
- [ ] Native Pydantic Evals cases (SPEC-0018 runs plus the IDEA-0004 negatives), development and held-out splits.
- [ ] Add `read_source` once `agents/source/` is on main, if evaluation shows it is needed.
- [x] First bounded live smoke on llm.almckay.io (prompt v1; below).
- [ ] Rerun the smoke with prompt v2, then Evals-based live repeats; durable stage.

## Validation and progress

2026-10-12, on branch `claude/evidence-assessment-checks-e694q5` (PR #25), after the gates: `uv run --locked python -m pytest tests/agents/test_evidence_assessment.py -q` 17 passed. Full `make test-config` result is in HANDOFF-0047.

Live smoke, prompt `evidence-assessment-v1` at `acf07a8` on RIG0, vLLM at llm.almckay.io serving Qwen3.6-35B-A3B-NVFP4 (every response reported that name), temperature 0, response cap 8192 (the configured maximum), `UsageLimits(request_limit=12, tool_calls_limit=10)`, one output retry, concurrency one. Inputs built from the rebased retained runs (benchmark-admission, vulnerable run 1 as baseline, fixed run 1 as candidate). Cases: (a) true pair, (b) a synthetic test-phase policy denial touching the witness path on the candidate, (c) the candidate witness changed to `PermissionError`. Two repeats each:

| Attempt | Proposed | Admitted | Gate | Requests / tools | Tokens in/out | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| a1 | completed/reproduced/verified | yes | same | 6 / 5 | 24823/2987 | 37.1s |
| a2 | completed/reproduced/verified | yes | same | 6 / 5 | 23754/1605 | 20.2s |
| b1 | completed/reproduced/verified | no | blocked/reproduced/not_verified | 7 / 6 | 30115/3554 | 42.2s |
| b2 | completed/reproduced/verified | no (one output retry) | blocked/reproduced/not_verified | 8 / 6 | 36454/10655 | 115.6s |
| c1 | none: `UnexpectedModelBehavior`, model token limit (8192) exceeded after five reads | n/a | completed/reproduced/not_verified | 6 / 5 | 25530/9216 | 99.1s |
| c2 | completed/reproduced/not_verified | yes | same | 6 / 5 | 24550/8512 | 93.6s |

Every attempt read every item; no tool call was refused. In (b) the model cited the denial but read it as the sandbox blocking the traversal and proposed a verified fix; the gate rejected it both times. In (c2) the model noticed the JUnit/witness discrepancy and weakened its own proposal. Both (a) attempts added a wrong limitation comparing the candidate source digest with `frozen_patch_sha256`. c1 is a provider response-cap failure, the same 8192-token cap ISSUE-0007 tracks; it is kept in the denominator. Six attempts are a smoke, not qualification. Receipts are retained privately under `.runs/evidence-assessment-live-20261012T213319Z/` on RIG0.

Prompt `evidence-assessment-v2` answers the two semantic errors: the skill now says `frozen_patch_sha256` identifies only the test patch, and that a sandbox denial or resource limit is never evidence of application safety. Its effect is unmeasured until the smoke is rerun.

## Decisions and next action

Rejected proposals are kept, not retried. `read_source` deferred to avoid importing paths the planner thread is moving. Next: rerun the smoke with prompt v2, then the Evals dataset. The response cap stays at the configured 8192 maximum; raising it belongs to ISSUE-0007. Stop condition: no connection to other stages before evals and a live baseline exist.
