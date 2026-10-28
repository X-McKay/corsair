"""The gym runner under a real ephemeral Temporal server and real Docker, scripted inference.

This is not a live-model result: the scripted ADK model supplies a frozen proposal while
the production worker composition, workflows, source admission, content-tagged image and
sandbox execute. It proves the runner's lifecycle and records, the shared run store and the
verify chain, not model accuracy. The run-lock tests need no Docker: a stub sandbox reports
itself unavailable, so the episodes end in an error while the lock serialises real runs.
"""

import asyncio
import json
import logging
import os
import socket
from collections.abc import Sequence
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
from corsair.contracts import (
    GateDecision,
    GroupSummary,
    OperationalReason,
    RunContext,
    Scorecard,
    Trajectory,
    VerifyRecord,
    digest,
)
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.comparison import read_report
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.budgets import budgets_digest, load_budgets
from corsair.evaluation.gym.noise import noise_band
from corsair.evaluation.gym.scoring import (
    REPORT_FILE,
    SCORECARD_FILE,
    TRAJECTORIES_FILE,
    build_scorecard,
    read_scorecard,
    read_trajectories,
    write_scorecard,
    write_trajectories,
)
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.settings import Settings
from corsair.steps.activities import Activities
from tests.integration.test_chain import ReferenceModel
from tests.unit.evaluation.test_gym_capture import CASE, _evals_root
from tests.unit.test_gym_pinning import _grow

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
    assert result.record.skipped == {"tier1": "rejected_at_tier0"}
    tier0, (run,) = result.record.tier0, result.runs.values()
    assert tier0 is not None and result.record.tier1 is None
    assert tier0.gate.decision is GateDecision.REJECTED, tier0.gate
    assert tier0.gate.language_deltas == {"python": 0.0}
    run_dir = run.run_dir
    assert run_dir.parent == shared / "runs"
    assert run.scorecard.repeats == 3 and run.scorecard.macro_effective_tokens
    record = json.loads((run_dir / gym.RUN_FILE).read_text())
    assert record["store"] == str(shared / "store")
    assert (run_dir / gym.BUDGETS_FILE).read_bytes() == BUDGETS.read_bytes()
    assert any((shared / "store/blobs").iterdir()) and any((shared / "store/operations").iterdir())
    verdict = VerifyRecord.model_validate_json(result.verdict_path.read_text())
    assert result.verdict_path.parent.parent == shared / "verify"
    assert verdict == result.record
    assert (verdict.decision, verdict.complete) == (GateDecision.REJECTED, False)
    assert verdict.reference == str(shared / "reference")
    assert verdict.tier0 is not None and verdict.tier1 is None
    assert verdict.tier0.reference == str(shared / "reference/tier0.json")
    assert (verdict.tier0.scorecard, verdict.tier0.run_dir) == (
        str(run_dir / SCORECARD_FILE),
        str(run_dir),
    )
    assert verdict.commit == run.scorecard.run.git_commit

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
    gates = [result.record.tier0, result.record.tier1]
    assert [item and item.gate.decision for item in gates] == [GateDecision.INCOMPARABLE] * 2
    assert result.decision is GateDecision.INCOMPARABLE and result.record.skipped == {}
    rows = gym.list_runs(shared)
    assert [row["run_dir"] for row in rows] == [
        str(run.run_dir) for run in reversed(result.runs.values())
    ]
    verdict = VerifyRecord.model_validate_json(result.verdict_path.read_text())
    assert (verdict.decision, verdict.complete) == (GateDecision.INCOMPARABLE, True)
    assert [item and item.run_dir for item in (verdict.tier0, verdict.tier1)] == [
        str(run.run_dir) for run in result.runs.values()
    ]


# The run lock: real ephemeral Temporal servers, scripted inference, no Docker


def _require_temporal() -> None:
    if os.environ.get("CORSAIR_TEST_TEMPORAL") != "1":
        pytest.skip("set CORSAIR_TEST_TEMPORAL=1 to start a Temporal dev server")


class _UnavailableSandbox:
    """Image checks pass; every role reports the sandbox unavailable (no Docker here)."""

    @property
    def image_id(self) -> str:
        return "sha256:" + "b" * 64

    def image_id_for(self, kind: str) -> str:
        del kind
        return self.image_id

    def has_unknown_operation(self, operation_id: str) -> bool:
        del operation_id
        return False

    def execute_role(self, *args, **kwargs):
        del args, kwargs
        raise SandboxUnavailable("no Docker in the run-lock test")


def _composer_without_docker(settings: Settings) -> Activities:
    store = ArtifactStore(settings.artifact_root)
    return Activities(
        settings,
        store=store,
        inference=AdkInference(settings, store, ReferenceModel(model="scripted-gym")),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_UnavailableSandbox(),
    )


def _lock_case(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Settings]:
    dataset, shared, settings = _shared_case(tmp_path, monkeypatch)
    image = "sha256:" + "b" * 64
    monkeypatch.setattr(
        gym, "ensure_images", lambda root, refs: dict.fromkeys(refs.values(), image)
    )
    monkeypatch.setattr(gym, "LOCK_POLL_SECONDS", 0.1)
    return dataset, shared, settings


def _record(run: gym.GymRun) -> dict:
    return json.loads((run.run_dir / gym.RUN_FILE).read_text())


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_second_gym_run_waits_for_the_first_and_then_proceeds(
    tmp_path, monkeypatch, caplog
):
    _require_temporal()
    caplog.set_level(logging.INFO, logger="corsair")
    dataset, shared, settings = _lock_case(tmp_path, monkeypatch)
    first_id, second_id = "gym-lock-first-20261027t010000-aaaaaa", "gym-lock-second-bbbbbb"
    first_running, finish_first = asyncio.Event(), asyncio.Event()
    second_holder: list[gym.LockHolder | None] = []

    async def hold_first(handle):
        first_running.set()
        await finish_first.wait()
        return await wait_for_result(handle)

    async def observe_second(handle):
        second_holder.append(gym.read_lock(shared))
        return await wait_for_result(handle)

    def start(run_id: str, observe) -> asyncio.Task[gym.GymRun]:
        options = gym.GymOptions(dataset=dataset, settings=settings, run_id=run_id, concurrency=1)
        return asyncio.create_task(
            gym.run_gym(
                options, root=ROOT, compose_activities=_composer_without_docker, observe=observe
            )
        )

    first = start(first_id, hold_first)
    await asyncio.wait_for(first_running.wait(), 120)
    second = start(second_id, observe_second)
    await asyncio.sleep(1.5)

    # The second run waits before writing anything or starting its Temporal server.
    assert not second.done() and second_holder == []
    assert not (shared / "runs" / second_id).exists()
    holder = gym.read_lock(shared)
    assert holder is not None and holder.run_id == first_id
    waiting = [r for r in caplog.records if r.getMessage() == "gym.lock_waiting"]
    assert waiting and {r.fields["run_id"] for r in waiting} == {first_id}

    finish_first.set()
    first_run = await asyncio.wait_for(first, 180)
    second_run = await asyncio.wait_for(second, 180)

    # Its episode stops operationally (no Docker), so its retry batch runs under the same lock.
    assert [item and item.run_id for item in second_holder] == [second_id, second_id]
    assert gym.read_lock(shared) is None, "both runs released the lock"
    first_record, second_record = _record(first_run), _record(second_run)
    assert first_record["lock"]["waited"] is False
    assert first_record["lock"]["holder_run_id"] == first_id
    lock = second_record["lock"]
    assert (lock["used"], lock["waited"], lock["holder_run_id"]) == (True, True, second_id)
    assert [item["run_id"] for item in lock["waited_for"]] == [first_id]
    assert lock["waited_for"][0]["tier"] == "capture" and lock["wait_seconds"] >= 1.5
    assert second_record["started_at"] >= first_record["completed_at"]
    assert [row["run_id"] for row in gym.list_runs(shared)] == [second_id, first_id]
    # Each run keeps the manifest it was admitted with beside run.json.
    for run, record in ((first_run, first_record), (second_run, second_record)):
        assert (run.run_dir / gym.DATASET_FILE).read_bytes() == dataset.read_bytes()
        assert record["dataset_digest"] == run.scorecard.dataset_digest
        assert (record["cases"], record["dataset_entries"]) == ([CASE], 1)
        assert record["git_commit_at_finish"] == record["git"]["commit"]


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_run_scores_the_manifest_it_ran_when_the_tier_grows_mid_run(tmp_path, monkeypatch):
    _require_temporal()
    dataset, shared, settings = _lock_case(tmp_path, monkeypatch)
    admitted = dataset.read_bytes()
    pinned = digest(load_dataset(dataset)[0])
    grown: list[str] = []

    async def grow_then_wait(handle):
        # A merge into the run's checkout replaces the tier while the episodes run.
        grown.append(_grow(dataset.parents[1], dataset))
        return await wait_for_result(handle)

    run = await gym.run_gym(
        gym.GymOptions(dataset=dataset, settings=settings, concurrency=1, lock=False),
        root=ROOT,
        compose_activities=_composer_without_docker,
        observe=grow_then_wait,
    )

    assert grown and grown[0] != pinned
    assert run.scorecard.dataset_digest == pinned
    assert {name: group.cases for name, group in run.scorecard.languages.items()} == {"python": 1}
    assert [item.case_id for item in run.trajectories] == [CASE]
    assert (run.run_dir / gym.DATASET_FILE).read_bytes() == admitted
    record = _record(run)
    assert (record["dataset_digest"], record["cases"]) == (pinned, [CASE])
    assert read_report(run.run_dir / REPORT_FILE)["dataset_digest"] == pinned


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_verify_holds_the_lock_across_both_tiers(tmp_path, monkeypatch):
    _require_temporal()
    dataset, shared, settings = _lock_case(tmp_path, monkeypatch)
    for tier in gym.VERIFY_TIERS:
        _reference(shared / "reference" / f"{tier}.json", dataset, objective_j=0.0, tokens=1.0)
    other_id = "gym-lock-other-cccccc"
    holders: dict[str, str | None] = {}
    other: list[asyncio.Task[gym.GymRun]] = []

    def on_gate(tier, gated, baseline, run) -> None:
        del gated, baseline, run
        holder = gym.read_lock(shared)
        holders[tier] = None if holder is None else holder.run_id
        if tier == "tier0":  # Another experimenter starts a run between the two tiers.
            options = gym.GymOptions(dataset=dataset, settings=settings, run_id=other_id)
            other.append(
                asyncio.create_task(
                    gym.run_gym(options, root=ROOT, compose_activities=_composer_without_docker)
                )
            )
        else:
            assert not other[0].done(), "the other run must not run between verify's tiers"

    result = await gym.verify_candidate(
        gym.GymOptions(dataset=dataset, settings=settings, repeats=1, concurrency=1),
        shared / "reference",
        root=ROOT,
        tiers={"tier0": dataset, "tier1": dataset},
        compose_activities=_composer_without_docker,
        on_gate=on_gate,
    )
    verify_id = result.verdict_path.parent.name
    other_run = await asyncio.wait_for(other[0], 180)

    assert set(result.runs) == {"tier0", "tier1"}
    assert holders == {"tier0": verify_id, "tier1": verify_id}
    tier0, tier1 = (_record(run) for run in result.runs.values())
    assert tier0["lock"]["holder_run_id"] == tier1["lock"]["holder_run_id"] == verify_id
    assert tier1["lock"]["waited"] is False and tier1["lock"]["wait_seconds"] == 0.0
    waited = _record(other_run)["lock"]
    assert waited["waited"] is True
    assert [(item["run_id"], item["tier"]) for item in waited["waited_for"]] == [
        (verify_id, "tier0+tier1")
    ]
    assert _record(other_run)["started_at"] >= tier1["completed_at"]
    assert gym.read_lock(shared) is None


@pytest.mark.temporal
@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [True, False])
async def test_an_operational_episode_is_retried_once_on_a_real_server(
    tmp_path, monkeypatch, retry
):
    _require_temporal()
    dataset, shared, settings = _lock_case(tmp_path, monkeypatch)
    run_id = "gym-retry-20261028t020826-1c30ba"
    submitted: list[str] = []

    async def observe(handle):
        submitted.append(handle.id)
        return await wait_for_result(handle)

    run = await gym.run_gym(
        gym.GymOptions(
            dataset=dataset, settings=settings, run_id=run_id, concurrency=1, retry=retry
        ),
        root=ROOT,
        compose_activities=_composer_without_docker,
        observe=observe,
    )

    # Every role reports the sandbox unavailable, so each attempt is a sandbox fault; the
    # retry is the same request under a fresh child id and, operational again, is scored.
    (scored,) = run.trajectories
    assert scored.operational_reason is OperationalReason.SANDBOX_FAULT
    record = _record(run)
    assert (record["retry"], record["episodes"]) == (retry, 1)
    assert gym.read_lock(shared) is None
    if not retry:
        assert submitted == [run_id]
        assert (scored.run_id, scored.attempt) == (f"{run_id}.c0.r0", 1)
        assert (run.scorecard.retried_episodes, record["retried_episodes"]) == (0, 0)
        assert not (run.run_dir / gym.SUPERSEDED_FILE).exists()
        return
    assert submitted == [run_id, f"{run_id}.a2"]
    assert (scored.run_id, scored.attempt, scored.supersedes) == (
        f"{run_id}.a2.c0.r0",
        2,
        f"{run_id}.c0.r0",
    )
    assert scored.retried_reason is OperationalReason.SANDBOX_FAULT
    (first,) = read_trajectories(run.run_dir / gym.SUPERSEDED_FILE)
    assert (first.run_id, first.superseded_by) == (f"{run_id}.c0.r0", scored.run_id)
    assert (run.scorecard.retried_episodes, run.scorecard.operational_episodes) == (1, 1)
    assert [(item.repeat, item.reason) for item in run.scorecard.retries] == [
        (0, OperationalReason.SANDBOX_FAULT)
    ]
    assert record["retried_episodes"] == 1
    # Both attempts' results are in the store; replay shows the scored one, then on request
    # the superseded one.
    store = ArtifactStore(record["store"])
    view = gym.replay_case(run.run_dir, CASE, store, superseded=True)
    assert [(item["run_id"], item["attempt"], item["result"]) for item in view["repeats"]] == [
        (f"{run_id}.a2.c0.r0", 2, "present"),
        (f"{run_id}.c0.r0", 1, "present"),
    ]


# The confirmation stage: real ephemeral Temporal servers, scripted inference, no Docker


def _metered_without_docker(settings: Settings) -> Activities:
    """The run-lock composition with token usage reported, so the gate can compare runs."""
    store = ArtifactStore(settings.artifact_root)
    return Activities(
        settings,
        store=store,
        inference=AdkInference(settings, store, MeteredModel(model="scripted-gym")),
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_UnavailableSandbox(),
    )


# A failing reference episode scores as the candidate's errored episodes do, so J's band
# covers a candidate that fails every episode.
ERRORED = -0.5


def _reference_runs(
    shared: Path, dataset: Path, records: Sequence[list[bool]]
) -> tuple[list[Scorecard], list[list[Trajectory]]]:
    """Reference runs of the one-case tier, one per record of verified repeats, each with
    its trajectories under ``<shared>/runs/<run id>/``, as ``gym run`` leaves them."""
    (request,) = load_dataset(dataset)[1]
    kind = request.case.recipe.kind
    dataset_digest = digest(load_dataset(dataset)[0])
    cards, trajectories = [], []
    for index, flags in enumerate(records):
        run_id = f"gym-reference-{index}"
        rows = [
            Trajectory(
                run_id=f"{run_id}-{repeat}",
                case_id=CASE,
                repeat=repeat,
                kind=kind,
                language="python",
                status="pass" if flag else "fail",
                passed=flag,
                verified=flag,
                false_label=False,
                usage_known=True,
                effective_tokens=1e9,
                seconds=10.0,
                reward_verdict=1.0 if flag else ERRORED,
                reward=1.0 if flag else ERRORED,
            )
            for repeat, flag in enumerate(flags)
        ]
        card = build_scorecard(
            rows,
            run=RunContext(run_id=run_id, concurrency=1),
            dataset_digest=dataset_digest,
            cases={CASE: kind},
            budgets=load_budgets(BUDGETS),
        ).model_copy(update={"run_identity": {"config": ["c" * 64]}})
        write_scorecard(shared / "runs" / run_id / SCORECARD_FILE, card)
        write_trajectories(shared / "runs" / run_id / TRAJECTORIES_FILE, rows)
        cards.append(card)
        trajectories.append(rows)
    return cards, trajectories


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_verify_confirms_an_inconclusive_tier_by_its_flipped_case_under_the_same_lock(
    tmp_path, monkeypatch
):
    _require_temporal()
    dataset, shared, settings = _lock_case(tmp_path, monkeypatch)
    # The reference configuration verified the case 3, 2 and 1 times in three: pooled 6/9.
    cards, trajectories = _reference_runs(
        shared, dataset, ([True] * 3, [True, True, False], [True, False, False])
    )
    band = noise_band(cards, trajectories)
    assert band.pooled
    for tier in gym.VERIFY_TIERS:
        write_scorecard(shared / "reference" / f"{tier}.json", cards[0])

    # Every episode of the candidate errors (no sandbox): 0/3 against the pooled 6/9 is
    # within noise (p = 2/11), so each tier is INCONCLUSIVE and its case is re-run.
    result = await gym.verify_candidate(
        gym.GymOptions(dataset=dataset, settings=settings, repeats=3, concurrency=1),
        shared / "reference",
        root=ROOT,
        tiers={"tier0": dataset, "tier1": dataset},
        compose_activities=_metered_without_docker,
        noise={"noise-capture.json": band},
    )

    gates = [result.record.tier0, result.record.tier1]
    assert [item and item.gate.decision for item in gates] == [GateDecision.INCONCLUSIVE] * 2
    assert set(result.confirmation_runs) == {"tier0", "tier1"}
    verify_id = result.verdict_path.parent.name
    for tier, stage in result.record.confirmation.items():
        rerun = result.confirmation_runs[tier]
        assert (stage.cases, stage.repeats, stage.run_dir) == ([CASE], 5, str(rerun.run_dir))
        assert rerun.run_dir.parent == shared / "runs"
        # The re-run is a sliced run of the one case at five repeats, under verify's lock.
        record = _record(rerun)
        assert (record["repeats"], record["sliced"], record["cases"]) == (5, True, [CASE])
        assert record["lock"]["holder_run_id"] == verify_id
        assert record["lock"]["waited"] is False
        # 0/5 against the pooled 6/9: p = 62/2002, a regression outside noise.
        assert stage.screen is not None and stage.screen.paired is not None
        (flip,) = stage.screen.paired.pass_to_fail_cases
        assert (flip.candidate_verified, flip.candidate_episodes) == (0, 5)
        assert flip.p_value == pytest.approx(62 / 2002)
        assert (stage.decision, stage.basis) == (GateDecision.REJECTED, "regression_separated")
    assert result.decision is GateDecision.REJECTED
    verdict = VerifyRecord.model_validate_json(result.verdict_path.read_text())
    assert verdict == result.record and verdict.decision is GateDecision.REJECTED
    assert gym.read_lock(shared) is None
