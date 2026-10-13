"""E2E-0 over the plain Docker route with a fake docker CLI: each runner call is a fresh offline container."""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from contextlib import ExitStack
from uuid import uuid4

import pytest
from pydantic_ai import models

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.test_runner import ApprovedPatch, PatchFile
from evals.fixture_e2e import docker as route
from evals.fixture_e2e import run as cli
from evals.fixture_e2e.case import FIXTURE
from evals.fixture_e2e.sandbox import DISCOVER, PYTHON

IMAGE = "sha256:" + "a" * 64
CONTROL = "test_documents.py::test_benign_control"
SECURITY = "test_documents.py::test_security_rejects_outside_read"


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


class FakeDocker:
    """Test-only docker CLI: a container is a private directory standing in for its /tmp, with its read-only /src
    mount; commands run locally with those paths and the image's interpreter localized."""
    def __init__(self, root: Path):
        self.root, self.containers, self.runs, self.removed = root, {}, [], []

    def _local(self, container, text):
        tmp, src = self.containers[container]
        return re.sub(r"(?<![\w/])/src\b", str(src), text.replace("/tmp/", f"{tmp}/").replace(PYTHON, sys.executable))

    def __call__(self, *args, stdin=None, timeout=900):
        def done(code=0, out=b"", err=b""):
            return subprocess.CompletedProcess(args, code, out, err)
        match args:
            case ("run", "-d", *flags, image, "/bin/sleep", "infinity"):
                self.runs.append(flags)
                container = f"c{len(self.containers)}"
                source = next(v.split(":")[0] for f, v in zip(flags, flags[1:]) if f == "-v" and v.endswith(":/src:ro"))
                (self.root / container).mkdir()
                self.containers[container] = (self.root / container, Path(source))
                return done(out=container.encode())
            case ("exec", "-i", container, *argv):
                local = [self._local(container, token) for token in argv]
                return subprocess.run(local, input=stdin, capture_output=True, timeout=timeout)
            case ("exec", "-w", work, container, *argv):
                local = [self._local(container, token) for token in argv]
                return subprocess.run(local, cwd=self._local(container, work), capture_output=True, timeout=timeout,
                                      env={"PATH": os.environ["PATH"]})
            case ("exec", container, *argv):
                return subprocess.run([self._local(container, token) for token in argv], capture_output=True,
                                      timeout=timeout)
            case ("rm", "--force", container):
                self.removed.append(container)
                return done()
            case ("inspect", container):
                return done(1, err=b"Error: No such object: " + container.encode())
        raise AssertionError(f"unexpected docker call {args}")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    (tmp_path / "containers").mkdir()
    docker = FakeDocker(tmp_path / "containers")
    monkeypatch.setattr(route, "docker", docker)
    return docker


def test_a_live_authors_own_test_runs_in_an_offline_container_never_on_the_host(tmp_path, fake):
    reviewed = (FIXTURE / "test_documents.py").read_bytes()
    # The planned ids with other bytes: the reviewed host workspace refuses this patch before any interpreter.
    authored = reviewed + b"\n# Authored by the model, not the reviewed SPEC-0018 bytes.\n"
    patch = ApprovedPatch((PatchFile("test_documents.py", authored),), ("test_documents.py",))
    (tmp_path / "objects").mkdir(mode=0o700)
    with ExitStack() as stack, LocalArtifacts(tmp_path / "objects", max_bytes=1 << 20) as store:
        (tmp_path / "route").mkdir()
        runners = route.docker_runners(IMAGE, tmp_path / "route", store, stack, 60)
        observed = runners("development").run(patch, control_test_id=CONTROL, security_test_id=SECURITY,
                                              discovery_command=DISCOVER, operation=uuid4())
    assert observed.failure_layer is None and observed.cleanup == "confirmed"
    assert {c.test_id: c.outcome for c in observed.execution.cases} == {CONTROL: "passed", SECURITY: "failed"}
    (flags,) = fake.runs
    assert "--network=none" in flags and "--cap-drop=ALL" in flags and "--security-opt=no-new-privileges" in flags
    assert IMAGE not in flags and fake.removed == ["c0"]  # The container is removed when the stack closes
    assert observed.workspace.source.sha256 == route._digest(route.source_label("vulnerable"))


def test_the_docker_route_runs_every_stage_and_records_itself_unqualified(tmp_path, fake):
    evidence = tmp_path / "run"
    result = asyncio.run(cli.docker_async(evidence, (), None, IMAGE, timeout=60))
    # Every stage ran; the gate's verdict needs the real /tmp/work failure locations, so the real Docker check
    # (PLAN-0081) shows it, not this fake.
    assert result.stopped_at is None and result.reason == "complete" and result.assessment is not None
    assert [w.reason for w in result.witnesses] == ["admitted", "admitted"]
    assert len(fake.runs) == 3 and all("--network=none" in flags for flags in fake.runs)
    assert sorted(fake.removed) == ["c0", "c1", "c2"]
    configuration = json.loads((evidence / "configuration.json").read_text())
    recorded = json.loads((evidence / "result.json").read_text())
    for runner in (configuration["runner"], recorded["runner"]):
        assert runner["route"] == "docker" and runner["qualification"] == "unqualified"
        assert runner["image_row"] == "cpython-3.12-pytest" and runner["image"] == IMAGE
    assert configuration["environment_identity"]["policy_revision"] == "docker-offline-cap-drop-all"


def test_the_docker_route_needs_the_rows_local_image(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CORSAIR_IMAGES", raising=False)
    argv = ["run", "--evidence", str(tmp_path / "e"), "--sandbox", "docker"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        cli.main()
    assert "needs --images or CORSAIR_IMAGES" in capsys.readouterr().err
    other = tmp_path / "images.json"
    other.write_text(json.dumps({"temurin-17-maven": IMAGE}))
    monkeypatch.setattr(sys, "argv", argv + ["--images", str(other)])
    with pytest.raises(SystemExit):
        cli.main()
    assert "needs a cpython-3.12-pytest entry" in capsys.readouterr().err
    assert not (tmp_path / "e").exists()
