import os
from pathlib import Path


def test_canary():
    Path(os.environ["CORSAIR_MARKER_DIR"], "start").write_text("start")
    total = 1 + 1
    holds = total == 3
    Path(os.environ["CORSAIR_MARKER_DIR"], "check").write_text("safe" if holds else "unsafe")
    assert holds, os.environ["CORSAIR_TOKEN"]
    Path(os.environ["CORSAIR_MARKER_DIR"], "end").write_text("end")
