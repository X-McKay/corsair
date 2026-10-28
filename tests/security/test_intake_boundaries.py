"""Inspection reads text only and rejects paths outside its admitted mount."""

import pytest

from corsair.adapters.sandboxing.inspection_reader import inspect_source


def test_inspection_never_imports_target_and_bounds_output(tmp_path):
    (tmp_path / "bad.py").write_text('raise RuntimeError("must never execute")')
    response = inspect_source(tmp_path, "read", "bad.py", 1024)
    assert "raise RuntimeError" in response["content"]
    with pytest.raises(ValueError):
        inspect_source(tmp_path, "read", "../outside", 1024)
    with pytest.raises(ValueError):
        inspect_source(tmp_path, "read", "bad.py", 4)


def test_inspection_rejects_symlink(tmp_path):
    (tmp_path / "target").write_text("text")
    (tmp_path / "link").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError):
        inspect_source(tmp_path, "read", "link", 1024)
