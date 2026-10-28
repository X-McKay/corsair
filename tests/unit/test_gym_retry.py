"""A gym run retries an operationally stopped episode once and scores the retry.

The runner's services (images, Temporal, the batch) are stubs that commit scripted results
to the run's store under the child run ids the evaluation workflow assigns, so these tests
prove the run path's retry rule and records; tests/integration/test_gym_runner.py runs the
same path on a real ephemeral Temporal server.
"""

import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    BatchItem,
    BatchRequest,
    Disposition,
    ExecutionStatus,
    InvestigationResult,
    OperationalReason,
    RetriedEpisode,
    Scorecard,
    Trajectory,
    Verdict,
    validate_root_identity,
)
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.render import render_scorecard
from corsair.evaluation.gym.scoring import (
    REPORT_FILE,
    SCORECARD_FILE,
    TRAJECTORIES_FILE,
    read_scorecard,
    read_trajectories,
)
from corsair.settings import Settings
from tests.unit.evaluation.test_gym_capture import CASE, _evals_root, _result
from tests.unit.test_evidence import _prepared

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "gym-retry-20261028t020826-1c30ba"
HEARTBEAT = "evidence: activity Heartbeat timeout"

# What a scripted episode returns: a verified result, a rejected (behavioural) one, a
# heartbeat timeout, or no result at all (a lost child workflow).
type Outcome = str


def _heartbeat(store: ArtifactStore, run_id: str) -> None:
    """The workflow's terminal result after a Temporal heartbeat timeout of the evidence."""
    result = InvestigationResult(
        run_id=run_id,
        case_id=CASE,
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.ERROR,
        execution_status=ExecutionStatus.ERROR,
        reason=HEARTBEAT,
        manifest=_prepared().manifest,
    )
    store.commit(f"result.{run_id}", store.put_json(result))


def _verified_rows(scored: set[str]):
    """``score_batch`` with each ``scored`` run's row passing: the stored accepted result
    stands in for a fix-blocked demonstration, which a stub cannot build."""
    real = gym.score_batch

    def score_batch(items, store, oracles):
        return [
            {**row, "status": "pass"} if row["run_id"] in scored else row
            for row in real(items, store, oracles)
        ]

    return score_batch


def _episode(store: ArtifactStore, run_id: str, outcome: Outcome) -> BatchItem:
    if outcome == "lost":
        return BatchItem(case_id=CASE, run_id=run_id, error="child workflow lost")
    if outcome == "heartbeat":
        _heartbeat(store, run_id)
    else:
        accept = outcome == "verified"
        _result(store, run_id, AuditDecision.ACCEPT if accept else AuditDecision.REJECT)
    return BatchItem(case_id=CASE, run_id=run_id, artifact=store.reconcile(f"result.{run_id}"))


def _stub_services(monkeypatch, outcome: Callable[[str], Outcome]) -> list[BatchRequest]:
    """No image build, no Temporal: each batch commits ``outcome(child run id)``'s result
    under the ids the evaluation workflow assigns, in its receipt order."""
    batches: list[BatchRequest] = []
    verified: set[str] = set()

    @asynccontextmanager
    async def endpoint(address, log):
        del address, log
        yield "127.0.0.1:1"

    async def execute(settings, batch, compose_activities, observe):
        del compose_activities, observe
        batches.append(batch)
        store = ArtifactStore(settings.artifact_root)
        run_ids = [
            f"{batch.batch_id}.c{index}.r{repeat}"
            for index in range(len(batch.requests))
            for repeat in range(batch.repeats)
        ]
        verified.update(run_id for run_id in run_ids if outcome(run_id) == "verified")
        return [_episode(store, run_id, outcome(run_id)) for run_id in run_ids]

    monkeypatch.setattr(gym, "temporal_endpoint", endpoint)
    monkeypatch.setattr(gym, "execute_batch", execute)
    monkeypatch.setattr(gym, "score_batch", _verified_rows(verified))
    monkeypatch.setattr(
        gym, "ensure_images", lambda root, refs: dict.fromkeys(refs.values(), "sha256:" + "0" * 64)
    )
    return batches


def _scripted(first: dict[int, Outcome], retry: Outcome = "verified") -> Callable[[str], Outcome]:
    """First attempts by repeat (default verified); every retry returns ``retry``."""

    def outcome(run_id: str) -> Outcome:
        if run_id.startswith(gym.retry_batch_id(RUN_ID)):
            return retry
        return first.get(int(run_id.rpartition(".r")[2]), "verified")

    return outcome


async def _run(tmp_path: Path, *, repeats: int = 3, retry: bool = True) -> gym.GymRun:
    _, manifest, _ = _evals_root(tmp_path)
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    options = gym.GymOptions(
        dataset=manifest,
        settings=settings,
        repeats=repeats,
        concurrency=2,
        out=tmp_path / "run",
        run_id=RUN_ID,
        lock=False,
        retry=retry,
    )
    return await gym.run_gym(options, root=ROOT)


def _record(run: gym.GymRun) -> dict:
    return json.loads((run.run_dir / gym.RUN_FILE).read_text())


@pytest.mark.asyncio
async def test_an_operational_first_attempt_is_retried_once_and_its_retry_scored(
    tmp_path, monkeypatch
):
    batches = _stub_services(monkeypatch, _scripted({1: "heartbeat"}))

    run = await _run(tmp_path)

    # The run's batch, then one retry batch: the same request, one repeat, same concurrency.
    first, retry = batches
    assert retry.batch_id == f"{RUN_ID}.a2"
    assert retry.requests == first.requests and retry.repeats == 1
    assert retry.concurrency == first.concurrency == 2
    # The retry replaces repeat 1 in the scored trajectories; the others are untouched.
    assert [(item.repeat, item.attempt, item.verified) for item in run.trajectories] == [
        (0, 1, True),
        (1, 2, True),
        (2, 1, True),
    ]
    retried = run.trajectories[1]
    assert retried.run_id == f"{RUN_ID}.a2.c0.r0"
    assert retried.retried_reason is OperationalReason.HEARTBEAT_TIMEOUT
    assert retried.supersedes == f"{RUN_ID}.c0.r1"
    assert not retried.operational and retried.superseded_by is None
    card = run.scorecard
    assert card.retried_episodes == 1 and card.operational_episodes == 0
    assert card.retries == [
        RetriedEpisode(
            case_id=CASE,
            repeat=1,
            language="python",
            reason=OperationalReason.HEARTBEAT_TIMEOUT,
            run_id=f"{RUN_ID}.a2.c0.r0",
            superseded_run_id=f"{RUN_ID}.c0.r1",
        )
    ]
    assert card.languages["python"].verified_accuracy == 1.0
    # The files on disk say the same, and the first attempt is kept beside them, marked.
    assert read_trajectories(run.run_dir / TRAJECTORIES_FILE) == run.trajectories
    assert read_scorecard(run.run_dir / SCORECARD_FILE) == card
    (superseded,) = read_trajectories(run.run_dir / gym.SUPERSEDED_FILE)
    assert (superseded.run_id, superseded.repeat, superseded.attempt) == (
        f"{RUN_ID}.c0.r1",
        1,
        1,
    )
    assert superseded.operational_reason is OperationalReason.HEARTBEAT_TIMEOUT
    assert superseded.superseded_by == retried.run_id
    rows = json.loads((run.run_dir / REPORT_FILE).read_text())["rows"]
    assert [row["run_id"] for row in rows] == [
        f"{RUN_ID}.c0.r0",
        f"{RUN_ID}.a2.c0.r0",
        f"{RUN_ID}.c0.r2",
    ]
    assert {key: rows[1][key] for key in ("attempt", "retried_reason", "supersedes")} == {
        "attempt": 2,
        "retried_reason": "heartbeat_timeout",
        "supersedes": f"{RUN_ID}.c0.r1",
    }
    record = _record(run)
    assert (record["retry"], record["retried_episodes"], record["episodes"]) == (True, 1, 3)
    text = render_scorecard(card)
    assert "- Operational episodes: 0; retried: 1" in text
    assert f"- `{CASE}` repeat 1: heartbeat_timeout; retry `{RUN_ID}.a2.c0.r0`" in text


@pytest.mark.asyncio
async def test_a_rescore_keeps_the_retry_marks_of_the_report(tmp_path, monkeypatch, capsys):
    _stub_services(monkeypatch, _scripted({1: "heartbeat"}))
    run = await _run(tmp_path)
    out = tmp_path / "rescored"

    args = cli.parser().parse_args(
        ["--format", "json", "gym", "score", str(run.run_dir), "--out", str(out)],
        namespace=cli.CliArguments(),
    )
    assert await cli.execute(args, Terminal(args)) == 0
    capsys.readouterr()

    assert read_trajectories(out / TRAJECTORIES_FILE) == run.trajectories
    assert read_scorecard(out / SCORECARD_FILE).retries == run.scorecard.retries


@pytest.mark.asyncio
async def test_a_retry_that_stops_operationally_again_is_scored_and_not_retried(
    tmp_path, monkeypatch
):
    batches = _stub_services(monkeypatch, _scripted({0: "heartbeat"}, retry="lost"))

    run = await _run(tmp_path)

    assert [batch.batch_id for batch in batches] == [RUN_ID, f"{RUN_ID}.a2"]
    retried = run.trajectories[0]
    assert (retried.attempt, retried.status, retried.operational) == (2, "unavailable", True)
    assert retried.operational_reason is OperationalReason.RESULT_UNAVAILABLE
    assert retried.retried_reason is OperationalReason.HEARTBEAT_TIMEOUT
    card = run.scorecard
    assert (card.retried_episodes, card.operational_episodes) == (1, 1)
    assert [item.reason for item in card.operational_stops] == [
        OperationalReason.RESULT_UNAVAILABLE
    ]
    assert [item.reason for item in card.retries] == [OperationalReason.HEARTBEAT_TIMEOUT]


@pytest.mark.asyncio
async def test_no_retry_scores_the_first_attempts_as_before(tmp_path, monkeypatch):
    batches = _stub_services(monkeypatch, _scripted({1: "heartbeat", 2: "lost"}))

    run = await _run(tmp_path, retry=False)

    assert [batch.batch_id for batch in batches] == [RUN_ID]
    assert [item.attempt for item in run.trajectories] == [1, 1, 1]
    assert [item.operational_reason for item in run.trajectories] == [
        None,
        OperationalReason.HEARTBEAT_TIMEOUT,
        OperationalReason.RESULT_UNAVAILABLE,
    ]
    assert (run.scorecard.retried_episodes, run.scorecard.retries) == (0, [])
    assert run.scorecard.operational_episodes == 2
    assert not (run.run_dir / gym.SUPERSEDED_FILE).exists()
    record = _record(run)
    assert (record["retry"], record["retried_episodes"]) == (False, 0)
    rows = json.loads((run.run_dir / REPORT_FILE).read_text())["rows"]
    assert not any("attempt" in row for row in rows)


def test_the_cli_turns_retry_off_with_no_retry():
    arguments = ["gym", "run", "tier0"]
    assert cli.parser().parse_args(arguments).no_retry is False
    assert cli.parser().parse_args([*arguments, "--no-retry"]).no_retry is True


@pytest.mark.asyncio
async def test_verified_and_behavioural_first_attempts_are_never_retried(tmp_path, monkeypatch):
    batches = _stub_services(monkeypatch, _scripted({1: "rejected"}))

    run = await _run(tmp_path)

    assert [batch.batch_id for batch in batches] == [RUN_ID]
    assert [(item.attempt, item.operational) for item in run.trajectories] == [(1, False)] * 3
    assert not run.trajectories[1].verified, "a behavioural failure is scored, not retried"
    assert run.scorecard.retried_episodes == 0
    assert not (run.run_dir / gym.SUPERSEDED_FILE).exists()
    assert _record(run)["retried_episodes"] == 0


@pytest.mark.asyncio
async def test_replay_finds_the_scored_attempt_and_on_request_the_superseded_one(
    tmp_path, monkeypatch
):
    _stub_services(monkeypatch, _scripted({1: "heartbeat"}))
    run = await _run(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")

    scored = gym.replay_case(run.run_dir, CASE, store)
    assert [(item["repeat"], item["attempt"]) for item in scored["repeats"]] == [
        (0, 1),
        (1, 2),
        (2, 1),
    ]
    assert scored["repeats"][1]["retried_reason"] == "heartbeat_timeout"
    assert all(item["result"] == "present" for item in scored["repeats"])

    both = gym.replay_case(run.run_dir, CASE, store, superseded=True)
    first = both["repeats"][-1]
    assert (first["run_id"], first["attempt"], first["superseded_by"]) == (
        f"{RUN_ID}.c0.r1",
        1,
        f"{RUN_ID}.a2.c0.r0",
    )
    assert first["failure_stop"] == "execution_error" and first["result"] == "present"
    text = gym.render_replay(both)
    assert (
        f"### Repeat 1 · run `{RUN_ID}.a2.c0.r0` · attempt 2, retried after heartbeat_timeout "
        f"(first attempt `{RUN_ID}.c0.r1`)"
    ) in text
    assert f"### Repeat 1 · run `{RUN_ID}.c0.r1` · attempt 1, superseded by " in text
    args = cli.parser().parse_args(["gym", "replay", str(run.run_dir), "--case", CASE])
    assert args.superseded is False


def test_retry_batches_bind_each_episode_and_keep_bounded_identities():
    request = gym.pin_dataset(ROOT / "evals/datasets/gym-tier0.json").loaded[1][0]
    run_id = gym.new_run_id(Path("x" * 200 + ".json"))
    batch = BatchRequest(batch_id=run_id, requests=[request] * 64, repeats=8, concurrency=3)
    positions = list(range(0, 64 * 8, 7))

    retries = gym.retry_batches(batch, positions)

    assert [item.batch_id for item in retries] == [f"{run_id}.a2", f"{run_id}.a2.1"]
    assert [len(item.requests) for item in retries] == [64, len(positions) - 64]
    assert {(item.repeats, item.concurrency) for item in retries} == {(1, 3)}
    for item in retries:
        last = f"{item.batch_id}.c{len(item.requests) - 1}.r0"
        assert validate_root_identity(last) == last


def test_retry_marks_are_coherent_on_a_trajectory():
    fields = {
        "run_id": "run-1",
        "case_id": CASE,
        "repeat": 0,
        "kind": "python.k/1",
        "language": "python",
        "status": "fail",
        "passed": False,
        "verified": False,
        "false_label": False,
        "usage_known": False,
        "reward_verdict": -0.5,
        "reward": -0.5,
    }
    assert Trajectory.model_validate(fields).attempt == 1
    for update in (
        {"attempt": 2},
        {"retried_reason": "heartbeat_timeout"},
        {"attempt": 2, "retried_reason": "heartbeat_timeout"},
        {"superseded_by": "run-2"},
    ):
        with pytest.raises(ValueError):
            Trajectory.model_validate({**fields, **update})
    Trajectory.model_validate(
        {**fields, "attempt": 2, "retried_reason": "heartbeat_timeout", "supersedes": "run-0"}
    )
    Trajectory.model_validate(
        {
            **fields,
            "operational": True,
            "operational_reason": "heartbeat_timeout",
            "superseded_by": "run-2",
        }
    )


def test_a_scorecard_from_before_retries_reads_them_as_unknown():
    card = Scorecard.model_validate_json(
        (ROOT / "tests/unit/evaluation/scorecard-before-packet-digests.json").read_bytes()
    )
    assert (card.retried_episodes, card.retries) == (None, [])
    assert "retried: unknown" in render_scorecard(card)
