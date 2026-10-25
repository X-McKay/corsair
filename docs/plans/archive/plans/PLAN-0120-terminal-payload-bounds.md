---
id: PLAN-0120
kind: plan
title: Bounded terminal result and diagnostic payloads
status: implemented_unqualified
updated: 2026-10-25
---
# Goal

Keep final result, activity-failure, and batch child-failure diagnostics safely below a conservative terminal wire budget before `corsair.record`, without removing structured evidence, raw-receipt provenance, operation claims, explicit terminal state, or unknown usage.

## Implemented scope

- `DiagnosticText` is the one canonical Pydantic constraint for optional diagnostic text: non-empty and at most 4,096 characters. It is used by terminal result reasons, feedback reasons, native role observation reasons, auditor reasons, and batch item errors. Feedback gates are likewise bounded to 128 characters.
- `InvestigationResult.rounds` is canonically capped at 16, matching the admitted `Budget.max_rounds` limit. Its model validator rejects a serialized result above the conservative 1,000,000-byte terminal budget.
- `format_terminal_result` is a pure formatter. It serializes the current result, caps only known optional diagnostic `reason` fields with the explicit ` … [diagnostic truncated]` marker, then calls `InvestigationResult.model_validate_json` on the resulting JSON. It also checks the exact validated Pydantic JSON output size. This revalidation closes the `model_copy(update=...)` validation bypass.
- The workflow invokes the formatter immediately before scheduling `corsair.record`. The real record activity invokes it again after clearing `result_artifact` and after attaching the immutable result artifact reference, so both persisted input and returned output are revalidated.
- The concrete producer, auditor, evidence, source-denial, record, and batch child-workflow error paths compact exception text before it becomes a Temporal error/result diagnostic. They re-raise attributed errors; they do not suppress failures. A non-diagnostic oversized value remains an explicit validation failure rather than being shortened or discarded.
- No immutable evidence reference, native receipt reference, operation identifier/digest, submitted payload, hypothesis, plan, disposition, execution status, fix status, or `usage_complete` value is truncated by the formatter. The final result still retains every structured reference needed to locate immutable native artifacts.

## Focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/unit/test_terminal_payload.py tests/unit/test_composition.py tests/unit/test_terminal.py
```

Passed: **22 tests in 4.35s**. The new isolated tests cover diagnostic marker insertion, preservation of submission claims and native artifact provenance, revalidation failures for an oversized model-copied operation claim or 17 model-copied rounds, and direct concrete record-activity revalidation before persistence and after artifact attachment.

```bash
/Users/al/git/corsair/.venv/bin/ruff check src/corsair/contracts/__init__.py src/corsair/contracts/agents.py src/corsair/contracts/common.py src/corsair/contracts/evaluation.py src/corsair/contracts/evidence.py src/corsair/contracts/results.py src/corsair/steps/activities.py src/corsair/workflows/evaluation.py src/corsair/workflows/investigation.py tests/unit/test_terminal_payload.py tests/workflow/temporal.py tests/workflow/test_investigation.py
/Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/contracts/__init__.py src/corsair/contracts/agents.py src/corsair/contracts/common.py src/corsair/contracts/evaluation.py src/corsair/contracts/evidence.py src/corsair/contracts/results.py src/corsair/steps/activities.py src/corsair/workflows/evaluation.py src/corsair/workflows/investigation.py tests/unit/test_terminal_payload.py tests/workflow/temporal.py tests/workflow/test_investigation.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

Passed: pinned Ruff lint, pinned Ruff format check, and pinned ty with no diagnostics.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q -m 'not temporal and not docker and not live' --ignore=tests/integration/test_package.py
```

Passed: **122 tests, 33 deselected in 10.39s**. This is an offline/no-service selection and is not native, live-provider, package, or full qualification.

## Opt-in real Temporal coverage

`tests/workflow/test_investigation.py` now includes two `@pytest.mark.temporal` cases using a real Temporal worker and typed fake activities:

1. A 16-round held-result history asserts both the actual encoded `corsair.record` input and returned result stay within 1,000,000 bytes.
2. An oversized fake evidence activity error asserts the final persisted result remains `ERROR`, keeps the `evidence:` attribution, retains the completed producer submission, reports complete known usage, and records a concise truncation marker.

The tests were collected without enabling Temporal:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/workflow/test_investigation.py -k 'maximum_round_result or oversized_activity_error'
```

Result: **2 skipped, 9 deselected in 0.03s** because `CORSAIR_TEST_TEMPORAL=1` was intentionally not set. No Temporal service was launched.

## Boundaries and remaining gates

A broader no-service command was attempted first. Its ordinary tests reached **121 passed, 33 deselected**, but `tests/integration/test_package.py` invoked `uv build` and was blocked by local execution policy from creating `/Users/al/.cache/uv` state and binding its local cache service. It exited with one package-test failure; it was not retried or escalated because wheel/package qualification is parent-owned.

Unrun: real Temporal (`CORSAIR_TEST_TEMPORAL=1`), Docker/native evidence, provider/live-agent tests, wheel/sdist build and external installed-resource loading, full `just check`, full CI, and any cross-platform qualification. The passing scripted unit/offline results do not establish those gates or a general payload-limit guarantee beyond the tested formatter and actual Pydantic JSON budget.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 160 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
