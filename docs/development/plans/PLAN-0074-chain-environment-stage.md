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

- [ ] `SetupSource`, `PreparedSandbox`, `Preparation` port and `PreparationMissing`; `FixtureCase.setup`; `CompositionBudget.environment`.
- [ ] Mapping `ready_evidence(result, declared, identity)` beside `check_ready`; unit tests.
- [ ] `run_chain` environment stage (direct mode) with routing, stops, limitation lines and `DirectRun.environment`; `run_direct(preparation=)`; tests with a scripted environment model and a host double.
- [ ] Durable mode: typed stop for a case with setup source; `ChainResult.environment` left for the durable slice.
- [ ] Carried from #73 review: accept `JUnit Jupiter 5.10` as `junit5` in the declared-framework check.
- [ ] `make test-config`, `make eval AGENT=chain`, `make eval AGENT=environment`; review; CURRENT.md row; handoff.

## Validation and progress

- 2026-10-13: records written; numbers SPEC-0068/PLAN-0074/HANDOFF-0094 reserved in the shared record-numbers file.
