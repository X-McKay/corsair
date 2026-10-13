---
id: PLAN-0075
kind: plan
title: The environment stage in durable mode
status: in_progress
updated: 2026-10-13
related: [SPEC-0068, PLAN-0074, SPEC-0060, PLAN-0065]
---

# The environment stage in durable mode

## Objective and dependencies

Implement the durable mode of [SPEC-0068](../specs/SPEC-0068-chain-environment-stage.md#durable-mode-plan-0075) from main `8858560` (#100 merged): the durable chain runs the environment stage as one activity, `corsair.chain.prepare_environment`, with the same routing, result and limitations as direct mode. Depends only on merged work. No kind cluster, model server or real sandbox adapter is needed; the OpenShell `Preparation` adapter is the next slice. The environment agent's prompt, skill and tools are not changed.

## Steps

- [x] SPEC-0068 durable-mode section: one activity, no retry, why not per-call activities.
- [ ] One module-level `prepare_environment` shared by `run_direct` and the activity.
- [ ] `StageKeys.environment` (optional, admitted like the others), `ChainRuntime.preparation` and the worker's models, `configure_chain(..., preparation=)`, `run_durable(..., preparation=)`, the stage budget in the ceiling check.
- [ ] The activity and its typed record; the workflow schedules it once with the stage timeout plus a margin, and a failed activity is a recorded failure with unconfirmed cleanup.
- [ ] `ChainResult.environment`, `AttemptRecord.cleanup` and the environment results in the attempt record.
- [ ] Native test: durable equals direct for a ready and a blocked case with one `prepare_environment` scheduled; no preparation stops with `PreparationMissing`.
- [ ] `make test-config`, native tests, `make eval AGENT=chain`, `make eval AGENT=environment`; CURRENT.md row; handoff ([HANDOFF-0096](../handoffs/HANDOFF-0096-durable-environment-stage.md)).

## Validation and progress

- 2026-10-13: records written; PLAN-0075 and HANDOFF-0096 reserved in the shared record-numbers file.

## Decisions and next action

Defaults chosen where the work forked: one activity for the whole stage (the setup ledger and live sandbox cannot persist across PydanticAI's per-call activities); one attempt, never retried, because setup commands have side effects; the activity's start-to-close timeout is the stage timeout plus a fixed margin for preparation and release. Next: the OpenShell `Preparation` adapter, then a chain eval case with setup source.
