---
id: PLAN-0034
kind: plan
title: Fully live fixture E2E over the OpenShell test workspace
status: in_progress
updated: 2026-10-13
related: [SPEC-0031, SPEC-0032, PLAN-0031, PLAN-0032, SPEC-0025, PLAN-0028, ISSUE-0007]
---

# Fully live fixture E2E over the OpenShell test workspace

## Objective and dependencies

Close the open PLAN-0031 step: plug a `Runners` factory over the [SPEC-0032](../specs/SPEC-0032-openshell-test-workspace.md) OpenShell test workspace into the [SPEC-0031](../specs/SPEC-0031-fixture-direct-composition.md) E2E-0 chain and run the SPEC-0018 fixture pair fully live on RIG0 (kind, OpenShell 0.1.3, local model), so a live author's own tests execute inside a fresh sandbox. Also gather live facts on the two open sandbox gaps that block real repositories under [SPEC-0025](../specs/SPEC-0025-sandbox-source-fetch.md)/[PLAN-0028](PLAN-0028-environment-agent-and-source-fetch.md): a quota-enforcing storage volume and the 0.1.3 credential placeholder.

Out of scope, owned elsewhere: witness capture outside the test process (SPEC-0033/PLAN-0033, parallel thread), so every gate verdict stays at most `completed`/`inconclusive`/`not_verified`; agent prompt or budget changes (PLAN-0035, parallel thread); real repositories, the environment agent and durable mode.

## Steps

- [x] `evals/fixture_e2e/sandbox.py`: `sandbox_runners` (one fresh sandbox per runner call, variant per purpose as in the reviewed route) and `sandbox_case` (sandbox discovery argv, toolchain pytest version, declared identity from the image manifest, argv, hash-pinned wheels, policy file and limits; revision sources are the captured snapshot manifests).
- [x] `evals/fixture_e2e/run.py`: `record_run` shared by the reviewed CLI and the live gate; configuration records route, environment, identity and revision sources; scripted planning follows the case's discovery argv.
- [x] Offline tests `tests/agents/test_fixture_sandbox.py` over fake sandbox ports: full scripted chain with three fresh sandboxes; a model-authored test is delivered and run (the host route refuses it); configuration and journal evidence.
- [x] Live gate `tests/qualification/test_fixture_e2e.py`, marker `fixture_e2e`, target `make qualify-fixture-e2e`: an all-scripted control asserted strictly, then `CORSAIR_E2E_RUNS` live runs recorded but not asserted; every native run must confirm cleanup and leave no Sandbox resource.
- [ ] Fresh RIG0 runtime and live run: control plus live runs on llm.almckay.io.
- [ ] Live facts on storage quota and the credential placeholder (throwaway probes; no policy change).
- [ ] Review, CURRENT.md, HANDOFF-0052.

## Validation and progress

2026-10-13, cloud container from main `0d9bb5a`: `make test-config` 781 passed before the change, 784 after (3 new). `-m fixture_e2e --collect-only`: 1 selected. Live: pending.

## Decisions and next action

The sandbox route reuses PLAN-0032's adapters and wiring unchanged; the only new code is the purpose-to-variant factory, the sandbox environment declaration and the gate. The scripted control runs first in every gate invocation so a live failure can be attributed to the agent rather than the route. Live agent outcomes are not gate assertions. Next: switch the RIG0 worktree to this branch and run the gate.
