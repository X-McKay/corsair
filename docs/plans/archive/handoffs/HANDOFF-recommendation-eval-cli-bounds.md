---
id: HANDOFF-recommendation-eval-cli-bounds
kind: handoff
title: Eval CLI argparse bounds
status: local_focused_validation
updated: 2026-10-25
---

# Eval CLI argparse bounds handoff

Implemented the assigned parser-only change on `manus/eval-cli-bounds`: `corsair eval --repeats` and `--concurrency` now use native `argparse` `choices=range(1, 9)`. Existing defaults and the canonical `BatchRequest` Pydantic bounds are unchanged, so direct API behavior remains as before.

Added `tests/unit/test_cli_arguments.py` for both valid endpoints (1 and 8) and invalid bounds (0 and 9) on both options. Added an executable-console regression in `tests/integration/test_cli.py`; invalid input paired with absent dataset/settings paths exits from argparse with status 2, no stdout or `cli.failed` event, and creates neither path. This exercises parser admission before handler runtime I/O; it does not run a workflow.

Final focused evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/python -m pytest -q tests/unit/test_cli_arguments.py tests/integration/test_cli.py::test_real_cli_rejects_eval_bounds_before_handler_io
# 12 passed in 5.82s

PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff format --check src/corsair/entrypoints/cli.py tests/unit/test_cli_arguments.py tests/integration/test_cli.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ruff check src/corsair/entrypoints/cli.py tests/unit/test_cli_arguments.py tests/integration/test_cli.py
# 3 files already formatted; all checks passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" /Users/al/git/corsair/.venv/bin/ty check --python /Users/al/git/corsair/.venv
# All checks passed
```

The initial focused selection had a duplicate `test_cli.py` module import collision, and the initial console assertion missed argparse's quoted token; both test-only issues were fixed before the final evidence above.

Unrun: real Docker/Temporal evaluation and full CLI native suite, live-provider diagnostics, complete suite, wheel build/fresh outside-checkout resource loading, and CI. No model, Docker, Temporal, package, or live-provider qualification is claimed. Parent must perform the requested native/live/package/CI gates before publication.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **162 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-eval-cli-bounds-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
