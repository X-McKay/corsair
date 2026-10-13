---
id: PLAN-0033
kind: plan
title: Execution-node witness capture
status: in_progress
updated: 2026-10-13
related: [SPEC-0033, SPEC-0027, SPEC-0031, SPEC-0032, PLAN-0031, PLAN-0032]
---

# Execution-node witness capture

## Objective and dependencies

Implement [SPEC-0033](../specs/SPEC-0033-witness-capture.md): the execution node captures a typed witness per frozen revision run so the [SPEC-0027](../specs/SPEC-0027-disposition-gates.md) gates can admit `reproduced` and `verified`. Builds on the native pytest runner (PLAN-0027), the OpenShell test workspace ([PLAN-0032](PLAN-0032-openshell-test-workspace.md), merged in #31) and the E2E-0 composition ([PLAN-0031](PLAN-0031-fixture-direct-composition.md), merged in #32). Independent of the parallel fully live E2E (PLAN-0034) and agent behaviour (PLAN-0035) threads; both consume the same `Runners` seam.

## Steps

- [x] `nodes/witness_probe.py`: stdlib pytest probe with `sys.monitoring` and audit hooks, call-phase scoping, integrity flags and exclusive record write.
- [x] `nodes/witness.py`: bootstrap, `probe_argv`, strict record model and `witness_evidence` mapping; `WitnessRequest`/`WitnessCapture` on the runner port.
- [x] `PytestRunner`: optional witness request, `witness_record_path`, single fixed read-back after a completed execution.
- [x] Composition: target from the identification, witness and sandbox events per revision into the gates, refusal reasons as limitations, record as a `witness` evidence item; CLI journal forwards the request.
- [x] Offline tests: real probe subprocesses, runner orchestration, composition reaching `reproduced`/`verified`.
- [x] Live gate `make qualify-witness` (marker `witness`) on the SPEC-0032 recipe with the gates over the four runs.
- [ ] Live qualification on a fresh RIG0 kind node; results here.
- [ ] Review, CURRENT.md row and HANDOFF-0051.

## Validation and progress

2026-10-13, cloud container from main `0d9bb5a`: prototype over the reviewed pair through the real runner and reviewed host workspace gave vulnerable `(path_reached True, effect observed)` and fixed `(True, absent, ValueError)` on the first run. `make test-config` 811 passed (781 on main; new probe, runner and composition checks, one replaced composition check), one existing pydantic_graph deprecation warning. Two unit expectations were wrong on first run and corrected: a test opened `sub/../outside.txt` without creating `sub`, which the probe correctly reported as a failed open (effect unknown); and an exception in `pytest_sessionfinish` made pytest exit 1, not an internal error, so the probe now sets `INTERNAL_ERROR` itself when the record path is occupied. The live gate collects (`-m witness --collect-only`: 1 selected).

Live: not yet run. The RIG0 helper found the shared kind cluster in use by the fully live E2E thread and changed nothing; the run waits for that thread to finish.

## Decisions and next action

The design fork (in-interpreter operator probe versus an out-of-process kernel observer) was put to the user as a decision card; work continued on the recommended probe. The probe travels as an execution argument instead of a file, so the SPEC-0032 tree admission and the toolchain image are unchanged. Next: run `make qualify-witness` on RIG0, record the result, then the handoff.
