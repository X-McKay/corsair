"""Actual Docker inspection with native ADK; scripted model is not live accuracy."""

import json
import os
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import docker
import pytest
from docker.errors import NotFound

from corsair.adapters.inference.adk import run_intake
from corsair.adapters.sandboxing.inspection import DockerInspection
from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source
from corsair.contracts.intake import ImageInventory, IntakeRequest, JsonIssueInput, PreparedIntake
from corsair.settings import Settings
from tests.unit.adk import ScriptedLlm, text_response, tool_response
from tests.unit.test_intake_agent import proposal_dict

pytestmark = pytest.mark.docker


async def test_real_inspection_is_readonly_offline_and_cleaned():
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("explicit real-Docker opt-in required")
    shared_root = Path(__file__).resolve().parents[2] / ".work"
    shared_root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="intake-native-", dir=shared_root) as directory:
        await _inspect(Path(directory))


async def _inspect(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "reader.py").write_text('raise RuntimeError("never execute target")')
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    request = IntakeRequest(
        input=JsonIssueInput(payload=proposal_dict()["issue"]), source=Source(path=str(source))
    )
    snapshot = snapshot_source(request.source, settings, store)
    prepared = PreparedIntake(
        run_id="real-inspection",
        request=request,
        source=snapshot,
        input_artifact=store.put_json(request.input),
        payload=proposal_dict()["issue"],
        inventory=ImageInventory(),
        config_digest=settings.identity,
    )
    with closing(docker.from_env(timeout=15)) as client:
        with DockerInspection(settings, store, prepared, client) as reader:
            reader.container.reload()
            config = reader.container.attrs["HostConfig"]
            assert config["ReadonlyRootfs"] is True
            assert config["NetworkMode"] == "none"
            assert config["CapDrop"] == ["ALL"]
            assert all(
                "docker.sock" not in mount["Source"] for mount in reader.container.attrs["Mounts"]
            )
            assert "never execute target" in reader.read("read", "reader.py")["content"]
            assert "error" in reader.read("read", "../etc/passwd")
            model = ScriptedLlm(
                model="docker-intake",
                responses=[
                    tool_response("read_file", {"path": "reader.py"}),
                    text_response(json.dumps(proposal_dict())),
                ],
            )
            output = await run_intake(prepared, settings, reader, model)
            assert output.proposal is not None
            identity = reader.container_id
        with pytest.raises(NotFound):
            client.containers.get(identity)
