"""Test the actual Just runner; the labelled UV recorder observes arguments only."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def just_binary() -> str:
    binary = shutil.which("just")
    assert binary is not None, "Enter nix develop before running developer-task tests"
    return binary


def test_default_just_lists_recipes_without_running_side_effects():
    process = subprocess.run([just_binary()], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert "Available recipes" in process.stdout
    for recipe in ("check", "test-all", "verify", "eval-agent", "demo", "temporal-up"):
        assert recipe in process.stdout


@pytest.mark.parametrize(
    "recipe,arguments,prefix",
    [
        (
            "verify",
            [
                "request with space's.json",
                "submission $(touch SHOULD_NOT_EXIST).json",
                "--settings",
                "settings path.json",
            ],
            ["run", "--locked", "corsair", "verify"],
        ),
        (
            "eval",
            ["dataset; touch SHOULD_NOT_EXIST.json", "--repeats", "3"],
            ["run", "--locked", "--extra", "providers", "corsair", "eval"],
        ),
        (
            "eval-agent",
            ["auditor", "dataset.json", "--settings", "settings path.json"],
            [
                "run",
                "--locked",
                "--extra",
                "providers",
                "python",
                "-m",
                "corsair.evaluation.agents",
            ],
        ),
    ],
)
def test_literal_forwarding_through_real_just(tmp_path, recipe, arguments, prefix):
    # A test-only executable records argv; it does not fake provider/evidence execution.
    (tmp_path / "justfile").write_bytes((ROOT / "justfile").read_bytes())
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    recorder = bin_path / "uv"
    recorder.write_text(f"#!{sys.executable}\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n")
    recorder.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_path}:{os.environ['PATH']}")
    result = subprocess.run(
        [just_binary(), "--", recipe, *arguments],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == prefix + arguments
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_verify_requires_both_paths_before_executing():
    result = subprocess.run([just_binary(), "verify"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "argument" in result.stderr.lower()
