"""The gym runner under a real ephemeral Temporal server and real Docker, scripted inference.

This is not a live-model result: the scripted ADK model supplies a frozen proposal while
the production worker composition, workflows, source admission, content-tagged image and
sandbox execute. It proves the runner's lifecycle and records, the shared run store and the
verify chain, not model accuracy.
"""

import json
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
from corsair.contracts import GateDecision, GroupSummary, RunContext, Scorecard, digest
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.comparison import read_report
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.budgets import budgets_digest, load_budgets
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
from tests.unit.evaluation.test_gym_capture import CASE, _evals_root

ROOT = Path(__file__).resolve().parents[2]


BUDGETS = ROOT / "evals/experiments/budgets.json"


def _require_docker_and_temporal() -> None:
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for native execution")
    if os.environ.get("CORSAIR_TEST_TEMPORAL") != "1":
        pytest.skip("set CORSAIR_TEST_TEMPORAL=1 to start a Temporal dev server")


class MeteredModel(ReferenceModel):
    """The scripted reference model reporting token usage on every call, as a live route does."""

    async def generate_content_async(self, llm_request, stream=False):
        from google.genai import types

        async for response in super().generate_content_async(llm_request, stream):
            response.usage_metadata = types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=10
            )
            yield response


def _composer(model_type: type[ReferenceModel] = ReferenceModel):
    def compose(settings: Settings) -> Activities:
        store = ArtifactStore(settings.artifact_root)
        return Activities(
            settings,
            store=store,
            inference=AdkInference(settings, store, model_type(model="scripted-gym")),
            sources=LocalSourceSnapshots(settings, store),
            sandbox=DockerSandbox(settings, store=store),
        )

    return compose


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
    _require_docker_and_temporal()
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
            invocation=("corsair", "gym", "run", "dev", "--case", "case01"),
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

    # Settings naming an artifact root keep it as the store; run.json and budgets.json record
    # where and how the run executed.
    assert settings.artifact_root == str(tmp_path / "artifacts")
    assert (out / gym.BUDGETS_FILE).read_bytes() == BUDGETS.read_bytes()
    record = json.loads((out / gym.RUN_FILE).read_text())
    assert record["store"] == str(tmp_path / "artifacts")
    assert record["invocation"] == ["corsair", "gym", "run", "dev", "--case", "case01"]
    assert record["git"] == {"branch": branch, "commit": commit, "dirty": gym.git_dirty(ROOT)}
    assert (record["tier"], record["repeats"], record["sliced"]) == ("dev", 1, True)
    assert record["budgets"]["digest"] == card.budgets_digest
    assert record["episodes"] == 1 and record["completed_at"] >= record["started_at"]


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


def _shared_case(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Settings]:
    """A one-case manifest and a shared gym root standing in for the main checkout's."""
    _, dataset, _ = _evals_root(tmp_path)
    shared = tmp_path / "main/.runs/gym"
    monkeypatch.setattr(gym, "shared_gym_root", lambda root: shared)
    return dataset, shared, Settings(source_root=str(tmp_path))


def _reference(path: Path, dataset: Path, *, objective_j: float, tokens: float) -> None:
    """A reference scorecard over the same dataset, budgets and repeats as the candidate."""
    language = GroupSummary(cases=1, attempts=3, verified_accuracy=1.0)
    card = Scorecard(
        run=RunContext(run_id="reference"),
        dataset_digest=digest(load_dataset(dataset)[0]),
        budgets_digest=budgets_digest(load_budgets(BUDGETS)),
        repeats=3,
        sliced=False,
        kinds={},
        languages={"python": language},
        macro_verified_accuracy=1.0,
        worst_language_verified_accuracy=1.0,
        macro_reward=1.0,
        objective_j=objective_j,
        macro_effective_tokens=tokens,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card.model_dump_json(indent=2))


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio
async def test_verify_rejected_at_tier0_skips_tier1_and_keeps_the_run_in_the_shared_store(
    tmp_path, monkeypatch, capsys
):
    _require_docker_and_temporal()
    dataset, shared, settings = _shared_case(tmp_path, monkeypatch)
    for tier in gym.VERIFY_TIERS:
        _reference(shared / "reference" / f"{tier}.json", dataset, objective_j=9.0, tokens=1.0)

    result = await gym.verify_candidate(
        gym.GymOptions(dataset=dataset, settings=settings, repeats=3, concurrency=3),
        shared / "reference",
        root=ROOT,
        tiers={"tier0": dataset, "tier1": dataset},
        compose_activities=_composer(MeteredModel),
    )

    assert result.decision is GateDecision.REJECTED
    assert result.skipped == {"tier1": "rejected_at_tier0"}
    (tier0,) = result.gates
    assert tier0.verdict.decision is GateDecision.REJECTED, tier0.verdict
    assert tier0.verdict.language_deltas == {"python": 0.0}
    run_dir = tier0.run.run_dir
    assert run_dir.parent == shared / "runs"
    assert tier0.run.scorecard.repeats == 3 and tier0.run.scorecard.macro_effective_tokens
    record = json.loads((run_dir / gym.RUN_FILE).read_text())
    assert record["store"] == str(shared / "store")
    assert (run_dir / gym.BUDGETS_FILE).read_bytes() == BUDGETS.read_bytes()
    assert any((shared / "store/blobs").iterdir()) and any((shared / "store/operations").iterdir())
    verdict = json.loads(result.verdict_path.read_text())
    assert result.verdict_path.parent.parent == shared / "verify"
    assert verdict["decision"] == "REJECTED" and len(verdict["tiers"]) == 1

    (row,) = gym.list_runs(shared)
    assert (row["run_id"], row["tier"], row["repeats"]) == (run_dir.name, "capture", 3)

    # Any checkout reads the run back through the store its run.json names.
    args = cli.parser().parse_args(
        ["--format", "json", "gym", "replay", str(run_dir), "--case", CASE],
        namespace=cli.CliArguments(),
    )
    assert await cli.execute(args, Terminal(args)) == 0
    view = json.loads(capsys.readouterr().out)
    assert [repeat["result"] for repeat in view["repeats"]] == ["present"] * 3


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio
async def test_verify_runs_tier1_when_tier0_is_not_rejected(tmp_path, monkeypatch):
    _require_docker_and_temporal()
    dataset, shared, settings = _shared_case(tmp_path, monkeypatch)
    for tier in gym.VERIFY_TIERS:
        _reference(shared / "reference" / f"{tier}.json", dataset, objective_j=0.0, tokens=1.0)

    result = await gym.verify_candidate(
        gym.GymOptions(dataset=dataset, settings=settings, repeats=1, concurrency=1),
        shared / "reference",
        root=ROOT,
        tiers={"tier0": dataset, "tier1": dataset},
        compose_activities=_composer(),
    )

    # One repeat is below the gate's minimum, so each gate is INCOMPARABLE, never a verdict.
    assert [item.verdict.decision for item in result.gates] == [GateDecision.INCOMPARABLE] * 2
    assert result.decision is GateDecision.INCOMPARABLE and result.skipped == {}
    rows = gym.list_runs(shared)
    assert [row["run_dir"] for row in rows] == [
        str(item.run.run_dir) for item in reversed(result.gates)
    ]
    assert json.loads(result.verdict_path.read_text())["complete"] is True
