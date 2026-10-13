---
id: PLAN-0037
kind: plan
title: Assessment and chain evaluation sets with durable chain mode
status: in_progress
updated: 2026-10-13
related: [SPEC-0035, SPEC-0030, SPEC-0031, PLAN-0029, PLAN-0031, IDEA-0004]
---

# Assessment and chain evaluation sets with durable chain mode

## Objective and dependencies

Implement [SPEC-0035](../specs/SPEC-0035-assessment-evals-and-durable-chain.md) from main `0d9bb5a`. Independent of the kind cluster (reserved by PLAN-0034 and PLAN-0033). Rebase expected after PRs #35 (witness capture, touches `composition/`), #34 (assessment output function and prompts) and #33 (fixture runner) land.

## Steps

- [ ] Assessment dataset builder, cases, evaluators, scripted run and guards.
- [ ] Chain dataset over the reviewed pair variants, direct mode.
- [x] `run_chain` routing split; `run_direct` unchanged for callers.
- [x] Durable chain: child stage workflows, revision activity, worker-side runner resolution, native Temporal tests and replay.
- [ ] Chain dataset in durable mode; direct/durable parity.
- [ ] Live baselines on the local provider (assessment development split; chain with live stages).
- [ ] Review, records, handoff.

## Validation and progress

Durable chain (branch `durable-chain`), scripted stage models and reviewed host runners only; no provider, OpenShell or live qualification:

- `make test-config`: 785 passed, 1 failed: SPEC-0035 listed SPEC-0033 (not yet on main) as related; removed from `related` until PR #35 lands.
- Native service: pinned Temporal CLI 1.9.1 (binary sha256 verified against `deploy/temporal/runtime-lock.yaml`) on loopback; `pytest tests/temporal --temporal-address … --temporal-evidence-dir …`: 45 passed (12 new chain checks, 33 existing), none skipped.
- Direct and durable runs agree on stop stage, reason, gate result, assessment admission, stage sequence, per-stage requests and tool calls for the true pair, an identification abstention, a raising candidate runner (one activity attempt, recorded, chain stops at execution) and an over-budget identification. A timed-out stage stops both modes at the same stage with kind `TimeoutError`; the reason text differs (durable `Timed out` from the child's execution timeout, direct an empty `asyncio` timeout message) and durable usage is `None` (unobserved). Parent admission refusals fail the workflow before any child or activity.
- 17 retained histories (parents and children) replayed with the native `Replayer`.

## Decisions and next action

Durable chain decisions (`src/corsair/workflows/chain.py`, `chain_runtime.py`):

- `run_chain` stays in `composition/direct.py` beside `run_direct` so the execution block keeps its lines for the PR #35 rebase; its ports are a stage invoker returning a `StageAttempt` and a revision executor mirroring `TestRunner.run`. Failures from another process are `RecordedFailure(kind, message)`, so reasons name the native type in both modes.
- Worker configuration: agents bind durability when built and workflow classes must be module-level, so a worker process calls `configure_chain(models, runners, activity_config=..., ceiling=...)` once (agents built with native `TemporalDurability` over keyed models; a refusing default model), then `chain_worker(...)`, which registers each agent with native `AgentPlugin`. Workflows read the configuration through the sandbox pass-through. One configuration per process; `run_durable(case, models, runners, budget, *, client, ...)` does both for an in-process worker with the stage names as model keys and `budget` as ceiling.
- Authoring deps cross natively as `AuthoringPayload` (inputs, budget, the runner's purpose via the workflow-side `WorkerRunner` stand-in); `AuthoringRunContext` (native `run_context_type`) adds the run's messages, which `run_tests` and the patch rebuild read, and resolves the development runner from the worker's `Runners`. This deviates from the spec's wording (inputs and budget in the run context) only to avoid carrying the inputs twice per activity.
- Output retries are fixed when agents are built, so admission requires the request's `output_retries` to equal the ceiling's. Native bytes cross as base64 (`RevisionRequest`, `RevisionRun`, `ExecutionRecord`). Messages round-trip with tool-return contents as JSON values.

Next: chain dataset in durable mode through `run_durable`; rebase after PR #35.

Work proceeds in parallel: the evaluation sets and the durable chain touch separate files except `composition/direct.py`, which only the durable work changes, keeping `run_direct`'s signature.

