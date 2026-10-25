---
id: PLAN-0118
kind: plan
title: Fail closed before adversarial execution when control cleanup is unconfirmed
status: implemented_pending_native_qualification
updated: 2026-10-25
---

# Cleanup fail-closed boundary

## Goal and scope

Make ordinary `EvidenceVerifier` role execution fail closed after it records a control raw receipt whose physical cleanup cannot be independently confirmed. The verifier must not start the adversarial role in that case. Preserve the received control raw evidence, the established default `ERROR`/`role was not executed` adversarial observation, an overall `cleanup_confirmed=False`, and the existing inconclusive policy result.

This change is limited to the ordinary evidence verifier loop and its owning fake-sandbox unit coverage. It does not change Docker cleanup, receipt validation rules, evidence schema, workflow scheduling, role permissions, resource limits, or normal paired probes whose control cleanup is confirmed.

## Implemented decision

After `execute_role` returns and the verifier stores the control raw reference, it checks that reference with the existing `_physical_cleanup_confirmed` identity-and-cleanup predicate. If the predicate is false, the role loop stops before creating an adversarial container. The existing completion defaults then retain an unexecuted adversarial observation and a `None` adversarial raw reference; the committed evidence bundle retains the control raw reference. The aggregate cleanup calculation remains false, and `decide` therefore reports `INCONCLUSIVE` with `ERROR` status rather than treating any partial execution as clearance.

A focused `_FakeSandbox` regression makes its raw receipt cleanup flag configurable. The new test asserts exactly one call, retained control raw evidence with `cleanup_confirmed=False`, no adversarial raw receipt, the established unexecuted adversarial observation, and the conservative policy outcome. The existing normal fake-sandbox test continues to assert two calls and successful paired control/adversarial behavior.

## Actual focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_evidence.py -q
```

Passed: `8 passed in 0.62s`. This includes the new scripted fake-sandbox cleanup-failure regression and the existing confirmed-cleanup paired-probe/reconciliation coverage.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

Passed: Ruff reported `All checks passed!` and `2 files already formatted`; ty reported `All checks passed!`. `git diff --check` also passed.

## Unrun qualification gates

The focused result uses a scripted fake sandbox only. The following gates remain unrun for this change: real-Docker cleanup-failure behavior, actual Temporal workflow/replay execution, the full offline or native suite, fresh wheel build and installed-package resource loading, live-provider evaluation, and CI/platform qualification. No fake result establishes Docker cleanup integrity, durable execution behavior, hostile-source observation integrity, or production readiness.

See the delivery record at [HANDOFF-recommendation-cleanup-fail-closed](../handoffs/HANDOFF-recommendation-cleanup-fail-closed.md).

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 152 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
