"""The gym runner under a real ephemeral Temporal server and real Docker, scripted inference.

This is not a live-model result: the scripted ADK model supplies a frozen proposal while
the production worker composition, workflows, source admission, content-tagged image and
sandbox execute. It proves the runner's lifecycle and records, not model accuracy.
"""

import os
import socket
from pathlib import Path

import pytest
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError

from corsair.adapters.inference.adk import AdkInference
from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.adapters.temporal.client import wait_for_result
from corsair.entrypoints import gym
from corsair.evaluation.comparison import read_report
from corsair.evaluation.gym.scoring import (
    REPORT_FILE,
    SCORECARD_FILE,
    TRAJECTORIES_FILE,
    read_scorecard,
    read_trajectories,
)
from corsair.settings import Settings
from corsair.steps.activities import Activities
from tests.integration.test_chain import ReferenceModel

ROOT = Path(__file__).resolve().parents[2]


def _accepting(address: str) -> bool:
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio
async def test_gym_run_on_an_ephemeral_server_writes_a_scored_sliced_run(tmp_path):
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for native execution")
    if os.environ.get("CORSAIR_TEST_TEMPORAL") != "1":
        pytest.skip("set CORSAIR_TEST_TEMPORAL=1 to start a Temporal dev server")
    base = Settings(source_root=str(ROOT), artifact_root=str(tmp_path / "artifacts"))
    composed: list[Settings] = []
    seen: dict[str, object] = {}

    def compose(settings: Settings) -> Activities:
        composed.append(settings)
        store = ArtifactStore(settings.artifact_root)
        return Activities(
            settings,
            store=store,
            inference=AdkInference(settings, store, ReferenceModel(model="scripted-gym")),
            sources=LocalSourceSnapshots(settings, store),
            sandbox=DockerSandbox(settings, store=store),
        )

    async def observe(handle):
        settings = composed[0]
        seen["address_during_run"] = _accepting(settings.temporal_address)
        client = await Client.connect(
            settings.temporal_address,
            namespace="corsair-gym",
            data_converter=pydantic_data_converter,
        )
        description = await client.get_workflow_handle(handle.id).describe()
        seen["task_queue"] = description.task_queue
        default = await Client.connect(settings.temporal_address, namespace="default")
        with pytest.raises(RPCError):
            await default.get_workflow_handle(handle.id).describe()
        return await wait_for_result(handle)

    out = tmp_path / "run"
    run = await gym.run_gym(
        gym.GymOptions(
            dataset=ROOT / "evals/datasets/dev.json",
            settings=base,
            repeats=1,
            concurrency=1,
            cases=("case01",),
            out=out,
        ),
        root=ROOT,
        compose_activities=compose,
        observe=observe,
    )

    branch, commit = gym.git_revision(ROOT)
    queue = gym.gym_task_queue(branch, commit)
    (settings,) = composed
    assert settings.temporal_namespace == "corsair-gym"
    assert settings.task_queue == queue == seen["task_queue"]
    assert (
        settings.identity
        == gym.gym_settings(
            base, temporal_address="elsewhere:1", task_queue="q", images=settings.images
        ).identity
    )
    assert seen["address_during_run"] is True
    assert run.ephemeral and run.temporal_address == settings.temporal_address
    assert not _accepting(run.temporal_address), "the ephemeral server must be stopped"

    assert run.run_dir == out
    for name in (REPORT_FILE, TRAJECTORIES_FILE, SCORECARD_FILE):
        assert (out / name).is_file()
    report = read_report(out / REPORT_FILE)
    assert [row["case_id"] for row in report["rows"]] == ["case01"]
    assert report["rows"][0]["status"] == "pass", report["rows"][0]
    (trajectory,) = read_trajectories(out / TRAJECTORIES_FILE)
    assert trajectory.verified and trajectory.git_commit == commit
    card = read_scorecard(out / SCORECARD_FILE)
    assert card.sliced is True
    assert card.run.temporal_namespace == "corsair-gym"
    assert card.run.task_queue == queue
    assert (card.run.git_branch, card.run.git_commit, card.run.concurrency) == (branch, commit, 1)
    python_image = f"corsair-python:{gym.image_tag(ROOT, 'python')}"
    assert settings.image_for("python.secret_disclosure/1") == python_image
    assert list(card.run.image_ids) == [python_image]
    assert card.run.image_ids[python_image].startswith("sha256:")
    assert card.identity_digests == [settings.identity]


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
async def test_an_existing_server_without_the_gym_namespace_is_refused(temporal_server, tmp_path):
    address = temporal_server.client.service_client.config.target_host
    out = tmp_path / "never"
    with pytest.raises(gym.GymRefused, match="no namespace corsair-gym"):
        await gym.run_gym(
            gym.GymOptions(
                dataset=ROOT / "evals/datasets/gym-tier0.json",
                settings=Settings(artifact_root=str(tmp_path / "artifacts")),
                temporal_address=address,
                out=out,
            ),
            root=ROOT,
        )
    assert not out.exists()
    assert not (tmp_path / "artifacts").exists()
