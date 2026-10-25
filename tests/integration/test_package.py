"""The installed wheel, not checkout-relative files, is the deployment artifact."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_built_wheel_includes_agent_metadata_instructions_and_risk(tmp_path):
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path / "dist")],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert not any(name.startswith("tests/") for name in archive.namelist())
    installed = tmp_path / "installed"
    subprocess.run(
        ["uv", "venv", str(installed), "--python", sys.executable],
        check=True,
        capture_output=True,
        text=True,
    )
    python = installed / "bin/python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    child = subprocess.run(
        [
            str(python),
            "-c",
            """
from importlib.resources import files
from pathlib import Path
import corsair
from corsair.runtime.client import connect, wait_for_result
from corsair.runtime.models import load_agent_spec, prompt_text
from corsair.runtime.terminal import Terminal
from corsair.observability.logging import LifecycleLoggingInterceptor
from corsair.cli import parser
assert Path(corsair.__file__).is_relative_to(Path('installed').resolve()), corsair.__file__
for role in ('producer', 'auditor'):
    assert load_agent_spec(role).name == role
    assert len(prompt_text(role)) > 100
assert 'pilot risk' in files('corsair.runtime').joinpath('risk.md').read_text().lower()
assert files('corsair.tools.security').joinpath('driver.py').is_file()
assert parser().parse_args(['report', 'report.json']).command == 'report'
print('Installed-wheel resources verified outside checkout')
""",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert "Installed-wheel resources" in child.stdout
    console = subprocess.run(
        [str(installed / "bin/corsair"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert console.returncode == 0, console.stdout + console.stderr
    assert "investigate" in console.stdout
    assert "doctor" in console.stdout and "--format" in console.stdout
    report = tmp_path / "report.json"
    report.write_text('{"summary": {"attempts": 1, "passed": 1}}')
    command = subprocess.run(
        [str(installed / "bin/corsair"), "report", str(report), "--format", "json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert command.returncode == 0, command.stderr
    assert '"passed": 1' in command.stdout
    assert "\x1b" not in command.stdout
