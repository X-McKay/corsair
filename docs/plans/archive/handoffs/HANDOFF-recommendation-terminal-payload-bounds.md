---
id: HANDOFF-recommendation-terminal-payload-bounds
kind: handoff
title: Terminal payload bounds recommendation implementation
status: ready_for_parent_qualification
updated: 2026-10-25
---
# Delivery record

This worktree implements the approved terminal payload-bound recommendation only. It adds one canonical 4,096-character diagnostic text constraint, a 16-round result constraint, and a conservative 1,000,000-byte `InvestigationResult` JSON budget. `format_terminal_result` is pure: it retains all structured facts and artifact references, compacts only optional diagnostic reasons with ` … [diagnostic truncated]`, and validates the actual serialized JSON again so `model_copy` updates cannot bypass the final wire contract.

The investigation workflow formats immediately before `corsair.record`; the concrete record activity repeats validation after removing and then adding `result_artifact`. Producer, auditor, evidence, source-denial, record, and evaluation-child error diagnostics are compacted before they become Temporal wire data. Errors are re-raised with type/phase attribution, not swallowed. Oversized operation claims, native facts, and artifact provenance are never silently truncated; final validation rejects them explicitly.

## Test evidence

Passed focused pure unit tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/unit/test_terminal_payload.py tests/unit/test_composition.py tests/unit/test_terminal.py
# 22 passed in 4.35s
```

Passed pinned checks:

```bash
/Users/al/git/corsair/.venv/bin/ruff check src/corsair/contracts/__init__.py src/corsair/contracts/agents.py src/corsair/contracts/common.py src/corsair/contracts/evaluation.py src/corsair/contracts/evidence.py src/corsair/contracts/results.py src/corsair/steps/activities.py src/corsair/workflows/evaluation.py src/corsair/workflows/investigation.py tests/unit/test_composition.py tests/unit/test_terminal_payload.py tests/workflow/temporal.py tests/workflow/test_investigation.py
/Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/contracts/__init__.py src/corsair/contracts/agents.py src/corsair/contracts/common.py src/corsair/contracts/evaluation.py src/corsair/contracts/evidence.py src/corsair/contracts/results.py src/corsair/steps/activities.py src/corsair/workflows/evaluation.py src/corsair/workflows/investigation.py tests/unit/test_composition.py tests/unit/test_terminal_payload.py tests/workflow/temporal.py tests/workflow/test_investigation.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
# all passed; ty reported no diagnostics
```

Passed no-service selection (intentionally excludes parent-owned wheel build):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q -m 'not temporal and not docker and not live' --ignore=tests/integration/test_package.py
# 122 passed, 33 deselected in 10.39s
```

The newly added real-Temporal worker cases for oversized fake activity errors and 16 rounds were collected but not run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/workflow/test_investigation.py -k 'maximum_round_result or oversized_activity_error'
# 2 skipped, 9 deselected in 0.03s; CORSAIR_TEST_TEMPORAL was intentionally unset
```

An initial no-service selection including `tests/integration/test_package.py` reached 121 passing tests but failed its `uv build` subprocess after local policy blocked external `/Users/al/.cache/uv` writes and a local bind. It was deliberately not escalated or retried.

## Parent-required gates

Run the real Temporal opt-in coverage with the reviewed service; native Docker/evidence tests; real ADK/provider and frozen evaluation coverage; wheel/sdist build plus installed-outside-checkout resource loading; complete `just check`; and CI/cross-platform qualification as applicable. Do not treat fake activities, skipped Temporal cases, or no-service tests as native/live/package qualification.

No commit, push, merge, Git configuration, installation, model call, Docker invocation, Temporal service launch, or package build was performed in this worktree.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **160 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The packaged risk digest changes capability identity, and v2 execution intents bind that digest. Existing v1 claims remain retained and mismatched reconciliation is explicit, not silently migrated. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-terminal-payload-bounds-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
