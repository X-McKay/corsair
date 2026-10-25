---
id: HANDOFF-recommendation-eval-report-provenance
kind: handoff
title: Evaluation report dataset provenance
status: focused_checks_passed_pending_parent_qualification
updated: 2026-10-25
---

# Handoff

Implemented the bounded [PLAN-0122](../plans/PLAN-0122-eval-report-provenance.md) change on `manus/eval-report-provenance` from base `c0bd5b9783ed00ffceea99d820fb72f2e4035117`.

## Delivered behavior

- `save_report(path, rows, dataset_digest: Digest | None = None)` writes and returns one complete report. A supplied digest is included before the only disk write.
- `corsair eval` passes `digest(dataset)` directly to the writer and no longer makes a second `write_text` call.
- `corsair rescore` retains its verified loaded `Dataset` and passes `digest(dataset)` to the writer.
- Focused tests cover the returned/on-disk report equality, exactly one writer call, both CLI consumer paths, and the existing real native CLI batch integration assertion.

Row scoring, saved native-evidence verification, frozen request/oracle bytes, and all frozen oracle contents were left unchanged. No installs, SDK/model/service calls, commits, pushes, merges, Git configuration changes, or root-worktree edits were made.

## Actual focused commands and results

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -p no:cacheprovider -q tests/unit/test_evaluation.py tests/unit/test_terminal.py
# 33 passed in 3.05s

/Users/al/git/corsair/.venv/bin/ruff check src/corsair/evaluation/scoring.py src/corsair/entrypoints/cli.py tests/unit/test_evaluation.py tests/unit/test_terminal.py tests/integration/test_chain.py
/Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/evaluation/scoring.py src/corsair/entrypoints/cli.py tests/unit/test_evaluation.py tests/unit/test_terminal.py tests/integration/test_chain.py
# All checks passed; 5 files already formatted

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
# All checks passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -p no:cacheprovider --collect-only -q tests/integration/test_chain.py
# 2 tests collected in 2.00s; no test execution or Docker, Temporal, or model call
```

The focused CLI `eval` test uses a scripted client/result seam to reach report persistence, and the rescore test uses a scripted saved-score seam. Those checks prove argument propagation and on-disk output only; they do not substitute for native service or provider qualification.

## Parent-required gates

Native Docker/Temporal integration, live-provider/isolated-agent gates, package build plus installed-wheel resource loading outside the checkout, full `just check`/suite, and exact-revision CI are unrun. In particular, the updated `test_cli_frozen_batch_uses_native_chain_and_external_oracles` requires real Docker and Temporal and has not passed on this revision. No claim of full qualification, native execution, live-model behavior, or package validity is made by this handoff.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **153 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-eval-report-provenance-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
