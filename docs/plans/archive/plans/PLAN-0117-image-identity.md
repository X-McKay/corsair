---
id: PLAN-0117
kind: plan
title: Require matching raw Docker image identity
status: implemented_pending_parent_qualification
updated: 2026-10-25
---
# Bounded objective

Require every raw evidence receipt to contain `image_id` as a concrete string exactly equal to `prepared.manifest.image_id`. An omitted, null, non-string, or different value is invalid evidence. Existing conservative disposition policy must continue to classify such evidence as `INCONCLUSIVE`; no policy or recipe behavior changes.

## Scope and decision

The implementation is limited to `EvidenceVerifier._validate_raw` and its owning unit tests. The verifier now rejects `raw["image_id"]` unless `type(raw_image_id) is str` and its value equals the prepared manifest image identity. This preserves the raw JSON boundary's strict primitive-field semantics and closes the previous missing/null acceptance path.

The deterministic unit fixture can emit raw receipts with an omitted or controlled image identity. Regression coverage confirms that missing, null, non-string, and mismatched identities make both role observations `INVALID`, retain physical-cleanup reporting separately, produce `INCONCLUSIVE` through the existing pure `decide` policy, and cause `validate_saved` to reject persisted evidence. The existing matching-image reconciliation test retains the positive control/adversarial path.

## Actual focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/al/git/corsair/.work/recommendations-20261025/worktrees/image-identity/src:/Users/al/git/corsair/.work/recommendations-20261025/worktrees/image-identity /Users/al/git/corsair/.venv/bin/python -m pytest tests/unit/test_evidence.py tests/unit/test_evaluation.py -q
```

Passed: **25 tests in 0.46s**. This is deterministic unit coverage with a controlled sandbox double; it is not native Docker, Temporal, live-model, package, or CI qualification.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/steps/verification.py tests/unit/test_evidence.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

All three checks passed. The first formatter check identified one assertion-layout change; it was formatted before the final passing focused test and quality run.

## Explicitly unrun gates

- Native Docker integration and real sandbox image/cleanup qualification.
- Real Temporal workflow and replay qualification.
- Live ADK/provider and frozen evaluator qualification.
- Full suite, `just check`, wheel/sdist build, and installed-package resource loading.
- CI on the eventual parent publication revision.

Parent owns these remaining gates and publication. No commit, push, merge, dependency install, service call, or configuration change was performed.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 155 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
