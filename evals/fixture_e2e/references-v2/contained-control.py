"""Reviewed split-v2 benign control at the existing application seam."""
import documents

def test_benign_control(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "document.txt").write_text("benign-control-sentinel")
    assert documents.read_document(allowed, "document.txt") == "benign-control-sentinel"
