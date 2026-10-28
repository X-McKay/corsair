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
    for recipe in ("check", "test-all", "verify", "eval-agent"):
        assert recipe in process.stdout


@pytest.mark.parametrize(
    "recipe,arguments,prefix",
    [
        (
            "eval-intake",
            ["dataset $(touch SHOULD_NOT_EXIST).json", "--settings", "settings path.json"],
            ["run", "--locked", "python", "-m", "corsair.evaluation.intake"],
        ),
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


def test_aggregate_images_includes_all_three_concrete_builds():
    result = subprocess.run(
        [just_binary(), "--dry-run", "images"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    commands = result.stderr + result.stdout
    for language in ("python", "node", "java"):
        assert f"deploy/{language}/Dockerfile" in commands


@pytest.mark.parametrize("language", ["python", "node", "java"])
def test_runtime_image_tag_is_forwarded_literally(tmp_path, language):
    (tmp_path / "justfile").write_bytes((ROOT / "justfile").read_bytes())
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    recorder = bin_path / "docker"
    recorder.write_text(f"#!{sys.executable}\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n")
    recorder.chmod(0o755)
    tag = "candidate:tag$(touch SHOULD_NOT_EXIST)"
    result = subprocess.run(
        [just_binary(), "--", f"images-{language}", tag],
        cwd=tmp_path,
        env=dict(os.environ, PATH=f"{bin_path}:{os.environ['PATH']}"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "build",
        "-f",
        f"deploy/{language}/Dockerfile",
        "-t",
        tag,
        ".",
    ]
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
