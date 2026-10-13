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
- [x] One module-level `prepare_environment` shared by `run_direct` and the activity.
- [x] `StageKeys.environment` (optional, admitted like the others), `ChainRuntime.preparation` and the worker's models, `configure_chain(..., preparation=)`, `run_durable(..., preparation=)`, the stage budget in the ceiling check.
- [x] The activity and its typed record; the workflow schedules it once with the stage timeout plus a margin, and a failed activity is a recorded failure with unconfirmed cleanup.
- [x] `ChainResult.environment`, `AttemptRecord.cleanup` and the environment results in the attempt record.
- [x] Native test: durable equals direct for a ready and a blocked case with one `prepare_environment` scheduled; no preparation stops with `PreparationMissing`.
- [x] `make test-config`, native tests, `make eval AGENT=chain`, `make eval AGENT=environment`; CURRENT.md row; handoff ([HANDOFF-0096](../handoffs/HANDOFF-0096-durable-environment-stage.md)).

## Validation and progress

- 2026-10-13: records written; PLAN-0075 and HANDOFF-0096 reserved in the shared record-numbers file.
- 2026-10-13, main `7d04cf3` merged (#91, #101, #99): `make test-config` 1756 passed. Native Temporal `tests/temporal/test_chain_native.py` 14/14 against a local dev server: durable equals direct for a ready case (complete) and a blocked case (stops at `environment`), apart from the random setup-command operation ids, with one `corsair.chain.prepare_environment` scheduled at one attempt and the sandbox prepared and released once; no environment key and no worker preparation each stop with `PreparationMissing` as in direct mode. `make eval AGENT=chain` scripted 5/5 clean; `make eval AGENT=environment` scripted 16/16.
- Main `59492d2` (#104) merged afterwards: SPEC-0068's trust line now says the non-pytest runners accept the agent's discovery command without running it.

- Review of `be51a24` after the merge (#103 `fa1b19c`), follow-up PR: a worker without the preparation port or the environment model now records no cleanup (no sandbox was made), not `unconfirmed`, matching direct mode; the native port test asserts it and failed before the fix. The activity's record drops its messages, with the limitation `environment stage messages omitted`, when its encoded JSON exceeds 1 MiB (model output is bounded by usage, not bytes); an offline test drives a 1 MiB model response through the activity. A prepare timeout leaving a sandbox behind is the preparation adapter's to handle (release or sweep by operation), recorded for that slice.
- Relay 17:11Z, every real case stopped at planning ("the baseline test file must be in the saved inventory"): the ready environment's baseline test file now joins the planning and authoring inventory from the operator's capture (`PreparedSandbox.read_source`), carried through the durable record as `baseline_source`; a capture without it, or not text, stops at `environment`. Taken on #106 rather than a separate PR because this thread works on one branch and #106 already holds the routing it changes. Offline tests: the file joins from the capture and reaches planning; a missing or non-UTF-8 capture file stops; native `ready-from-capture` durable equals direct.
- Coordinator review of `f4dbecb`: a 24 KB plain baseline test file stopped the run as "not text". The reason now names the cause (missing, not UTF-8, or the character count against the saved-source limit of 16,384 per file), carried through the durable record as `baseline_refusal`; a test covers each, including a large plain file. Carrying larger files would raise the shared `SourceFile` bound for every agent and their baselines, so it is left for a separate decision.

## Decisions and next action

Defaults chosen where the work forked: one activity for the whole stage (the setup ledger and live sandbox cannot persist across PydanticAI's per-call activities); one attempt, never retried, because setup commands have side effects; the activity's start-to-close timeout is the stage timeout plus a fixed margin for preparation and release. Next: the OpenShell `Preparation` adapter, then a chain eval case with setup source.
