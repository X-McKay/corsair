---
id: HANDOFF-0096
kind: handoff
title: The environment stage in durable mode
status: recorded
updated: 2026-10-13
related: [SPEC-0068, PLAN-0075, PLAN-0074, HANDOFF-0094]
---

# The environment stage in durable mode

## Verified state

Draft PR #103, branch `claude/chain-runtime-handoff-dtb1ut` from main `8858560` with later main merged. Delivered under the durable-mode section of [SPEC-0068](../specs/SPEC-0068-chain-environment-stage.md#durable-mode-plan-0075):

- `prepare_environment(inputs, model, preparation, budget)` in `composition/direct.py` is the whole stage (prepare, agent run, release) and is shared by `run_direct` and the activity.
- Activity `corsair.chain.prepare_environment` (`run_environment` in `workflows/chain_runtime.py`) returns an `EnvironmentRecord`. The workflow schedules it once, with no retry, and a start-to-close timeout of the stage `timeout_seconds` plus `PREPARATION_MARGIN` (5 minutes). An activity failure is a recorded failure with unconfirmed cleanup.
- `StageKeys.environment` is optional and admitted like the other keys. `ChainRuntime` gains `models` and `preparation`; `configure_chain(preparation=)` and `run_durable(preparation=)` pass it through, and `within` now also bounds the environment stage budget and `setup_commands`.
- A missing environment key stops in the workflow with `PreparationMissing`. A worker without a preparation port or that model raises a non-retryable `PreparationMissing`. Neither falls back to the declaration.
- `ChainResult.environment`, `AttemptRecord.cleanup` and the environment results in `StageOutput`.

## Validation and blockers

See [PLAN-0075](../plans/PLAN-0075-durable-environment-stage.md#validation-and-progress). The activity-failure path (worker loss or timeout giving unconfirmed cleanup) is not exercised natively. The environment record's messages are bounded only by the stage's token and request caps, not by an encoded-size check. No real preparation adapter exists yet.

## Decisions and next steps

- The whole stage is one activity, because the setup ledger and the live sandbox cannot persist across PydanticAI's per-call activities. It has one attempt because setup commands have side effects.
- Next: the OpenShell `Preparation` adapter, then a chain eval case with setup source and a recorded preparation double.

## Continuation prompt

Continue from PR #103: read SPEC-0068 and this handoff, verify the branch against main, then specify the OpenShell `Preparation` adapter (prepare and release one sandbox of a prepared image, confirm cleanup against immutable identity) before code.
