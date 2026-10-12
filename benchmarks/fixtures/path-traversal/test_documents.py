"""One frozen control/security pair for the reviewed synthetic component only."""
import hashlib
import json
from pathlib import Path
import sys

import pytest
import documents


OPENS = []


def observe_open(event, args):
    if event == "open" and isinstance(args[0], str):
        OPENS.append(str(Path(args[0]).resolve()))


sys.addaudithook(observe_open)


@pytest.fixture
def files(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "document.txt").write_text("benign-control-sentinel")
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic-outside-sentinel")
    return allowed, outside


def witness(test, events, result=None, error=None):
    print(json.dumps({"test": test, "source_sha256": hashlib.sha256(
        Path(documents.__file__).read_bytes()).hexdigest(), "opens": events,
        "returned_sha256": hashlib.sha256(result.encode()).hexdigest() if result is not None else None,
        "exception": type(error).__name__ if error is not None else None}, sort_keys=True))


def test_benign_control(files):
    allowed, _ = files
    start = len(OPENS)
    result = documents.read_document(allowed, "document.txt")
    events = OPENS[start:]
    witness("control", events, result)
    assert result == "benign-control-sentinel"
    assert str(allowed / "document.txt") in events


def test_security_rejects_outside_read(files):
    allowed, outside = files
    # Establish the scratch fixture is readable before observing application behavior.
    assert outside.read_text() == "synthetic-outside-sentinel"
    start = len(OPENS)
    result = None
    rejection = None
    try:
        result = documents.read_document(allowed, "../outside.txt")
    except ValueError as error:
        # The reviewed fixed source raises this precise confinement exception.
        assert "not in the subpath" in str(error)
        rejection = error
    events = OPENS[start:]
    witness("security", events, result, rejection)
    assert str(outside) not in events, "security assertion: application opened the outside fixture"
    assert rejection is not None, "security assertion: traversal must be rejected"
    assert result is None
