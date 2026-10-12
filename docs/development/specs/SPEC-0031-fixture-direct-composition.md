---
id: SPEC-0031
kind: spec
title: Direct-mode fixture composition
status: draft
updated: 2026-10-12
related: [IDEA-0004, SPEC-0018, SPEC-0022, SPEC-0024, SPEC-0027, SPEC-0028, SPEC-0030, PLAN-0031]
---

# Direct-mode fixture composition

## Goal and scope

Run E2E-0 from [IDEA-0004](../ideas/IDEA-0004-end-to-end-agent-plan.md): chain issue identification ([SPEC-0024](SPEC-0024-issue-identification.md)), test planning ([SPEC-0022](SPEC-0022-test-planning-agent.md)), test authoring ([SPEC-0028](SPEC-0028-test-authoring-agent.md)), frozen per-revision execution through the native pytest runner, evidence assessment ([SPEC-0030](SPEC-0030-evidence-assessment-agent.md)) and the [SPEC-0027](SPEC-0027-disposition-gates.md) gates on the [SPEC-0018](SPEC-0018-native-two-test-fixture.md) path-traversal pair, in direct mode, with environment evidence supplied by the operator in place of the environment agent.

Excluded: Temporal or any durable stage, the environment agent, the report renderer, the OpenShell test workspace (SPEC-0032, parallel), witness capture and real benchmark cases.

## Boundaries and design

**Handoff builder** (`composition/evidence.py`, trusted code only). `observation_plan(ReadyTestPlan, TestPatch) -> ObservationPlan` uses the mapping the stage threads agreed: `ExpectedFailure.exception_type = plan.security_expectation.failure_type`, `path = plan.security.test_path`, `function` = last `::` segment of `plan.security.test_id`, `assertion_lines = TestPatch.security_assertion_lines`; `expected_safe_behavior = plan.security_expectation.safe_behavior`; `frozen_patch_sha256 = TestPatch.patch_sha256`. It refuses a patch whose test ids, discovery command or security file differ from the plan. `freeze` rebuilds the `ApprovedPatch` from the patch files and refuses bytes that no longer hash to the authored digest. `run_evidence(NativeTestRun)` maps one native run to `RunEvidence`: delivery and completion from the last receipt (`not_dispatched` when the workspace refused before dispatch, `unknown` without a receipt), `execution_failure` `discovery` for inexact collection and `timeout`/`unknown` for every other runner layer, outcomes from parsed JUnit, and a failure classification only when every field fits the gate's types (anything else is unclassified, never coerced). `evidence_items` exposes the plan, environment identity, patch files and per-run receipt summary and JUnit as frozen items named `baseline`/`candidate`.

**Witness.** No execution node captures the planned witness outside the test process yet, so the composition passes `witness=None` for every run. The gates then classify both revisions as unusable (`witness_missing`) and permit at most `completed`/`inconclusive`/`not_verified`. This is the expected verdict by design, not a defect to work around; the test process's own audit-hook print stays an untrusted JUnit claim.

**Composition** (`composition/direct.py`). `run_direct(FixtureCase, StageModels, Runners, CompositionBudget)` reuses each stage's factory, prompt renderer and dependencies unchanged. Routing is a total match on the previous outcome: an identification abstention, an unsupported plan, blocked authoring, a refused handoff (the next stage's input validators) or a stage with no output stops the run with its reason; nothing loops between stages and no stage is retried. A patch is frozen once and executed in a fresh workspace per revision under a new operation id; a refused or failed run is recorded, never repeated. The gate verdict is computed from the frozen evidence before and independently of the assessment agent, whose proposal is admitted or rejected by its own trusted output function. Every stage attempt keeps usage, messages, elapsed time and failure. Operator-owned inputs: per-stage `UsageLimits` and timeouts, the authoring run budget, the model per stage, a runner factory per purpose (`development`, `baseline`, `candidate`) and a declared `EnvironmentIdentity`.

**Fixture execution.** Model-authored test code is untrusted workload code and never runs on the host. `evals/fixture_e2e/reviewed.py` (moved from the runner tests) is the only host workspace: it refuses every patch except the reviewed SPEC-0018 test bytes before anything executes. A live author's own tests therefore end in a `workspace_failure` development run and blocked authoring until the sandbox test workspace exists; that runner then plugs into the same `Runners` seam.

## Acceptance and validation

Deterministic tests in `tests/agents/test_fixture_composition.py`, scripted `FunctionModel` stages with real requests blocked and real pytest runs of the reviewed bytes: the four stages compose; both revisions execute the authored digest with confirmed cleanup; the baseline security failure is classified at a planned assertion line; the gate permits exactly `completed`/`inconclusive`/`not_verified` with `witness_missing` on both revisions; the assessment proposal of that triple is admitted and an over-claim is rejected with the gate value standing; supplying a witness to the same runs (test-only) permits `reproduced`/`verified`, showing the witness is the only missing gate input; mismatched patches are refused; abstentions stop before later stages; unreviewed test bytes never reach an interpreter; prompts carry no variant labels.

A live run on the local provider measures stage behavior on this one fixture; it is a smoke, not qualification, and cannot exceed the witness-limited verdict.

## Decisions and open questions

The environment agent stays out (IDEA-0004 default); the declared environment identity is the operator's statement for both revisions. Witness capture (owned by the execution node, likely OpenShell policy or sandbox telemetry) decides when a reproduced or verified disposition can exist and is the next design question. The composition lives outside `workflows/` because no durable stage is connected. Plan: [PLAN-0031](../plans/PLAN-0031-fixture-direct-composition.md).
