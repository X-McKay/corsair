---
name: python-pytest
description: Write and troubleshoot Python probes under pytest and coverage.py. Use when the runtime is python / pytest.
---

# Python / pytest runtime

- `run_target(payload) -> bool` returns the same Boolean invariant through the same setup and target call for both
  payloads: `True` means preserved and `False` means the reported condition occurred. The driver assigns control
  `PASS` for true and exploit `PASS` for false; exploit `FAIL` is a clean true observation and scoped negative
  evidence. Use actual `bool` values; integers, strings and other truthy values are invalid. The probe receives no
  role or expected answer. An uncaught exception, including `AssertionError`, is `ERROR`; do not assert in the probe.
- Image: Python 3.12 with `pytest` and `coverage` installed; nothing else until your build script installs it.
- The repository root is `/work`, which is on `PYTHONPATH` when the probe runs. A top-level module `app.py` is
  `import app`; a package `src/pkg/` installed with `pip install -e .` is `import pkg`. Check with
  `bash: python -c "import <module>"` in your working sandbox first.
- The kernel writes your probe to `/work/.corsair/corsair_probe.py` and drives it with its own pytest file. Do not
  write tests yourself; do not use pytest fixtures or `conftest.py`; `run_target` must be self-contained.
- Use `tempfile.TemporaryDirectory()` for files; the probe runs without network. For a repository-local script or
  CLI, prefer `subprocess.run([sys.executable, '/work/path/to/script.py', payload], capture_output=True,
  text=True, timeout=...)`. Omit `env`, or start with a copy of `os.environ` when adding application variables.
  Preserve `PYTHONPATH`, `COVERAGE_PROCESS_START`, `COVERAGE_PROCESS_CONFIG`, `COVERAGE_FILE` and
  `COVERAGE_RCFILE`; replacing the environment and losing effective startup/configuration makes the run
  nondecisive. Coverage.py 7.13 subprocess patching may propagate `COVERAGE_PROCESS_CONFIG`, so deleting only
  `COVERAGE_PROCESS_START` does not prove coverage is absent. Wait for completion, parse only documented output,
  and recognize a fixed refusal only when it proves the shared invariant. The adapter combines parallel child data
  before rendering JSON. Importing a launcher or observing stdout alone is insufficient.
- Coverage is measured on `target_file` only, with `coverage.py`. Lines inside functions count when executed;
  module-level lines count on import. Choose `target_lines` inside the vulnerable function.
- Exploring: `bash: sed -n 1,80p path/to/file.py`, `bash: grep -rn "def read_doc" .`, `bash: python -m pytest -q`
  to see whether the project's own tests run. Keep commands short; output is truncated.
