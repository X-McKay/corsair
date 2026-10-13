# Real pytest output on CPython 3.7

Recorded 2026-10-13 for [SPEC-0046](../../../docs/development/specs/SPEC-0046-cpython37-toolchain.md) in a `docker.io/library/python@sha256:b53f496c…` container (CPython 3.7.17) with no network, one fresh container per pytest version, each version installed from hash-checked PyPI wheels with its own resolved dependencies (pytest 6.0.2 with pluggy 0.13.1; 6.2.5 to 7.4.4 with pluggy 1.2.0). Files are the unedited stdout of the operator commands used by the runner, with `/usr/local/bin/python3.7` in place of the 3.12 interpreter in the E2E-0 prefix (`evals/fixture_e2e/sandbox.py`), run in `/w`:

- `*-collect.txt`: the prefix plus `--collect-only -q tests/test_case.py`.
- `*-junit.xml`: the runner's wrapper output (JUnit only) for `--tb=native` and the two ids below.
- `*-baseline.txt`: the prefix plus `-q tests/test_case.py::test_control`.

The project had two files. `target.py`:

```python
import os


def read(root, name, error=None):
    if error == 'reject':
        raise ValueError('outside')
    with open(os.path.join(root, name)) as stream:
        return stream.read()
```

`tests/test_case.py`:

```python
import pytest

import target


def test_control(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    assert target.read(str(tmp_path), "a.txt") == "a"


class TestSecurity:
    def test_security(self, tmp_path):
        (tmp_path / "outside.txt").write_text("x")
        assert target.read(str(tmp_path), "outside.txt") == "never"
```

The same runs with the witness probe injected exited the same way and wrote a record naming the runtime as unsupported; those records carry the probe digest of the time and are not kept here (`tests/unit/test_witness.py` checks the behavior directly). pytest 4.6.11 and 5.4.3 were recorded too and exit 4 on the prefix's `--import-mode=importlib`, so they are not part of the qualified range.
