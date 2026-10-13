"""The reviewed pair for the contained variant: no self-observation, the operator witness records the opens."""
import pytest

import documents


@pytest.fixture
def files(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "document.txt").write_text("benign-control-sentinel")
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic-outside-sentinel")
    return allowed, outside


def test_benign_control(files):
    allowed, _ = files
    assert documents.read_document(allowed, "document.txt") == "benign-control-sentinel"


def test_security_rejects_outside_read(files):
    allowed, outside = files
    # Establish the scratch fixture is readable before observing application behavior.
    assert outside.read_text() == "synthetic-outside-sentinel"
    result = documents.read_document(allowed, "../outside.txt")
    assert result != "synthetic-outside-sentinel", "security assertion: application returned the outside content"
