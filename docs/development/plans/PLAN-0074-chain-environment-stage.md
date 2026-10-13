---
id: PLAN-0074
kind: plan
title: The environment agent as a chain stage
status: in_progress
updated: 2026-10-13
related: [SPEC-0068, SPEC-0060, SPEC-0029, PLAN-0065]
---

# The environment agent as a chain stage

## Objective and dependencies

Implement [SPEC-0068](../specs/SPEC-0068-chain-environment-stage.md) from main `165afac` (#73 merged). Depends only on merged work: SPEC-0060 runtime stage, the SPEC-0029 environment agent on the package convention (#62, #63 blockers, #96 TAP). No kind cluster or model server is needed. The environment agent's prompt, skill and tools are not changed, so its eval baseline stands.

## Steps

- [x] `SetupSource`, `PreparedSandbox`, `Preparation` port and `PreparationMissing`; `FixtureCase.setup`; `CompositionBudget.environment`.
- [x] Mapping `ready_evidence(result, declared, identity)` and `recipe_sha256` beside `check_ready`; `RuntimeOutcome.toolchain` carries the selected row as the agent's toolchain so durable workflow code needs no matrix; unit tests.
- [x] `run_chain` environment stage (direct mode) with routing, stops, limitation lines and `DirectRun.environment`; `run_direct(preparation=)`; tests with a scripted environment model and a host double.
- [x] Durable mode: typed stop for a case with setup source; `ChainResult.environment` left for the durable slice.
- [x] Carried from #73 review: accept `JUnit Jupiter 5.10` as `junit5` in the declared-framework check.
- [x] `make test-config`, `make eval AGENT=chain`, `make eval AGENT=environment`; CURRENT.md row; handoff ([HANDOFF-0094](../handoffs/HANDOFF-0094-chain-environment-stage.md)); review pending.

## Validation and progress

- 2026-10-13: records written; numbers SPEC-0068/PLAN-0074/HANDOFF-0094 reserved in the shared record-numbers file.
- 2026-10-13, main `26c5316` merged: `make test-config` 1670 passed. `tests/agents/test_chain_environment_stage.py` 9 passed (ready continues with the observed recipe digest reaching assessment; unconfirmed cleanup; blocked; unsupported; a 34-token discovery command the planner's contract cannot hold; no model, no port, refused preparation; setup without a runtime). Native Temporal `tests/temporal/test_chain_native.py` 11/11 against a local dev server, including the durable `EnvironmentStageNotDurable` stop with only `select_runtime` scheduled. `make eval AGENT=chain` scripted 5/5 clean; `make eval AGENT=environment` scripted 16/16.

## Decisions and next action

Defaults chosen where the work forked: direct mode first, durable stops with a typed reason; observation and witness facilities, dependency inventory, policy revision and limits stay the operator's; the SPEC-0060 declared-identity check is skipped when the stage ran. The discovery command the agent admits flows through planning to the revision runners exactly as the declared one did; the runners' refusal of non-operator discovery commands is the Perl thread's fix, not worked around here. Next: the durable stage (sandbox lifecycle activities, setup ledger per tool activity) and a chain eval case with setup source.
