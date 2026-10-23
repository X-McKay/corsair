---
name: python-pytest
description: Build and cover Python targets with pytest and coverage.
---
# Python / pytest runtime

- Image: Python 3.12 with `pytest` and `coverage` installed; nothing else until your build script installs it.
- The repository root is `/work`, which is on `PYTHONPATH` when the probe runs. A top-level module `app.py` is
  `import app`; a package `src/pkg/` installed with `pip install -e .` is `import pkg`. Check with
  `bash: python -c "import <module>"` in your working sandbox first.
- The kernel writes your probe to `/work/.corsair/corsair_probe.py` and drives it with its own pytest file. Do not
  write tests yourself; do not use pytest fixtures or `conftest.py`; `run_target` must be self-contained.
- Use `tempfile.TemporaryDirectory()` for files; the probe runs without network and as a single process.
- Coverage is measured on `target_file` only, with `coverage.py`. Lines inside functions count when executed;
  module-level lines count on import. Choose `target_lines` inside the vulnerable function.
- Exploring: `bash: sed -n 1,80p path/to/file.py`, `bash: grep -rn "def read_doc" .`, `bash: python -m pytest -q`
  to see whether the project's own tests run. Keep commands short; output is truncated.
