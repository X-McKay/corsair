import os
from pathlib import Path


def test_canary():
    Path(os.environ["CORSAIR_MARKER_DIR"], "start").write_text("start")
    total = 1 + 1
    assert total == 3, os.environ["CORSAIR_TOKEN"]
    Path(os.environ["CORSAIR_MARKER_DIR"], "end").write_text("end")
