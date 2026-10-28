"""A gym run pins what it scores and finishes without reading the changed checkout.

The runner's service path (images, Temporal, the batch) is replaced by stubs, so these
tests prove admission, the pinned ``dataset.json``, the finish and the offline commands
that read a run back; tests/integration/test_gym_runner.py runs the same path on a real
ephemeral Temporal server with scripted inference.
"""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    BatchItem,
    Dataset,
    DatasetEntry,
    digest,
)
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.render import render_runs
from corsair.evaluation.gym.scoring import (
    REPORT_FILE,
    SCORECARD_FILE,
    read_scorecard,
)
from corsair.settings import Settings
from tests.unit.evaluation.test_gym_capture import CASE, _evals_root, _result

ROOT = Path(__file__).resolve().parents[2]
RUNS = ("gym-rejected", "gym-accepted")
RUN_ID = "gym-capture-20261027t162650-cea22f"


def _arguments(*argv: str, format: str = "json") -> cli.CliArguments:
    return cli.parser().parse_args(["--format", format, *argv], namespace=cli.CliArguments())


async def _run(args: cli.CliArguments) -> int:
    return await cli.execute(args, Terminal(args))


def _grow(evals: Path, manifest: Path) -> str:
    """Freeze a second row into the tier, as a merge into the run's checkout did."""
    shutil.copytree(ROOT / "evals/fixtures/case02", evals / "fixtures/case02", dirs_exist_ok=True)
    source = json.loads((ROOT / "evals/datasets/dev.json").read_text())
    entries = [DatasetEntry.model_validate(item) for item in source["entries"][:2]]
    grown = Dataset(entries=entries)
    manifest.write_text(grown.model_dump_json(indent=2))
    return digest(grown)


def _case(tmp_path: Path) -> tuple[Path, Path, Settings, bytes]:
    """The one-case tier, a store holding a rejected and an accepted result, and settings."""
    evals, manifest, _ = _evals_root(tmp_path)
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    _result(store, RUNS[0], AuditDecision.REJECT)
    _result(store, RUNS[1], AuditDecision.ACCEPT)
    return evals, manifest, settings, manifest.read_bytes()


def _stub_services(monkeypatch, during: Callable[[], None] = lambda: None) -> None:
    """No image build, no Temporal: the batch returns the stored results; ``during`` runs
    while the episodes would execute."""

    @asynccontextmanager
    async def endpoint(address, log):
        del address, log
        yield "127.0.0.1:1"

    async def execute(settings, batch, compose_activities, observe):
        del batch, compose_activities, observe
        during()
        store = ArtifactStore(settings.artifact_root)
        return [
            BatchItem(case_id=CASE, run_id=run_id, artifact=store.reconcile(f"result.{run_id}"))
            for run_id in RUNS
        ]

    monkeypatch.setattr(gym, "temporal_endpoint", endpoint)
    monkeypatch.setattr(gym, "execute_batch", execute)
    monkeypatch.setattr(
        gym, "ensure_images", lambda root, refs: dict.fromkeys(refs.values(), "sha256:" + "0" * 64)
    )


async def _gym_run(tmp_path: Path, manifest: Path, settings: Settings) -> gym.GymRun:
    options = gym.GymOptions(
        dataset=manifest, settings=settings, out=tmp_path / "run", run_id=RUN_ID, lock=False
    )
    return await gym.run_gym(options, root=ROOT)


def _record(run_dir: Path) -> dict:
    return json.loads((run_dir / gym.RUN_FILE).read_text())


# The pinned copy


@pytest.mark.asyncio
async def test_a_run_scores_the_manifest_it_ran_when_the_tier_changes_mid_run(
    tmp_path, monkeypatch
):
    evals, manifest, settings, admitted = _case(tmp_path)
    pinned = digest(Dataset.model_validate_json(admitted))
    grown: list[str] = []
    _stub_services(monkeypatch, lambda: grown.append(_grow(evals, manifest)))

    run = await _gym_run(tmp_path, manifest, settings)

    assert grown and grown[0] != pinned, "the manifest on disk changed while the run executed"
    assert (run.run_dir / gym.DATASET_FILE).read_bytes() == admitted
    record = _record(run.run_dir)
    assert record["dataset"] == str(manifest)
    assert record["dataset_digest"] == pinned
    assert record["dataset_entries"] == 1
    assert record["dataset_root"] == str(evals.resolve())
    assert record["cases"] == [CASE]
    assert record["case_filter"] == [] and record["languages"] == []
    assert record["episodes"] == 2
    # Scored against the copy: one case, the admitted digest; no row of the grown tier.
    assert run.scorecard.dataset_digest == pinned
    assert json.loads((run.run_dir / REPORT_FILE).read_text())["dataset_digest"] == pinned
    assert {name: group.cases for name, group in run.scorecard.languages.items()} == {"python": 1}
    assert [item.case_id for item in run.trajectories] == [CASE, CASE]


@pytest.mark.asyncio
async def test_cases_record_the_selection_actually_run(tmp_path, monkeypatch):
    evals, manifest, settings, _ = _case(tmp_path)
    _grow(evals, manifest)
    _stub_services(monkeypatch)
    options = gym.GymOptions(
        dataset=manifest,
        settings=settings,
        out=tmp_path / "run",
        run_id=RUN_ID,
        lock=False,
        cases=(CASE,),
    )

    run = await gym.run_gym(options, root=ROOT)

    record = _record(run.run_dir)
    assert (record["cases"], record["case_filter"]) == ([CASE], [CASE])
    assert record["dataset_entries"] == 2 and record["sliced"] is True


async def _pinned_run(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, str, str]:
    """A finished pinned run whose tier grew afterwards; returns the grown digest too."""
    evals, manifest, settings, admitted = _case(tmp_path)
    _stub_services(monkeypatch)
    run = await _gym_run(tmp_path, manifest, settings)
    grown = _grow(evals, manifest)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(settings.model_dump_json())
    pinned = digest(Dataset.model_validate_json(admitted))
    return run.run_dir, manifest, settings_file, pinned, grown


@pytest.mark.asyncio
async def test_score_reads_the_pinned_copy_by_default(tmp_path, monkeypatch, capsys):
    run_dir, manifest, settings, pinned, _ = await _pinned_run(tmp_path, monkeypatch)
    (run_dir / SCORECARD_FILE).unlink()

    assert await _run(_arguments("gym", "score", str(run_dir), "--settings", str(settings))) == 0
    captured = capsys.readouterr()
    card = read_scorecard(run_dir / SCORECARD_FILE)
    assert card.dataset_digest == pinned
    assert {name: group.cases for name, group in card.languages.items()} == {"python": 1}
    assert "dataset_unpinned" not in captured.err

    # The report file names the same run directory; a manifest with the pinned digest is
    # accepted, and it is not a warning.
    original = manifest.parent / "original.json"
    original.write_bytes((run_dir / gym.DATASET_FILE).read_bytes())
    report = str(run_dir / REPORT_FILE)
    args = _arguments(
        "gym", "score", report, "--dataset", str(original), "--settings", str(settings)
    )
    assert await _run(args) == 0
    assert "dataset_unpinned" not in capsys.readouterr().err
    assert read_scorecard(run_dir / SCORECARD_FILE).dataset_digest == pinned


def _console(*argv: str) -> subprocess.CompletedProcess[str]:
    """``corsair`` as the console runs it, where a refused command exits 2."""
    command = [sys.executable, "-m", "corsair.entrypoints.cli", "--format", "json"]
    return subprocess.run(
        [*command, "--log-format", "json", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@pytest.mark.asyncio
async def test_a_dataset_with_another_digest_is_refused_with_exit_2(tmp_path, monkeypatch):
    run_dir, manifest, settings, pinned, grown = await _pinned_run(tmp_path, monkeypatch)
    before = (run_dir / SCORECARD_FILE).read_bytes()

    with pytest.raises(gym.DatasetMismatch) as refused:
        gym.run_dataset(run_dir, manifest)
    message = str(refused.value)
    assert message.startswith("dataset_mismatch: ")
    assert pinned in message and grown in message

    flags = ("--dataset", str(manifest), "--settings", str(settings))
    score = _console("gym", "score", str(run_dir), *flags)
    assert score.returncode == 2, score.stderr
    failure = json.loads(score.stderr.splitlines()[-1])
    assert failure["event"] == "cli.failed"
    assert failure["message"].startswith("dataset_mismatch: ")
    assert pinned in failure["message"] and grown in failure["message"]
    assert score.stdout == ""
    # Nothing was re-scored.
    assert (run_dir / SCORECARD_FILE).read_bytes() == before

    capture = _console("gym", "capture", str(run_dir), "--case", CASE, *flags)
    assert capture.returncode == 2, capture.stderr
    assert "dataset_mismatch" in capture.stderr


@pytest.mark.asyncio
async def test_an_altered_pinned_copy_is_refused(tmp_path, monkeypatch):
    run_dir, manifest, _, pinned, grown = await _pinned_run(tmp_path, monkeypatch)
    shutil.copyfile(manifest, run_dir / gym.DATASET_FILE)

    with pytest.raises(gym.DatasetMismatch, match="dataset_mismatch: the pinned copy") as refused:
        gym.run_dataset(run_dir, None)
    assert pinned in str(refused.value) and grown in str(refused.value)


@pytest.mark.asyncio
async def test_capture_reads_the_pinned_copy_after_the_tier_changed(tmp_path, monkeypatch, capsys):
    run_dir, _, settings, _, _ = await _pinned_run(tmp_path, monkeypatch)
    monkeypatch.setattr(gym, "checkout_root", lambda: tmp_path)
    args = _arguments("gym", "capture", str(run_dir), "--case", CASE, "--settings", str(settings))

    assert await _run(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["case_id"] == CASE
    assert "dataset_unpinned" not in captured.err


# A run from before pinning


@pytest.mark.asyncio
async def test_a_run_without_a_pinned_copy_falls_back_to_dataset_with_a_warning(
    tmp_path, monkeypatch, capsys
):
    run_dir, manifest, settings, pinned, _ = await _pinned_run(tmp_path, monkeypatch)
    original = manifest.parent / "original.json"
    original.write_bytes((run_dir / gym.DATASET_FILE).read_bytes())
    (run_dir / gym.DATASET_FILE).unlink()

    with pytest.raises(ValueError, match="pass --dataset"):
        await _run(_arguments("gym", "score", str(run_dir), "--settings", str(settings)))
    assert gym.run_dataset(run_dir, None) is None

    args = ("gym", "score", str(run_dir), "--dataset", str(original), "--settings", str(settings))
    assert await _run(_arguments(*args)) == 0
    err = capsys.readouterr().err
    assert "Warning: dataset_unpinned:" in err and str(original) in err
    assert read_scorecard(run_dir / SCORECARD_FILE).dataset_digest == pinned

    # Capture finds the checked-in manifest by the report's digest, also with the warning.
    monkeypatch.setattr(gym, "checkout_root", lambda: tmp_path)
    monkeypatch.setattr(gym, "dataset_for_report", lambda report, root: original)
    capture = ("gym", "capture", str(run_dir), "--case", CASE, "--settings", str(settings))
    assert await _run(_arguments(*capture)) == 0
    assert "Warning: dataset_unpinned:" in capsys.readouterr().err


# The source at the end of the run


def _git_sequence(monkeypatch, commits: list[str], dirty: list[bool]) -> None:
    """The checkout's commit and dirty flag, one value per call: start, then finish."""
    monkeypatch.setattr(gym, "git_revision", lambda root: ("gym/loop", commits.pop(0)))
    monkeypatch.setattr(gym, "git_dirty", lambda root: dirty.pop(0))


@pytest.mark.asyncio
async def test_run_json_records_the_checkout_at_finish(tmp_path, monkeypatch):
    _, manifest, settings, _ = _case(tmp_path)
    _stub_services(monkeypatch)
    _git_sequence(monkeypatch, ["a" * 40, "b" * 40], [False, True])

    run = await _gym_run(tmp_path, manifest, settings)

    record = _record(run.run_dir)
    assert record["git"] == {"branch": "gym/loop", "commit": "a" * 40, "dirty": False}
    assert record["git_commit_at_finish"] == "b" * 40
    assert record["source_dirty_at_finish"] is True
    assert record["run"]["git_commit"] == "a" * 40, "the scorecard names the commit it ran"


@pytest.mark.asyncio
async def test_a_finish_git_cannot_read_stays_unknown(tmp_path, monkeypatch):
    _, manifest, settings, _ = _case(tmp_path)
    _stub_services(monkeypatch)
    calls: list[int] = []

    def revision(root: Path) -> tuple[str, str]:
        del root
        calls.append(1)
        if len(calls) > 1:
            raise ValueError("git rev-parse HEAD failed")
        return "gym/loop", "a" * 40

    monkeypatch.setattr(gym, "git_revision", revision)
    monkeypatch.setattr(gym, "git_dirty", lambda root: False)

    run = await _gym_run(tmp_path, manifest, settings)

    record = _record(run.run_dir)
    assert record["git_commit_at_finish"] is None
    assert record["source_dirty_at_finish"] is False
    assert record["completed_at"]


@pytest.mark.asyncio
async def test_gym_runs_marks_a_run_whose_checkout_changed_before_it_finished(
    tmp_path, monkeypatch, capsys
):
    _, manifest, settings, _ = _case(tmp_path)
    _stub_services(monkeypatch)
    _git_sequence(
        monkeypatch, ["a" * 40, "b" * 40, "c" * 40, "c" * 40], [False, False, False, True]
    )
    changed = await _gym_run(tmp_path, manifest, settings)
    steady = await gym.run_gym(
        gym.GymOptions(dataset=manifest, settings=settings, out=tmp_path / "steady", lock=False),
        root=ROOT,
    )
    root = tmp_path / "runs"
    shutil.copytree(changed.run_dir, root / "runs" / changed.run_dir.name)
    shutil.copytree(steady.run_dir, root / "runs" / steady.run_dir.name)

    rows = {row["run_dir"].split("/")[-1]: row for row in gym.list_runs(root)}
    marked, plain = rows["run"], rows["steady"]
    assert (marked["commit_changed"], marked["git_commit_at_finish"]) == (True, "b" * 40)
    assert (plain["commit_changed"], plain["source_dirty_at_finish"]) == (False, True)

    assert await _run(_arguments("gym", "runs", "--root", str(root), format="markdown")) == 0
    text = capsys.readouterr().out
    assert "| aaaaaaa, changed to bbbbbbb at finish |" in text
    assert "| ccccccc, dirty at finish |" in text
    # A run recorded before the finish fields carries no marker.
    assert (
        render_runs([{**plain, "commit_changed": None, "source_dirty_at_finish": None}]).count(
            "| ccccccc |"
        )
        == 1
    )


# No late import at the finish

_FINISH_PROBE = """
import asyncio, json, sys
from contextlib import asynccontextmanager
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import BatchItem
from corsair.entrypoints import cli, gym
from corsair.entrypoints.terminal import Terminal

out, preload, case, runs = sys.argv[1], sys.argv[2] == "preload", sys.argv[3], sys.argv[4]
argv = sys.argv[5:]
late = []


class Recorder:
    # Every corsair module first imported once the run is under way would be read from a
    # checkout that may have changed since admission.
    def find_spec(self, name, path=None, target=None):
        if name == "corsair" or name.startswith("corsair."):
            late.append(name)
        return None


@asynccontextmanager
async def endpoint(address, log):
    sys.meta_path.insert(0, Recorder())
    yield "127.0.0.1:1"


async def execute(settings, batch, compose_activities, observe):
    store = ArtifactStore(settings.artifact_root)
    return [
        BatchItem(case_id=case, run_id=run_id, artifact=store.reconcile("result." + run_id))
        for run_id in runs.split(",")
    ]


gym.temporal_endpoint = endpoint
gym.execute_batch = execute
gym.ensure_images = lambda root, refs: dict.fromkeys(refs.values(), "sha256:" + "0" * 64)
if not preload:
    gym.FINISH_IMPORTS = ()
args = cli.parser().parse_args(argv, namespace=cli.CliArguments())
code = asyncio.run(cli.execute(args, Terminal(args)))
with open(out, "w") as handle:
    json.dump({"code": code, "late": late}, handle)
"""


def _finish_probe(tmp_path: Path, *, preload: bool) -> dict:
    """``corsair gym run`` in a fresh interpreter, recording imports after Temporal starts."""
    _, manifest, settings, _ = _case(tmp_path)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(settings.model_dump_json())
    out = tmp_path / f"probe-{preload}.json"
    argv = ["--format", "markdown", "gym", "run", str(manifest), "--settings", str(settings_file)]
    argv += ["--out", str(tmp_path / f"run-{preload}"), "--no-lock", "--run-id", RUN_ID]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _FINISH_PROBE,
            str(out),
            "preload" if preload else "lazy",
            CASE,
            ",".join(RUNS),
            *argv,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(out.read_text())


def test_the_finish_imports_nothing_after_admission(tmp_path):
    probe = _finish_probe(tmp_path, preload=True)

    assert probe == {"code": 0, "late": []}


def test_the_probe_sees_a_late_import_when_admission_skips_the_preload(tmp_path):
    # The control: without the admission preload the finish imports the evidence verifier.
    probe = _finish_probe(tmp_path, preload=False)

    assert probe["code"] == 0
    assert "corsair.steps.verification" in probe["late"]


def test_admission_imports_every_finish_module():
    gym.preload_finish()
    assert all(name in sys.modules for name in gym.FINISH_IMPORTS)
