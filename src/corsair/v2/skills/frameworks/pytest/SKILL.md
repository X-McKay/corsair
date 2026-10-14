---
name: pytest
description: Write one Corsair probe as a single pytest test function, with the start, check and end markers and the run token.
---
# pytest probe

**File and name.** Write the planned test file (normally under `tests/`, named `test_<topic>.py`) holding exactly
one test function named as planned, e.g. `def test_name():`. It runs alone, with no project `conftest.py`, no
pytest config and no plugins, from the repository root with `.` on `sys.path`: import production code by its
module path from the root and define any fixture you need in the same file. `@pytest.mark.parametrize` on the one
function is allowed.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the test body
writes a file named `start` there. Immediately before the main assertion it writes `check`, containing `safe` if
the asserted condition holds and `unsafe` if not, computed from the same variable the assertion checks. The last
statement, after every assertion, writes `end`:

```python
import os
from pathlib import Path

def test_name():
    Path(os.environ["CORSAIR_MARKER_DIR"], "start").write_text("start")
    result = target(benign_or_adversarial_input)
    holds = property_holds(result)
    Path(os.environ["CORSAIR_MARKER_DIR"], "check").write_text("safe" if holds else "unsafe")
    assert holds, os.environ["CORSAIR_TOKEN"]
    Path(os.environ["CORSAIR_MARKER_DIR"], "end").write_text("end")
```

**Token.** In both probes, the main assertion's failure message is exactly `os.environ["CORSAIR_TOKEN"]`. Never
print or log the token anywhere else.

**Pitfalls.** Do not catch `AssertionError` (no bare `except:` or `pytest.raises(AssertionError)` around the
assertion); do not use `xfail`, `skip` or `pytest.fail` to steer the outcome; do not write `end` before or inside a
branch that skips assertions; keep exactly one `test_` function in the file (helpers must not start with `test`).
