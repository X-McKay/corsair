---
id: HANDOFF-recommendation-image-identity
kind: handoff
title: Raw evidence image identity validation
status: ready_for_parent_qualification
updated: 2026-10-25
related: [PLAN-0117]
---
# Delivery record

Implemented the authorized one-condition hardening in `steps/verification.py`: raw evidence `image_id` must be a concrete `str` exactly matching `prepared.manifest.image_id`. Omitted, null, non-string, and mismatched values now yield `RoleOutcome.INVALID`; the existing pure policy returns `INCONCLUSIVE` for the resulting observation. Physical cleanup remains independently reported and is not treated as semantic validity.

`tests/unit/test_evidence.py` retains the matching-image positive path and adds deterministic regressions for all four invalid cases. Each case verifies execution-time validation, pure-policy inconclusive disposition, and saved-evidence rejection through `validate_saved`.

## Actual focused results

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/image-identity/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/image-identity /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_evidence.py tests/unit/test_evaluation.py -q
```

Passed: **25 tests in 0.46s**.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

All passed after formatting the new assertion. These are focused scripted tests, not a claim of full qualification.

## Parent-required gates

Native Docker/integration, Temporal/workflow/replay, live ADK/provider and frozen evaluation, full suite/`just check`, package build plus installed-package resource loading, and CI for the parent-published revision were not run. No commit, push, merge, installation, model call, Docker/service call, or Git configuration change occurred.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **155 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The packaged risk digest changes capability identity, and v2 execution intents bind that digest. Existing v1 claims remain retained and mismatched reconciliation is explicit, not silently migrated. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-image-identity-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
