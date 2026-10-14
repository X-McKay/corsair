"""Pins the docker commands the Docker backend issues for replay (with and without setup network), one probe run,
one D3 check run and a sweep. ``docker_argv/golden.log`` was recorded from the code before the sandbox port
(develop at bc3c25fa) with the same fake CLI, so a diff here is a change to Docker behaviour, not a refactor."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent / "docker_argv"
ROOT = Path(__file__).parents[2]


def test_docker_backend_issues_the_pre_port_docker_commands(tmp_path):
    log = tmp_path / "docker.log"
    env = {**os.environ, "PATH": f"{HERE}{os.pathsep}{os.environ['PATH']}", "FAKE_DOCKER_LOG": str(log)}
    env.pop("CORSAIR_WORKSPACE", None)
    done = subprocess.run([sys.executable, str(HERE / "drive.py"), str(tmp_path / "work")], cwd=ROOT, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    assert log.read_text().splitlines() == (HERE / "golden.log").read_text().splitlines()
