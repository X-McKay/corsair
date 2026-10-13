---
id: HANDOFF-0094
kind: handoff
title: The environment agent as a chain stage
status: recorded
updated: 2026-10-13
related: [SPEC-0068, PLAN-0074, SPEC-0060, SPEC-0029, IDEA-0005]
---

# The environment agent as a chain stage

## Verified state

Branch `claude/chain-runtime-handoff-dtb1ut` restarted from main `165afac` after #73 merged, main `26c5316` merged since; draft PR #100. Delivered under [SPEC-0068](../specs/SPEC-0068-chain-environment-stage.md), direct mode only:

- `FixtureCase.setup` (`SetupSource`), the operator `Preparation` port (`PreparedSandbox`), `PreparationMissing`, `CompositionBudget.environment` and `setup_commands`, `StageModels.environment`, `run_direct(preparation=)`.
- `run_chain` runs `environment` after a supported runtime: `EnvironmentInput` with `RuntimeOutcome.toolchain` as the only toolchain, the agent in the prepared sandbox, `check_ready`, then `ready_evidence` replaces the declared `EnvironmentEvidence` (scratch location, recorders kept declared) and the identity's image and recipe digests. Blocked, unsupported, refused or failed runs stop at `environment`; `DirectRun.environment` and the fixture run record carry the result; `StageAttempt.cleanup` records the sandbox release.
- Durable mode returns `EnvironmentStageNotDurable` for a case with setup source.
- The declared-framework check reads `JUnit Jupiter 5.10` as `junit5` (`framework_names`).

## Validation and blockers

See [PLAN-0074](../plans/PLAN-0074-chain-environment-stage.md#validation-and-progress): `make test-config` 1671 passed; native Temporal chain file 11/11; scripted chain 5/5 and environment 16/16. No live run and no real preparation adapter: the stage is exercised with a scripted environment model and a host double.

## Decisions and next steps

- Revisions still run on the operator's runners; binding them to the prepared image or recipe is open (SPEC-0068).
- Non-pytest runners refuse discovery commands other than the operator's prefix; the Perl thread owns that fix. Until it lands, a non-pytest case through this stage stops at its first test run.
- Next: the durable stage (sandbox lifecycle as activities, the setup ledger rebuilt per tool activity), an OpenShell `Preparation` adapter, and a chain eval case with setup source.

## Continuation prompt

Continue PLAN-0074 from PR #100: read SPEC-0068 and this handoff, verify the branch against main, then design the durable environment stage as its own spec section before code.
