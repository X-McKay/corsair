---
id: HANDOFF-recommendation-producer-abstention
kind: handoff
title: Producer decision abstention implementation
status: pending_parent_qualification
updated: 2026-10-25
---

# Handoff

Implemented the approved bounded producer-abstention change on `manus/producer-abstention` only. The native producer `LlmAgent.output_schema` is now the canonical Pydantic `ProducerDecision`: a discriminated `proposal` variant wraps the unchanged `Submission`, and `NoGroundedCandidate` carries a bounded abstention reason. The production adapter returns that typed decision through `ProducerOutput`; existing `Submission` remains the proposal/evidence contract.

A newly recorded no-grounded-candidate decision ends the workflow as `COMPLETED` / `INCONCLUSIVE`, retaining the prepared manifest and producer usage but calling neither evidence nor audit. The workflow uses native `workflow.patched("producer-abstention-v1")` because this terminal branch changes scheduled commands. Histories without that marker retain the preceding no-submission progression; `ProducerOutput.submission` is retained only for decoding previously serialized activity/result payloads. The change cannot yield `REFUTED` or a negative clearance.

The producer prompt/metadata and manifest capability output-schema fingerprint are updated. `Settings.identity` deliberately remains the digest of unchanged settings; the run manifest separately captures the changed producer schema, prompt, and metadata capability identity. Maintained evaluator/scoring consumers now obtain a submission from the typed decision. Existing frozen source/oracle/dataset JSON and their hashes were not modified; no additional AI-authored candidate dataset was required for this schema/workflow regression.

## Focused executed result

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_agents.py tests/unit/test_agent_evaluator.py tests/unit/test_evaluation.py -q -W error
```

Passed **29 tests in 3.72s**. This used the installed pinned ADK `Runner` with a deterministic `BaseLlm`: direct schema output validates the proposal variant, and the native schema-tool fallback (`set_model_response`) validates the abstention variant. It is not a provider or full-chain qualification.

The complete pure unit suite initially reported **101 passed, 1 failed in 10.26s** because one maintained metadata assertion still named the superseded producer schema reference. After correcting that assertion, this command passed **102 tests in 19.45s**:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/producer-abstention /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit -q -W error
```

Pinned changed-file Ruff lint/format, `ty check --python /Users/al/git/corsair/.venv`, and `scripts/check_docs.py --root .` also passed. Frozen `evals/fixtures`, `evals/datasets`, and historical `evals/baselines` have no diff.

The new Temporal regression was collected without enabling a service (`1 test collected in 0.04s`); collection confirms test discovery only and is not an execution result.

## Parent-required gates

The following are intentionally unrun by this implementation task, which forbids model, Docker, and service calls:

1. New real-Temporal regression: `CORSAIR_TEST_TEMPORAL=1 ... pytest tests/workflow/test_investigation.py::test_producer_abstention_is_inconclusive_and_skips_target_execution -q -W error`, plus affected workflow and replay tests. Confirm `producer-abstention-v1` patch-marker replay behavior.
2. Scripted ADK with real Docker/Temporal chain and package resource checks; retain the distinction from live-model evidence.
3. Independent frozen producer diagnostic against the reviewed live provider, recording abstention/provider outcomes without changing original source/oracle bytes or historical cohort identities.
4. Parent integrated `just check`, package, and CI gates on the final integrated tree. Local changed-file Ruff/format, Ty, documentation, and pure-unit checks already passed but are not full qualification.

No commit, push, merge, Git configuration change, dependency installation, model call, Docker call, or service call was performed.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **153 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. This feature must remain draft. The retained live producer/auditor fixtures scored 3/9 and 12/12; the earlier composed batch scored 0/3, and its lost local waiter was not resubmitted. [ISSUE-0012](../../active/ISSUE-0012-producer-decision-live-quality.md) retains the unqualified gate. The packaged risk digest changes capability identity, and v2 execution intents bind that digest. Existing v1 claims remain retained and mismatched reconciliation is explicit, not silently migrated. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-producer-abstention-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
