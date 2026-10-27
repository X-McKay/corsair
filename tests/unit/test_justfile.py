"""Test the actual Just runner; the labelled UV recorder observes arguments only."""

import functools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_toolchain import JUST_REMEDY, PINNED_JUST, tool_version

ROOT = Path(__file__).resolve().parents[2]


@functools.cache
def just_parse_error(binary: str) -> str | None:
    """Return Just's first error line when this binary cannot parse the justfile."""

    process = subprocess.run([binary, "--summary"], cwd=ROOT, capture_output=True, text=True)
    if process.returncode == 0:
        return None
    return (process.stderr.strip().splitlines() or [f"exit status {process.returncode}"])[0]


def just_binary() -> str:
    binary = shutil.which("just")
    assert binary is not None, f"Just is not on PATH; {JUST_REMEDY}"
    version = tool_version("just")
    error = None if version == PINNED_JUST else just_parse_error(binary)
    if error is not None:
        # Only an unpinned Just may skip: the pinned one failing to parse is a real defect.
        pytest.skip(f"just {version} cannot parse the justfile ({error}); {JUST_REMEDY}")
    return binary


def test_default_just_lists_recipes_without_running_side_effects():
    process = subprocess.run([just_binary()], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert "Available recipes" in process.stdout
    recipes = ("check", "test-all", "verify", "eval-agent", "demo", "temporal-up")
    gym = ("gym-run", "gym-gate", "gym-verify", "gym-runs", "gym-replay", "gym-capture")
    gym += ("gym-ledger", "images-gym", "gym-noise")
    datasets = ("dataset-families", "dataset-audit")
    for recipe in (*recipes, "live-agent", "live-chain", *datasets, *gym):
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
        (
            "eval-intake",
            ["data set's.json", "--output", "report $(touch SHOULD_NOT_EXIST).json"],
            ["run", "--locked", "python", "-m", "corsair.evaluation.intake"],
        ),
        (
            "live-agent",
            [
                "auditor",
                "data set's.json",
                "base $(touch SHOULD_NOT_EXIST).json",
                "--dry-run",
            ],
            ["run", "--locked", "--extra", "providers", "python", "scripts/live_eval.py", "agent"],
        ),
        (
            "live-chain",
            ["dataset; touch SHOULD_NOT_EXIST.json", "--repeats", "2", "--dry-run"],
            ["run", "--locked", "--extra", "providers", "python", "scripts/live_eval.py", "chain"],
        ),
        (
            "gym-run",
            ["tier0; touch SHOULD_NOT_EXIST", "--repeats", "3", "--case", "a b"],
            ["run", "--locked", "--extra", "providers", "corsair", "gym", "run"],
        ),
        (
            "gym-ledger",
            ["append", "--lesson", "it's $(touch SHOULD_NOT_EXIST)"],
            ["run", "--locked", "--extra", "providers", "corsair", "gym", "ledger"],
        ),
        ("images-gym", ["--settings", "a b.json"], ["run", "--locked", "corsair", "gym", "images"]),
        (
            "dataset-audit",
            ["evals/datasets/gym tier1.json", "tier2 $(touch SHOULD_NOT_EXIST).json"]
            + ["--format", "json"],
            ["run", "--locked", "corsair", "dataset", "audit"],
        ),
        ("dataset-audit", [], ["run", "--locked", "corsair", "dataset", "audit"]),
    ],
)
def test_literal_forwarding_through_real_just(tmp_path, recipe, arguments, prefix):
    assert _recorded_uv(tmp_path, recipe, arguments) == prefix + arguments
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def _recorded_uv(tmp_path: Path, recipe: str, arguments: list[str]) -> list[str]:
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
    return json.loads(result.stdout)


GYM = ["run", "--locked", "--extra", "providers", "corsair", "gym"]


@pytest.mark.parametrize(
    "recipe,arguments,expected",
    [
        (
            "gym-gate",
            ["base $(touch SHOULD_NOT_EXIST).json", "cand.json"],
            [*GYM, "gate", "--baseline", "base $(touch SHOULD_NOT_EXIST).json"]
            + ["--candidate", "cand.json"],
        ),
        (
            "gym-gate",
            ["base.json", "cand.json", "--track", "accuracy"],
            [*GYM, "gate", "--baseline", "base.json", "--candidate", "cand.json"]
            + ["--track", "accuracy"],
        ),
        (
            "gym-gate",
            ["base.json", "cand.json", "--noise", "noise $(touch SHOULD_NOT_EXIST).json"],
            [*GYM, "gate", "--baseline", "base.json", "--candidate", "cand.json"]
            + ["--noise", "noise $(touch SHOULD_NOT_EXIST).json"],
        ),
        (
            "gym-noise",
            ["run a", "run $(touch SHOULD_NOT_EXIST)", "run c", "--out", "band file.json"],
            [*GYM, "noise", "run a", "run $(touch SHOULD_NOT_EXIST)", "run c"]
            + ["--out", "band file.json"],
        ),
        ("gym-replay", ["run dir", "case01"], [*GYM, "replay", "run dir", "--case", "case01"]),
        (
            "gym-verify",
            ["ref dir", "--skip-tier1"],
            [*GYM, "verify", "--reference", "ref dir", "--skip-tier1"],
        ),
        (
            "gym-verify",
            ["ref dir", "--noise", "noise-tier0.json", "--noise", "noise-tier1.json"],
            [*GYM, "verify", "--reference", "ref dir", "--noise", "noise-tier0.json"]
            + ["--noise", "noise-tier1.json"],
        ),
        ("gym-runs", ["--tier", "tier0"], [*GYM, "runs", "--tier", "tier0"]),
        (
            "gym-capture",
            ["run dir", "case01", "--reference", "other run"],
            [*GYM, "capture", "run dir", "--case", "case01", "--reference", "other run"],
        ),
    ],
)
def test_gym_recipes_place_their_positional_arguments(tmp_path, recipe, arguments, expected):
    assert _recorded_uv(tmp_path, recipe, arguments) == expected
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_verify_requires_both_paths_before_executing():
    result = subprocess.run([just_binary(), "verify"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "argument" in result.stderr.lower()


@pytest.mark.parametrize("recipe,arguments", [("live-agent", ["auditor"]), ("live-chain", [])])
def test_live_recipes_require_their_positional_arguments(recipe, arguments):
    result = subprocess.run(
        [just_binary(), recipe, *arguments], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "argument" in result.stderr.lower()
