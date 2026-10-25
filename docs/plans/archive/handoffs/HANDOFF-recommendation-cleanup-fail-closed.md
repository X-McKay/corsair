---
id: HANDOFF-recommendation-cleanup-fail-closed
kind: handoff
title: Cleanup-fail-closed recommendation implementation
status: focused_fake_validation_only
updated: 2026-10-25
---

# Delivery record

Implemented the approved narrow verifier change on `manus/cleanup-fail-closed`: once ordinary `EvidenceVerifier` execution receives and records a control raw receipt that fails the existing physical-cleanup confirmation predicate, it breaks before invoking the adversarial role. The control raw reference remains in the committed evidence bundle; the existing completion default retains an `ERROR`, `target_executed=False`, `role was not executed` adversarial observation and a `None` adversarial raw reference. Aggregate cleanup remains false. The existing policy returns `INCONCLUSIVE` with `ERROR` status and `container cleanup was not independently confirmed`.

`tests/unit/test_evidence.py` now has a configurable fake-sandbox cleanup flag and a focused regression. It verifies one sandbox call, the retained unconfirmed control receipt, no adversarial receipt, the existing unexecuted adversarial observation, false overall cleanup, and the conservative policy result. The existing confirmed-cleanup paired-probe test still verifies two calls, so valid normal probes are not skipped.

## Actual focused commands and results

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_evidence.py -q
```

Passed: `8 passed in 0.62s`.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

Passed: Ruff lint/format and ty all passed. `git diff --check` passed. No commit, push, merge, Git configuration change, installation, service call, Docker call, or model call was performed.

## Parent-required gates and limits

This is fake-sandbox-only validation, not native qualification. Parent must run the appropriate real-Docker cleanup regression and affected native/Temporal/replay suites, then the required full quality/package gates including fresh wheel build and installed-package resource loading. Live-provider evaluation, full CI/platform qualification, and any release/publication gates are unrun. The focused fake result does not establish physical Docker cleanup integrity, exactly-once behavior, host-loss continuation, hostile-source observation integrity, or production readiness.

The active implementation record is [PLAN-0118](../plans/PLAN-0118-cleanup-fail-closed.md).

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **152 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The packaged risk digest changes capability identity, and v2 execution intents bind that digest. Existing v1 claims remain retained and mismatched reconciliation is explicit, not silently migrated. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-cleanup-fail-closed-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
