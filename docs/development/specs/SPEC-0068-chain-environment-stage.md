---
id: SPEC-0068
kind: spec
title: The environment agent as a chain stage
status: draft
updated: 2026-10-13
related: [SPEC-0060, SPEC-0042, SPEC-0029, SPEC-0053, SPEC-0035, IDEA-0005, PLAN-0074, PLAN-0075]
---

# The environment agent as a chain stage

## Goal and scope

SPEC-0060 made runtime selection the chain's first stage, but the environment the later stages read is still the operator's declaration (`FixtureCase.environment`, `FixtureCase.environment_identity`), checked only against the selected row. The SPEC-0029 environment agent, which prepares a sandbox of one toolchain, runs one existing baseline test and returns `ReadyEnvironment`, is not called (IDEA-0005 G12). This spec puts it in the chain after runtime selection:

- a case may carry its setup source (manifests, CI workflows, setup docs) and policy profile;
- for a supported runtime, the chain builds `EnvironmentInput` with the selected row as the only toolchain (`environment_input`), prepares a sandbox of that row's prepared image through an operator port, and runs the environment agent there;
- a ready result is checked against the selection (`check_ready`) and mapped onto the `EnvironmentEvidence` and `EnvironmentIdentity` the later stages and gates read; blocked, unsupported, a refused ready result or a failed run end the run at stage `environment` with the reason and the agent's diagnostics.

Excluded: running the frozen revisions on the prepared sandbox or its recipe (the revision runners stay operator-owned), the dependency inventory node (SPEC-0026), changes to the environment agent's prompt, skill or tools, matrix rows and live runs.

## Boundaries and design

**Input.** `FixtureCase.setup: SetupSource | None` (new, in `composition/direct.py`): `commit`, `source_private`, `source_files` and `policy_profile`, the agent-visible fields of `EnvironmentInput` other than its toolchains. It is never labels or oracles. The stage runs only when the case has `runtime` and `setup` and selection is `supported`; with `setup` absent the run keeps today's declared environment and records a limitation.

**Port.** `Preparation` (operator-owned): given the selected `Toolchain` and a new operation id it yields a `PreparedSandbox` (the `SandboxExecution`, the `SandboxHandle`, the absolute scratch location) and releases the sandbox when the stage ends, confirming cleanup or reporting it unconfirmed. Adapters (OpenShell, a host double for evaluation) are chosen outside the chain. Direct mode takes it as `run_direct(..., preparation=)`; a case that needs the stage without a configured port stops at `environment` with `PreparationMissing`, the same pattern as `RuntimeCatalogMissing`.

**Stage.** `environment` is a new `Stage` and agent stage between `runtime` and `identification`. Its limits come from an operator `StageBudget` in `CompositionBudget.environment` (read windows over the setup source plus `setup_commands` work calls) and the agent's own `SetupBudget`. The defaults are the environment agent's isolated eval budget (16 requests, 20 tool calls, 48,000 tokens, 240 s; 12 setup commands), so the composed stage is not wider than its baseline. It runs once, without retries, through the same `StageInvoker` port as the other stages.

**Admission and mapping** (trusted code, `nodes/runtime/environment.py` beside `check_ready`):

- `check_ready(result, selection, prepared)` must pass: the selected row's id and prepared image, and a framework the selection admitted.
- `EnvironmentEvidence` from the ready result: `language`, `runtime`, `framework`, `discovery_command`, `approved_test_paths` and `baseline_test` (id and path) are observed; `observation_facilities` and `witness_facilities` stay the operator's (they name operator recorders, not anything the agent prepares), and so does `scratch_location`: the result's is the preparation sandbox's, which is released when the stage ends, while the revisions run in the operator's runners' own scratch, where planning places fixtures and witness `file_open` subjects (review of `6ec2632`).
- Trust: `discovery_command` and `approved_test_paths` are now agent-proposed. The agent's discovery command is admitted only as having succeeded and printed the baseline id in the preparation sandbox; planning must echo it exactly, and each revision runner admits what it executes (since #104 the Maven, TAP, Jest and Minitest runners accept it without running it and build their own listing; the pytest runner runs the command in its own workspace). `approved_test_paths` may not name a saved setup file.
- `EnvironmentIdentity`: `image_digest` is the digest of the ready result's `toolchain_image` and `recipe_sha256` the SHA-256 of the canonical JSON of the admitted recipe, build command, discovery command and baseline command. `dependency_inventory_sha256`, `policy_revision` and `limits_sha256` stay the operator's declaration until the inventory node and policy receipts exist, and the run records that limitation.

The mapped evidence replaces the declaration for planning, authoring, freezing, the gates and assessment. The SPEC-0060 declared-identity check is skipped when the stage ran, since the identity is now observed.

**Outcome.** `DirectRun.environment` carries the agent's `EnvironmentResult` when the stage ran. A `blocked` or `unsupported` result stops with its layer, requirement and the first `Blocker` diagnostic's code; a ready result that `check_ready` or the mapping refuses stops with that reason; a run without output stops with its failure kind like any agent stage. Sandbox cleanup that is not confirmed is a limitation on the run.

**Why bespoke.** The mapping is a field copy plus one digest; the port is the existing `SandboxExecution`/`SandboxHandle` pair with a lifecycle around it. PydanticAI runs the agent as everywhere else.

## Durable mode (PLAN-0075)

The durable chain runs the whole stage as one Temporal activity, `corsair.chain.prepare_environment` (a frozen name), scheduled once with no retry on the worker that holds the operator's `Preparation` and the environment model. The activity prepares the sandbox, runs the same agent factory with the same dependencies as direct mode, releases the sandbox and returns a typed record: the result, usage, messages, elapsed time, failure kind, limits and cleanup. Direct mode and the activity share one function, so their routing and stops match.

Why one activity and not a `TemporalAgent` with per-call activities: the agent's trusted setup ledger (records, full command output for the finalizer's discovery and baseline checks, halt and correction state) and the live sandbox handle must persist across tool calls, and PydanticAI discards dependency mutations made inside a tool activity by design. Rebuilding the ledger from messages would lose the full output the finalizer reads, and a sandbox cannot be resumed after a worker loss anyway: the stage is not retried because setup commands have side effects. Model requests therefore run inside the activity rather than as their own activities; a worker loss during the stage is a recorded activity failure that ends the run at `environment`.

Worker configuration: `configure_chain(..., preparation=)` and `run_durable(..., preparation=)`, the environment model under its own key (`StageKeys.environment`, admitted like the others), and the activity's start-to-close timeout is the stage's `timeout_seconds` plus a fixed margin for sandbox preparation and release. `ChainResult.environment` and `AttemptRecord.cleanup` carry what `DirectRun` carries. A worker that refuses for want of the preparation port or model records no cleanup, since no sandbox was made; any other activity failure records cleanup unconfirmed, and the adapter must be able to release or sweep a sandbox by its operation after a timeout. The record's messages are dropped, with a limitation, if its encoded JSON would exceed 1 MiB.

## Acceptance and validation

Offline, with a scripted environment model and a host double for the preparation port:

- ready continues: planning receives the mapped `EnvironmentEvidence`, the gate's runs carry the observed `image_digest` and `recipe_sha256`, and the limitations name the declared dependency, policy and limit fields;
- blocked, unsupported, a ready result on another toolchain or with an unadmitted framework, and a failed agent run stop at `environment` before identification, with no revision run;
- no preparation port stops with `PreparationMissing`; no setup source keeps the declared path and its limitation; unconfirmed cleanup is recorded;
- durable mode (PLAN-0075) gives the same routing, result and limitations as direct mode for a ready case and a blocked case, with exactly one `prepare_environment` activity scheduled at one attempt; a worker without a preparation port or environment model stops with `PreparationMissing`;
- `make test-config`, `make eval AGENT=chain` and `make eval AGENT=environment` unchanged (no frozen eval case carries setup source yet).

## Decisions and open questions

- Direct mode landed first (PLAN-0074, PR #100); the durable stage is one activity (PLAN-0075).
- The revision runners still choose their own image. Binding them to the prepared sandbox's image (or recipe) is a later decision; until then the runs' identity names the selected image, which the operator's runner configuration must match.
- A chain eval case with setup source and a recorded preparation double is the next eval addition.

The plans are [PLAN-0074](../plans/PLAN-0074-chain-environment-stage.md) (direct mode) and [PLAN-0075](../plans/PLAN-0075-durable-environment-stage.md) (durable mode).
