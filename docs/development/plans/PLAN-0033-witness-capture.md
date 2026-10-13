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
- [x] Live gate authored: `make qualify-witness` (marker `witness`) on the SPEC-0032 recipe with the gates over the four runs.
- [x] Independent adversarial review; findings fixed (below).
- [ ] Live qualification on a fresh RIG0 kind node; results here.
- [x] Review, CURRENT.md row and [HANDOFF-0051](../handoffs/HANDOFF-0051-witness-capture.md).

## Validation and progress

2026-10-13, cloud container from main `0d9bb5a`: prototype over the reviewed pair through the real runner and reviewed host workspace gave vulnerable `(path_reached True, effect observed)` and fixed `(True, absent, ValueError)` on the first run. `make test-config` 811 passed (781 on main; new probe, runner and composition checks, one replaced composition check), one existing pydantic_graph deprecation warning. Two unit expectations were wrong on first run and corrected: a test opened `sub/../outside.txt` without creating `sub`, which the probe correctly reported as a failed open (effect unknown); and an exception in `pytest_sessionfinish` made pytest exit 1, not an internal error, so the probe now sets `INTERNAL_ERROR` itself when the record path is occupied. The live gate collects (`-m witness --collect-only`: 1 selected).

2026-10-13, independent Opus review of `f21294a` (empirical CPython 3.12 checks): blocking, the target cache keyed by code equality let an identical function in another file pass as the target (verified end to end) and import-time `.pyc` opens inside the target counted as the effect; should-fix, an unaddressable identified symbol crashed the composition, one `OSError` produced an event per frame, and refused or malformed records reached the assessor and could stop it. All fixed: identity-keyed cache, importlib frames excluded, request refusal runs unwitnessed with a limitation, one event per exception, only admitted records exposed, non-builtin exception types qualified. New negative checks for each. Recorded, not fixed: `observed` means any non-import open by the target (SPEC-0033 limits); the fixture planner input now lists the probe, so its prompts are not like-for-like with the PLAN-0031 baseline.

`make test-config` after the fixes: 816 passed.

2026-10-13, Al's review of `391682e` (two P1, both reproduced with the real probe and gates): a target reading only a benign config file supported `reproduced` because any open counted as the effect, and an application read executed by a module body during an import was hidden because any importlib ancestor frame excluded the open, letting a candidate reach `verified`. Fixed: witnesses are requested only inside an operator-approved envelope (target plus planned effect file name) matching the identification target, and only opens of that file are the effect; only opens and `OSError`s issued directly by importlib loader frames are excluded. Both counterexamples are now real subprocess regressions, plus envelope refusal in the composition. `make test-config`: 820 passed.

Live: not run.
- The fully live E2E thread then handed over its fresh RIG0 node: network 3/3 and admission 1/1 today, toolchain images loaded, gateway installed.
- The qualification fixtures only accept kind state and evidence inside the running worktree.
- Al approved hardlinking the kind kubeconfig into `/home/al/git/corsair-witness`, but RIG0's auto-mode safety check denied all three staging attempts.
- Nothing was staged and the cluster was untouched. `make test-config` on RIG0 at `646f7fd`: 820 passed.

## Decisions and next action

The design fork (in-interpreter operator probe versus an out-of-process kernel observer) was put to the user as a decision card; work continued on the recommended probe. The probe travels as an execution argument instead of a file, so the SPEC-0032 tree admission and the toolchain image are unchanged. Next: run the live gate interactively on RIG0, then record the result here. Command sequence:

```
cd /home/al/git/corsair-witness
mkdir -p -m 700 .state/kind .state/openshell .runs/reused-live-e2e-20261013
ln ../corsair-live-e2e/.state/kind/kubeconfig .state/kind/kubeconfig
cp -p ../corsair-live-e2e/.state/kind/owner.json .state/kind/
cp -a ../corsair-live-e2e/.runs/live-e2e-20261013/{network,admission} .runs/reused-live-e2e-20261013/
jq '.admission_evidence="/home/al/git/corsair-witness/.runs/reused-live-e2e-20261013/admission"' ../corsair-live-e2e/.state/openshell/owner.json > .state/openshell/owner.json && chmod 600 .state/openshell/owner.json
make tools
CORSAIR_NETWORK_RUN=.runs/reused-live-e2e-20261013/network CORSAIR_QUAL_RUN=.runs/witness-$(date -u +%Y%m%dT%H%M%S) make qualify-witness
rm .state/kind/kubeconfig
cd ../corsair-live-e2e && make openshell-install CORSAIR_ADMISSION_RUN=.runs/live-e2e-20261013/admission
```
