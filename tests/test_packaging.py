"""What we ship must include the agent contracts and runtime guidance."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_contains_agent_resources_and_loads_them_outside_checkout(tmp_path):
    output = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    (wheel,) = output.glob("*.whl")
    target = tmp_path / "installed"
    with zipfile.ZipFile(wheel) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for agent in ["producer", "auditor", "bug_seeder", "skill_crystallizer"]:
            assert f"corsair/agents/{agent}/agent.yaml" in names
            assert f"corsair/agents/{agent}/instructions/system.md" in names
        assert "corsair/runtime/runtime-matrix.yaml" in names
        assert len([name for name in names if name.endswith("/SKILL.md")]) == 10
        archive.extractall(target)
    program = """
from pydantic_ai.models.test import TestModel
from corsair.agents.producer.agent import build_producer
from corsair.agents.auditor.agent import build_auditor
from corsair.agents.resources import load_agent_spec, instruction, skill_names, package_resource
from corsair.runtime.matrix import load
for name in ['producer', 'auditor', 'bug_seeder', 'skill_crystallizer']:
    package = 'corsair.agents.' + name
    assert load_agent_spec(package).owner == 'X-McKay'
    assert instruction(package)
for name in skill_names('corsair.agents.producer'):
    assert package_resource('corsair.agents.producer', 'skills/' + name + '/SKILL.md').read_text().startswith('---\\n')
assert build_producer(TestModel()).name == 'producer'
assert build_auditor(TestModel()).name == 'auditor'
assert len(load()) == 7
import corsair.cli
assert corsair.cli.main(['--help']) == 0
"""
    # argparse intentionally raises SystemExit(0); the subprocess success checks that installed help works too.
    env = {**os.environ, "PYTHONPATH": str(target), "PYTHONNOUSERSITE": "1"}
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
