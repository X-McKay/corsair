"""Behavior checks for the maintained local documentation checker."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_docs.py"


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Execute the independent documentation checker against a temporary repository."""

    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        check=False,
    )


def test_docs_checker_accepts_existing_local_link_and_heading_anchor(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Project\n\n[Guide](docs/guide.md#use-it)\n")
    (tmp_path / "docs/guide.md").write_text("# Guide\n\n## Use it\n")

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_docs_checker_reports_missing_local_target(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Project\n\n[Missing](docs/missing.md)\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "README.md: docs/missing.md: missing target" in result.stderr


def test_docs_checker_reports_missing_heading_anchor(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Project\n\n[Guide](guide.md#not-here)\n")
    (tmp_path / "guide.md").write_text("# Guide\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "README.md: guide.md#not-here: missing anchor" in result.stderr
