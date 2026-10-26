"""Read-only run listing and evidence inspection over a synthetic committed store."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditOutput,
    Budget,
    Disposition,
    EvidenceInput,
    ExecutionStatus,
    InvestigationResult,
    LineProvenance,
    ProducerDecision,
    ProducerOutput,
    RoleOutcome,
    RoundResult,
    Verdict,
)
from corsair.entrypoints.cli import execute, parser
from corsair.entrypoints.runs import inspect_evidence, list_runs
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.unit.test_evidence import _audit, _FakeSandbox, _prepared, _submission

PRIVATE = ("hello.txt", "../private/secret.txt", "return read(path)", "component finding")


def _commit_run(
    store: ArtifactStore,
    run_id: str,
    case_id: str = "case",
    *,
    recorded: float = 1_700_000_000,
    cleanup_confirmed: bool = True,
    audit: AuditOutput | None = None,
    declared_line: int = 4,
) -> InvestigationResult:
    """Commit one result whose round observation was produced by the trusted verifier."""
    prepared = _prepared().model_copy(
        update={"case_id": case_id, "source": store.put(b"source", "application/x-tar")}
    )
    if declared_line != 4:  # _FakeSandbox covers line 4: bind the declared line to it.
        finding = prepared.finding.model_copy(update={"line": declared_line})
        prepared = prepared.model_copy(update={"finding": finding, "target_line": 4})
    submission = _submission()
    observation = EvidenceVerifier(
        Settings(), store, _FakeSandbox(store, cleanup_confirmed=cleanup_confirmed)
    ).evaluate(
        EvidenceInput(
            run_id=run_id,
            operation_id=f"{run_id}.r1",
            prepared=prepared,
            submission=submission,
            budget=Budget(probe_timeout_seconds=5),
        )
    )
    result = InvestigationResult(
        run_id=run_id,
        case_id=case_id,
        disposition=Disposition.SUPPORTED,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
        execution_status=ExecutionStatus.COMPLETED,
        reason="synthetic",
        manifest=prepared.manifest,
        rounds=[
            RoundResult(
                index=1,
                producer=ProducerOutput(
                    decision=ProducerDecision(kind="proposal", submission=submission)
                ),
                observation=observation,
                audit=audit,
            )
        ],
    )
    store.commit(f"result.{run_id}", store.put_json(result))
    record = store.operations / store.operation_key(f"result.{run_id}")
    os.utime(record, (recorded, recorded))
    return result


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_list_runs_returns_only_bound_results_newest_first(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_run(store, "run-old", "case01", recorded=1_700_000_000)
    _commit_run(store, "run-new", "case02", recorded=1_700_000_500)
    before = _snapshot(store.root)

    listing = list_runs(store)

    assert [row["run_id"] for row in listing["runs"]] == ["run-new", "run-old"]
    newest = listing["runs"][0]
    assert newest["case_id"] == "case02"
    assert newest["verdict"] is Verdict.EXPLOIT_DEMONSTRATED
    assert newest["execution_status"] is ExecutionStatus.COMPLETED
    assert newest["rounds"] == 1
    assert newest["recorded_at"] == "2023-11-14T22:21:40+00:00"
    assert listing["invalid_records"] == 0
    assert _snapshot(store.root) == before, "listing must never write to the store"


def test_list_runs_filters_by_case_and_limits_after_filtering(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_run(store, "run-a", "case01", recorded=1_700_000_000)
    _commit_run(store, "run-b", "case02", recorded=1_700_000_100)
    _commit_run(store, "run-c", "case01", recorded=1_700_000_200)

    assert [row["run_id"] for row in list_runs(store, case_id="case01")["runs"]] == [
        "run-c",
        "run-a",
    ]
    assert [row["run_id"] for row in list_runs(store, limit=1)["runs"]] == ["run-c"]
    assert list_runs(store, case_id="absent")["runs"] == []


def test_list_runs_counts_unbound_and_unreadable_records_without_listing_them(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    result = _commit_run(store, "run-real")
    # A genuine result committed under a different name is not a listing of that name.
    store.commit("result.someone-else", store.put_json(result))
    (store.operations / ("f" * 64)).write_bytes(b"not a reference")
    (store.operations / ".write-partial").write_bytes(b"ignored temporary")

    listing = list_runs(store)

    assert [row["run_id"] for row in listing["runs"]] == ["run-real"]
    assert listing["invalid_records"] == 2


def test_inspect_evidence_walks_receipts_without_payloads_or_fixture(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    result = _commit_run(store, "run-evidence")
    before = _snapshot(store.root)

    view = inspect_evidence(store, result)

    assert _snapshot(store.root) == before
    [item] = view["observations"]
    assert (item["session"], item["round"], item["fixed"]) == (1, 1, False)
    assert item["operation_id"] == "run-evidence.r1"
    assert item["committed"] is True
    assert item["evidence"] == "present"
    assert item["receipts_admissible"] is True
    # The verified prepared case's target line, as declared by the request.
    assert (item["target_line"], item["line_provenance"]) == (4, LineProvenance.DECLARED)
    assert item["cleanup_confirmed"] is True
    # A record made before line binding reports the declared line as the bound one.
    assert item["declared_line"] == item["target_line"] == 4
    control, adversarial = item["roles"]["control"], item["roles"]["adversarial"]
    assert control["outcome"] is RoleOutcome.HELD and control["native_exit_code"] == 0
    assert adversarial["outcome"] is RoleOutcome.VIOLATION
    assert adversarial["native_exit_code"] == 1
    for role, entry in item["roles"].items():
        assert entry["receipt"] == "present"
        assert entry["target_executed"] is True
        assert entry["covered_lines"] == [4]
        assert entry["cleanup_confirmed"] is True
        assert entry["container_id"] == f"id-{role}"
        assert entry["image_id"] == "sha256:trusted"
        assert set(entry) == {
            "outcome",
            "target_executed",
            "covered_lines",
            "native_exit_code",
            "receipt",
            "raw_sha256",
            "cleanup_confirmed",
            "container_id",
            "image_id",
            "docker_exit_code",
        }
    rendered = json.dumps(view, default=str)
    for private in PRIVATE:
        assert private not in rendered


def test_inspect_evidence_reports_the_declared_and_the_bound_target_line(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    result = _commit_run(store, "run-bound", declared_line=3)
    [item] = inspect_evidence(store, result)["observations"]
    assert (item["declared_line"], item["target_line"]) == (3, 4)
    assert item["line_provenance"] == LineProvenance.DECLARED
    assert item["receipts_admissible"] is True


def test_inspect_evidence_reports_unconfirmed_cleanup_as_not_admissible(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    result = _commit_run(store, "run-unclean", cleanup_confirmed=False)

    [item] = inspect_evidence(store, result)["observations"]

    assert item["cleanup_confirmed"] is False
    assert item["receipts_admissible"] is False
    assert item["target_line"] is None  # only an admissible receipt names the target
    assert item["roles"]["control"]["cleanup_confirmed"] is False
    # Unconfirmed control cleanup skips the adversarial role: no receipt exists for it.
    assert item["roles"]["adversarial"]["receipt"] == "absent"


def test_inspect_evidence_flags_a_result_whose_observation_was_not_committed(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    result = _commit_run(store, "run-forged")
    observation = result.rounds[0].observation
    assert observation is not None
    forged = result.model_copy(
        update={
            "rounds": [
                result.rounds[0].model_copy(
                    update={"observation": observation.model_copy(update={"artifact": None})}
                )
            ]
        }
    )

    [item] = inspect_evidence(store, forged)["observations"]

    assert item["committed"] is False
    assert item["evidence"] == "absent"
    assert item["receipts_admissible"] is False
    assert {entry["receipt"] for entry in item["roles"].values()} == {"absent"}


def _settings_for(store: ArtifactStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "corsair.entrypoints.cli._settings",
        lambda _: Settings(artifact_root=str(store.root)),
    )


async def test_runs_command_emits_json_listing(tmp_path, monkeypatch, capsys):
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_run(store, "run-a", "case01", recorded=1_700_000_000)
    _commit_run(store, "run-b", "case02", recorded=1_700_000_100)
    _settings_for(store, monkeypatch)

    args = parser().parse_args(["--format", "json", "runs", "--case", "case01", "--limit", "5"])

    assert await execute(args) == 0
    listing = json.loads(capsys.readouterr().out)
    assert [row["run_id"] for row in listing["runs"]] == ["run-a"]
    assert listing["runs"][0]["verdict"] == "EXPLOIT_DEMONSTRATED"


async def test_inspect_evidence_command_emits_json_and_human_views(tmp_path, monkeypatch, capsys):
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_run(store, "run-a")
    _settings_for(store, monkeypatch)

    assert (
        await execute(parser().parse_args(["--format", "json", "inspect", "run-a", "--evidence"]))
        == 0
    )
    view = json.loads(capsys.readouterr().out)
    assert view["observations"][0]["roles"]["control"]["outcome"] == "PROPERTY_HELD"
    assert view["observations"][0]["line_provenance"] == "declared"

    human = ["--format", "human", "--no-color", "inspect", "run-a", "--evidence"]
    assert await execute(parser().parse_args(human)) == 0
    output = capsys.readouterr().out
    assert "Evidence run-a" in output and "id-control" in output
    assert "target=L4" in output and "derived" not in output
    for private in PRIVATE:
        assert private not in output

    assert await execute(parser().parse_args(["--format", "human", "--no-color", "runs"])) == 0
    assert "run-a" in capsys.readouterr().out


async def test_inspect_names_round_stops_from_the_committed_receipts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "160")
    store = ArtifactStore(tmp_path / "artifacts")
    _commit_run(store, "run-verified", audit=_audit())
    _commit_run(store, "run-unaudited")
    _settings_for(store, monkeypatch)
    before = _snapshot(store.root)

    human = ["--format", "human", "--no-color", "inspect"]
    assert await execute(parser().parse_args([*human, "run-verified"])) == 0
    output = capsys.readouterr().out
    stop = next(line for line in output.splitlines() if line.startswith("│ 1.1"))
    assert "demonstrated" in stop and "evidence_unverified" not in output
    assert "demonstrated · kernel at 1.1" in output

    assert await execute(parser().parse_args([*human, "run-unaudited"])) == 0
    assert "audit_not_run" in capsys.readouterr().out
    for private in PRIVATE:
        assert private not in output
    assert _snapshot(store.root) == before, "inspect must never write to the store"

    # JSON stays the committed result itself.
    assert await execute(parser().parse_args(["--format", "json", "inspect", "run-verified"])) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert set(emitted) == set(InvestigationResult.model_fields)


def test_existing_store_never_creates_an_absent_artifact_root(tmp_path):
    from corsair.entrypoints.cli import _existing_store

    absent = tmp_path / "absent"
    assert _existing_store(Settings(artifact_root=str(absent))) is None
    assert not absent.exists()
    store = ArtifactStore(tmp_path / "artifacts")
    opened = _existing_store(Settings(artifact_root=str(store.root)))
    assert opened is not None and opened.root == store.root


async def test_inspect_evidence_rejects_online_before_runtime_state():
    args = parser().parse_args(["inspect", "run1", "--online", "--evidence"])

    with pytest.raises(ValueError, match="--evidence"):
        await execute(args)


@pytest.mark.parametrize("limit", ["0", "-1", "many"])
def test_runs_parser_rejects_non_positive_limit(limit):
    with pytest.raises(SystemExit) as error:
        parser().parse_args(["runs", "--limit", limit])

    assert error.value.code == 2


def test_runs_parser_defaults_to_an_unfiltered_listing():
    args = parser().parse_args(["runs"])

    assert (args.case, args.limit) == (None, None)
    assert parser().parse_args(["inspect", "run1"]).evidence is False


def test_evidence_caption_marks_a_derived_target_line() -> None:
    from corsair.entrypoints.render.runs import _target_caption

    assert _target_caption({"target_line": None, "line_provenance": None}) == ""
    assert _target_caption({"target_line": 4, "line_provenance": "declared"}) == " · target=L4"
    assert _target_caption({"target_line": 6, "line_provenance": "recipe_function"}) == (
        " · target=L6 (derived from recipe function)"
    )


def test_evidence_caption_names_the_declared_line_a_binding_moved() -> None:
    from corsair.entrypoints.render.runs import _target_caption

    moved = {"target_line": 4, "declared_line": 3, "line_provenance": "declared"}
    assert _target_caption(moved) == " · target=L4 (declared L3, bound to its reported statement)"
    kept = {"target_line": 4, "declared_line": 4, "line_provenance": "declared"}
    assert _target_caption(kept) == " · target=L4"
