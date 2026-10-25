---
id: PLAN-0121
kind: plan
title: Eval CLI repeat and concurrency parser bounds
status: implemented
updated: 2026-10-25
---

# Eval CLI parser bounds

## Goal

Reject `corsair eval --repeats` and `--concurrency` values outside 1 through 8 during native `argparse` admission, before settings, artifact-store, dataset, or command-handler I/O.

## Bounded scope and decisions

- Added `choices=range(1, 9)` to both eval options in `corsair.entrypoints.cli.parser`.
- Retained the existing defaults (`repeats=1`, `concurrency=2`) and canonical `BatchRequest` Pydantic `ge=1, le=8` bounds. Direct Python API construction therefore retains its existing validation behavior.
- Added parser coverage for both allowed endpoints and all four out-of-bound option/value combinations.
- Added an executable-console regression that supplies absent dataset/settings paths with invalid values. It receives argparse exit status 2, writes no stdout, reports the invalid choice, does not emit the handler failure event, and does not create either runtime path.
- No parser framework, handler, settings, storage, dataset, workflow, or runtime-resource behavior changed.

## Focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/unit/test_cli_arguments.py tests/integration/test_cli.py::test_real_cli_rejects_eval_bounds_before_handler_io
```

Passed: **12 tests in 5.82s**. The unit cases accept 1 and 8 for each option and reject 0 and 9; the integration cases invoke the installed `corsair` console script with the worktree source on `PYTHONPATH`.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/entrypoints/cli.py tests/unit/test_cli_arguments.py tests/integration/test_cli.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/entrypoints/cli.py tests/unit/test_cli_arguments.py tests/integration/test_cli.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
```

Passed: all three changed Python files are formatted, Ruff reported no findings, and `ty` reported all checks passed. `git diff --check` also passed.

## Corrections retained in the record

The first combined focused pytest selection exposed pytest's flat import collision between a new unit module named `test_cli.py` and the existing integration module of that name. The unit module was renamed to `test_cli_arguments.py`. The first console assertion omitted argparse's quotation marks around an invalid token; it was corrected to the native diagnostic before the final passing run. These were test-structure/assertion corrections only.

## Unrun gates and blockers

This bounded change did not run the real Docker/Temporal batch, real worker/doctor/reference CLI suite, live-provider isolated-agent diagnostics, full suite, wheel build/install-and-load-from-outside-checkout, or CI. The focused console process validates parser admission only; it is not native workflow, live-model, package, or full qualification. Parent-owned qualification must run and record those gates separately.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 162 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
