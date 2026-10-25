---
id: PLAN-0122
kind: plan
title: Evaluation report dataset provenance
status: implemented_pending_parent_qualification
updated: 2026-10-25
---

# Delivery scope

Add one typed optional `dataset_digest` parameter to the existing external evaluation `save_report` writer. The `eval` and `rescore` CLI handlers must retain their verified loaded `Dataset`, pass its canonical `digest(dataset)`, and persist the complete returned report in exactly one write. This change does not alter row scoring, native-evidence verification, frozen datasets, frozen oracles, workflow behavior, provider behavior, or runtime resource loading.

## Implementation

`save_report` accepts `Digest | None` and, when supplied, includes the dataset identity before its sole `Path.write_text` call. The `eval` handler no longer modifies and rewrites a saved report. The `rescore` handler now retains the loaded `Dataset` rather than discarding it, then passes its canonical digest to the same writer.

Focused unit coverage verifies that the writer returns the exact JSON persisted by its one write; both CLI handler paths persist the digest of their loaded frozen development dataset. The existing real Docker/Temporal CLI integration now also checks the on-disk report against `digest(load_dataset(...)[0])`.

## Actual focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -p no:cacheprovider -q tests/unit/test_evaluation.py tests/unit/test_terminal.py
/Users/al/git/corsair/.venv/bin/ruff check src/corsair/evaluation/scoring.py src/corsair/entrypoints/cli.py tests/unit/test_evaluation.py tests/unit/test_terminal.py tests/integration/test_chain.py
/Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/evaluation/scoring.py src/corsair/entrypoints/cli.py tests/unit/test_evaluation.py tests/unit/test_terminal.py tests/integration/test_chain.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

The focused pytest command passed **33 tests in 3.05s**. Pinned Ruff lint passed and all five edited Python files were already formatted. Pinned ty reported **All checks passed**. The `eval` consumer test uses a labelled fake Temporal client/result only to reach the handler’s report-writing boundary; it does not qualify native Temporal, Docker, ADK, or provider behavior.

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -p no:cacheprovider --collect-only -q tests/integration/test_chain.py` collected the two native integration tests in **2.00s**. Collection performed no test execution, Docker, Temporal, or model calls.

## Parent-required qualification

- Unrun: `tests/integration/test_chain.py::test_cli_frozen_batch_uses_native_chain_and_external_oracles`, which requires a real Docker daemon and Temporal server. Its added assertion is not evidence that the native chain has passed on this revision.
- Unrun: live-provider and isolated-agent evaluation gates. No model or provider calls were made.
- Unrun: package build, fresh wheel installation, and installed-resource loading outside the checkout.
- Unrun: repository-wide `just check`, full suite, and exact-revision CI. Focused Ruff and ty are not a replacement for those gates.

See the concise [handoff](../handoffs/HANDOFF-recommendation-eval-report-provenance.md) for the delivered files and parent handoff boundary.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 153 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
