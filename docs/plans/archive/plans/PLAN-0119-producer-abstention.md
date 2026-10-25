---
id: PLAN-0119
kind: plan
title: Canonical producer abstention decision
status: implemented_pending_native_gates
updated: 2026-10-25
---

# Delivery scope

Implement one canonical native ADK `ProducerDecision` schema. Its discriminated `proposal` variant retains the existing `Submission`; its `no_grounded_candidate` variant records a bounded abstention reason. Do not change the auditor, evidence verifier, target permissions, Docker execution, negative-clearance policy, historical frozen fixture/oracle bytes, datasets, or model/provider configuration.

## Design and compatibility

`ProducerDecision` is a frozen Pydantic root model with a `kind`-discriminated `ProducerProposal | NoGroundedCandidate` value and is passed directly to `LlmAgent.output_schema`. Production inference parses that one typed decision without text repair. A proposal preserves the existing round/parent validation and supplies its nested `Submission` to trusted evidence/audit consumers. An abstention is successful structured producer data, not feedback or a provider failure.

`ProducerOutput.submission` remains solely to decode already-recorded activity/result payloads. New inference and maintained consumers use `ProducerOutput.submission_for_verification()`, which obtains a submission only from the current proposal decision or this documented historical decode path. A model cannot emit both shapes in one output.

For a new abstention, `InvestigationWorkflow` records the producer round and exits `INCONCLUSIVE` before evidence or audit activities. It preserves prepared manifest provenance and producer usage; it cannot produce `REFUTED` or target execution. `workflow.patched("producer-abstention-v1")` records the command-history change for new abstention histories and retains the prior no-submission progression while replaying a history without that marker.

`Settings.identity` is unchanged because settings did not change. `RunManifest.capabilities["producer"]` receives a new native output-schema digest and existing metadata/prompt fingerprints, making the contract identity visible without misrepresenting it as a settings change.

## Focused implementation evidence

The following local command used the parent-provided pinned environment and real ADK `Runner` with deterministic local `BaseLlm` responses:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_agents.py tests/unit/test_agent_evaluator.py tests/unit/test_evaluation.py -q -W error
```

It passed **29 tests in 3.72s**. It includes native ADK direct response-schema handling for the proposal variant and ADK's native `set_model_response` schema-tool fallback for the abstention variant. It also covers malformed/stale proposal rejection, no second producer request, current consumer/scoring behavior, and intentional decoding of pre-decision serialized producer output. This is scripted-native ADK coverage, not a live-provider result.

The complete pure unit command below initially reported **101 passed, 1 failed in 10.26s** because `test_model_settings.py` still expected the prior producer metadata schema reference. The maintained assertion was updated to the new canonical schema and the command was rerun successfully.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit -q -W error
```

It passed **102 tests in 19.45s**. Pinned Ruff lint and format checks passed for all 17 changed maintained code/test files; `PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv` passed; and `PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/python scripts/check_docs.py --root .` passed after the new plan/handoff and current documentation changes.

A real-Temporal scripted regression is added at `tests/workflow/test_investigation.py::test_producer_abstention_is_inconclusive_and_skips_target_execution`. It asserts a real worker maps abstention to completed `INCONCLUSIVE`, persists manifest/usage, and invokes neither evidence nor audit. It is intentionally unrun here: the authorized work excludes service calls, and this test needs `CORSAIR_TEST_TEMPORAL=1` plus the local Temporal test server.

Its no-service collection command passed with **1 test collected in 0.04s**:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention /Users/al/git/corsair/.venv/bin/python -m pytest tests/workflow/test_investigation.py::test_producer_abstention_is_inconclusive_and_skips_target_execution --collect-only -q -W error
```

Collection confirms discovery only; it is not a Temporal execution result.

## Required independent gates

- Run the new real-Temporal test and the affected Temporal workflow/replay suite with `CORSAIR_TEST_TEMPORAL=1`; confirm patch-marker history/replay behavior.
- Run scripted ADK plus real Docker/Temporal native composition and package-resource boundaries where available; this change itself made no Docker/model/service call.
- Run the isolated producer frozen diagnostics against a reviewed live provider and record abstentions/errors separately; do not alter the old source/oracle JSON, line hashes, or historical cohorts.
- Run the parent integrated `just check`, package, and CI qualification. Local changed-file Ruff/format, Ty, documentation, and pure-unit checks passed, but no focused result here is full qualification.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 153 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. The feature remains draft/unpromoted: isolated producer exact 3/9, auditor 12/12, earlier composed live 0/3; final full-live qualification remains open in ISSUE-0012. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
