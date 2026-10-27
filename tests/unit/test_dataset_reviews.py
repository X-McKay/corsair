"""Tracked review records: ``dataset freeze`` writes one, ``dataset audit`` reads them back.

Drafts and manifests are synthetic under tmp_path (helpers from the draft and staging tests);
one test audits the checked-in tiers and their reconstructed wave-4 records. No model,
Docker or Temporal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import corsair.contracts.evaluation as evaluation_contracts
from corsair.contracts import (
    Dataset,
    DatasetReview,
    DatasetReviewEntry,
    ReviewDecision,
    Verdict,
    digest,
)
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation import intake, reviews
from corsair.evaluation.intake import REASON_COLUMN, freeze_dataset
from tests.unit.test_dataset_intake_draft import _accept_all, _draft, _reviewed, _write_json
from tests.unit.test_dataset_intake_staging import _staged_case, _staged_draft

ROOT = Path(__file__).resolve().parents[2]
CASES = ("ih-python-demo-a", "ih-python-demo-b")
DIGEST = "a" * 64
WAVE4 = {
    "gym-tier1.json": {
        "ih-python-codeinjection-a",
        *(
            f"sbj-javascript-{name}"
            for name in ("aurelia-path", "deep-override", "mixin-deep", "safe-flat")
        ),
        "sbj-javascript-viking04-merge",
    },
    "gym-tier2.json": {
        f"sbj-javascript-{name}" for name in ("deep-extend", "json-schema", "nestie", "vega-util")
    },
}


@pytest.fixture
def evals(tmp_path: Path) -> Path:
    from tests.unit.test_dataset_intake_draft import _chain_pair

    root = tmp_path / "evals"
    _chain_pair(root, "demo")
    return root


def _with_reason(sheet: Path, reasons: dict[str, str]) -> Path:
    """The reviewer's sheet with an added last ``reason`` column."""
    lines = []
    for line in sheet.read_text().splitlines():
        if line.startswith("| case id |"):
            line = line + f" {REASON_COLUMN} |"
        elif line.startswith("| ---"):
            line = line + " --- |"
        elif line.startswith("| "):
            case_id = line.split("|")[1].strip()
            line = line + f" {reasons.get(case_id, '')} |"
        lines.append(line)
    sheet.write_text("\n".join(lines) + "\n")
    return sheet


def _accept_one(draft: Path, case_id: str) -> Path:
    """Accept ``case_id`` and reject the draft's other row."""
    return _reviewed(
        draft, {case: ("accept" if case == case_id else "reject", "owner", "") for case in CASES}
    )


def _record(result: dict) -> DatasetReview:
    return DatasetReview.model_validate_json(Path(result["review_record"]).read_bytes())


# The contract


def test_the_review_contract_is_one_canonical_class_publicly_re_exported():
    assert DatasetReview is evaluation_contracts.DatasetReview
    assert DatasetReviewEntry is evaluation_contracts.DatasetReviewEntry
    assert ReviewDecision is evaluation_contracts.ReviewDecision
    assert DatasetReview.model_fields["schema_version"].default == "corsair.dataset-review/1"


def test_a_review_record_round_trips_through_json():
    record = DatasetReview(
        manifest="evals/datasets/gym-tier1.json",
        old_manifest_digest=None,
        new_manifest_digest=DIGEST,
        draft_id="wave1",
        draft_digest=DIGEST,
        review_sheet_digest=DIGEST,
        source_root=".work/intake",
        staged=True,
        split="held_out",
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
        entries=[
            DatasetReviewEntry(
                case_id="sbj-javascript-a",
                family="sbj-javascript-a",
                kind="javascript.prototype_pollution/1",
                decision=ReviewDecision.AMEND,
                reviewer="owner",
                reviewed_oracle_digest=DIGEST,
                frozen_oracle_digest=DIGEST,
                reason="narrowed",
                licence="retained",
                import_target="evals/datasets/corpus/secbenchjs/sbj-javascript-a",
            ),
            DatasetReviewEntry(case_id="b", decision="reject", reason="duplicate tree"),
        ],
    )
    payload = record.model_dump_json(exclude_none=True)
    assert DatasetReview.model_validate_json(payload) == record
    assert json.loads(payload)["entries"][1] == {
        "case_id": "b",
        "decision": "reject",
        "reason": "duplicate tree",
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"case_id": "a", "decision": "accept"},  # an accepted row names its frozen oracle
        {"case_id": "a", "decision": "reject", "frozen_oracle_digest": DIGEST},
        {"case_id": "a", "decision": "reject", "import_target": "evals/x"},
        {"case_id": "a", "decision": "maybe"},
        {"case_id": "a", "decision": "reject", "licence": "MIT"},
    ],
)
def test_an_incoherent_review_entry_is_refused(entry):
    with pytest.raises(ValidationError):
        DatasetReviewEntry.model_validate(entry)


@pytest.mark.parametrize(
    "fields",
    [
        {"reconstructed": True},
        {"reconstructed_from": "agent reports"},
        {"entries": [{"case_id": "a", "decision": "reject"}] * 2},
        {"schema_version": "corsair.dataset-review/2"},
        {"draft_id": "../escape"},
    ],
)
def test_an_incoherent_review_record_is_refused(fields):
    base = {
        "manifest": "m.json",
        "draft_id": "d",
        "split": "s",
        "entries": [{"case_id": "a", "decision": "reject"}],
    }
    with pytest.raises(ValidationError):
        DatasetReview.model_validate({**base, **fields})


# dataset freeze writes the record


def test_freeze_records_accepted_and_rejected_rows_beside_the_manifest(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _reviewed(
        draft,
        {
            "ih-python-demo-b": ("accept", "owner", ""),
            "ih-python-demo-a": ("reject", "owner", "not a digest"),
        },
    )
    into = evals / "datasets/t2.json"
    result = freeze_dataset(draft, review=review, into=into, against=[])

    assert result["written"] and result["rejected"] == ["ih-python-demo-a"]
    path = Path(result["review_record"])
    assert path == evals / "datasets/reviews/t2/draft-held_out.json"
    record = _record(result)
    manifest = Dataset.model_validate_json(into.read_bytes())
    assert record.manifest == "evals/datasets/t2.json"
    assert (record.old_manifest_digest, record.new_manifest_digest) == (
        None,
        result["identity"]["new"],
    )
    assert record.new_manifest_digest == digest(manifest)
    assert record.draft_id == "draft"
    assert record.draft_digest == digest((draft / "draft.json").read_bytes())
    assert record.review_sheet_digest == digest(review.read_bytes())
    assert (record.source_root, record.staged, record.split) == ("evals", False, "held_out")
    assert record.recorded_at is not None and not record.reconstructed
    accepted, rejected = sorted(record.entries, key=lambda entry: entry.decision)
    frozen = manifest.entries[0]
    assert accepted.model_dump(exclude_none=True) == {
        "case_id": "ih-python-demo-b",
        "family": frozen.family,
        "kind": "python.secret_disclosure/1",
        "decision": ReviewDecision.ACCEPT,
        "reviewer": "owner",
        "frozen_oracle_digest": frozen.oracle_digest,
    }
    assert rejected.decision is ReviewDecision.REJECT
    assert rejected.frozen_oracle_digest is None
    # An unchecked digest cell of a rejected row is kept only when it is a digest.
    assert rejected.reviewed_oracle_digest is None and rejected.reason is None


def test_freeze_records_an_amended_oracle_its_reviewed_digest_and_the_reasons(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    proposal = json.loads((draft / "ih-python-demo-b/oracle.proposed.json").read_text())
    proposal["acceptable_verdicts"] = [Verdict.EXPLOIT_DEMONSTRATED.value]
    amended_path = _write_json(draft / "ih-python-demo-b/oracle.json", proposal)
    reviewed = digest(amended_path.read_bytes())
    review = _with_reason(
        _reviewed(
            draft,
            {
                "ih-python-demo-b": ("amend", "owner", reviewed),
                "ih-python-demo-a": ("reject", "owner", ""),
            },
        ),
        {"ih-python-demo-b": "violation only", "ih-python-demo-a": "duplicate tree"},
    )
    result = freeze_dataset(draft, review=review, into=evals / "datasets/t2.json", against=[])

    assert result["written"], result["refusals"]
    entries = {entry.case_id: entry for entry in _record(result).entries}
    amend = entries["ih-python-demo-b"]
    assert amend.decision is ReviewDecision.AMEND
    assert amend.reviewed_oracle_digest == reviewed == amend.frozen_oracle_digest
    assert amend.reason == "violation only"
    assert entries["ih-python-demo-a"].reason == "duplicate tree"


def test_a_sheet_with_an_unknown_extra_column_is_still_refused(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _accept_all(draft, *CASES)
    review.write_text(
        review.read_text()
        .replace("reviewed oracle digest |\n", "reviewed oracle digest | notes |\n")
        .replace("| --- |\n", "| --- | --- |\n")
    )
    result = freeze_dataset(draft, review=review, into=evals / "datasets/t2.json", against=[])
    assert {item["rule"] for item in result["refusals"]} == {"sheet_missing_table"}
    assert result["review_record"] is None
    assert not (evals / "datasets/reviews").exists()


def test_a_review_that_rejects_every_row_is_recorded_and_writes_no_manifest(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _reviewed(draft, dict.fromkeys(CASES, ("reject", "owner", "")))
    into = evals / "datasets/t2.json"
    result = freeze_dataset(draft, review=review, into=into, against=[])

    assert not result["written"] and not into.exists()
    record = _record(result)
    assert (record.old_manifest_digest, record.new_manifest_digest) == (None, None)
    assert {entry.decision for entry in record.entries} == {ReviewDecision.REJECT}


def test_a_refused_freeze_records_nothing(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _reviewed(draft, {"ih-python-demo-b": ("accept", "owner", "")})
    result = freeze_dataset(draft, review=review, into=evals / "datasets/t2.json", against=[])
    assert result["refusals"] and result["review_record"] is None
    assert not (evals / "datasets/reviews").exists()


def test_the_record_is_written_before_the_manifest_is_replaced(tmp_path, evals, monkeypatch):
    draft = _draft(tmp_path, evals)
    review = _accept_one(draft, "ih-python-demo-b")
    into = evals / "datasets/t2.json"
    seen = []
    replace = intake.os.replace

    def observed(source, target):
        if Path(target) == into:
            seen.append(sorted((evals / "datasets/reviews/t2").glob("*.json")))
        return replace(source, target)

    monkeypatch.setattr(intake.os, "replace", observed)
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert seen == [[Path(result["review_record"])]]


def test_a_later_freeze_of_a_same_named_draft_keeps_the_earlier_record(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    into = evals / "datasets/t2.json"
    first = freeze_dataset(
        draft, review=_accept_one(draft, "ih-python-demo-b"), into=into, against=[]
    )
    second_draft = tmp_path / "second/draft"
    second_draft.parent.mkdir()
    intake.draft_dataset(
        [evals / "datasets/chain/python/demo-a"],
        recipe_template=tmp_path / "recipe-template.json",
        split="held_out",
        out=second_draft,
    )
    second = freeze_dataset(
        second_draft, review=_accept_all(second_draft, "ih-python-demo-a"), into=into, against=[]
    )
    assert second["written"], second["refusals"]
    assert first["review_record"] != second["review_record"]
    assert Path(first["review_record"]).name == "draft-held_out.json"
    assert Path(second["review_record"]).name.startswith("draft-2")
    assert _record(second).old_manifest_digest == first["identity"]["new"]


def test_freeze_records_a_staged_rows_licence_and_import_target(tmp_path):
    stage = tmp_path / "work/intake"
    _staged_case(stage, "demo-b")
    _staged_case(stage, "other-b", licence=False)
    evals = tmp_path / "evals"
    (evals / "datasets/corpus").mkdir(parents=True)
    draft = _staged_draft(tmp_path, stage, "demo-b", "other-b")
    review = _reviewed(
        draft,
        {
            "unk-python-demo-b": ("accept", "owner (pending owner audit)", ""),
            "unk-python-other-b": ("reject", "owner", ""),
        },
    )
    target = evals / "datasets/corpus/staged"
    result = freeze_dataset(
        draft,
        review=review,
        into=evals / "datasets/gym-tier2.json",
        against=[],
        import_into=target,
    )

    assert result["written"], result["refusals"]
    record = _record(result)
    assert record.staged and record.source_root == "work/intake"
    entries = {entry.case_id: entry for entry in record.entries}
    imported = entries["unk-python-demo-b"]
    assert imported.licence == "retained"
    assert imported.import_target == "evals/datasets/corpus/staged/unk-python-demo-b"
    rejected = entries["unk-python-other-b"]
    assert (rejected.licence, rejected.import_target) == ("NOASSERTION", None)


async def test_cli_freeze_redirects_the_record_and_keeps_its_exit_status(tmp_path, evals, capsys):
    draft = _draft(tmp_path, evals)
    review = _accept_one(draft, "ih-python-demo-b")
    into = evals / "datasets/t2.json"
    elsewhere = tmp_path / "records"
    against = _write_json(
        tmp_path / "empty.json", {"schema_version": "corsair.agent-dataset/1", "entries": []}
    )
    args = _arguments(
        "dataset", "freeze", str(draft), "--review", str(review), "--into", str(into),
        "--against", str(against), "--record-review", str(elsewhere),
    )  # fmt: skip
    assert await cli.execute(args, Terminal(args)) == 1
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["review_record"] == str(elsewhere / "t2/draft-held_out.json")
    assert not (evals / "datasets/reviews").exists()


# dataset audit


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


def _audited_manifest(tmp_path: Path, evals: Path) -> Path:
    """A manifest of both demo rows: one accepted by the owner, one by a stand-in."""
    draft = _draft(tmp_path, evals)
    review = _reviewed(
        draft,
        {
            "ih-python-demo-b": ("accept", "owner", ""),
            "ih-python-demo-a": ("accept", "agent (Pending Owner Audit)", ""),
        },
    )
    into = evals / "datasets/t2.json"
    assert freeze_dataset(draft, review=review, into=into, against=[])["written"]
    return into


def _rows(audit: dict) -> dict[str, dict]:
    return {row["case_id"]: row for item in audit["manifests"] for row in item["rows"]}


def test_audit_lists_each_row_with_its_record_and_flags_pending_owner_audits(tmp_path, evals):
    into = _audited_manifest(tmp_path, evals)
    audit = reviews.audit_manifests([into])
    rows = _rows(audit)

    assert rows["ih-python-demo-b"]["status"] == "reviewed"
    assert rows["ih-python-demo-b"]["flags"] == []
    assert rows["ih-python-demo-b"]["record"] == "evals/datasets/reviews/t2/draft-held_out.json"
    assert rows["ih-python-demo-b"]["reviewer"] == "owner"
    assert rows["ih-python-demo-a"]["status"] == "pending_owner_audit"
    assert audit["counts"] == {
        "rows": 2,
        "reviewed": 1,
        "unreviewed": 0,
        "pending_owner_audit": 1,
        "oracle_changed": 0,
        "rejected_but_frozen": 0,
        "problems": 0,
    }


def test_audit_flags_unreviewed_changed_and_rejected_rows_and_takes_the_latest_record(
    tmp_path, evals
):
    into = _audited_manifest(tmp_path, evals)
    manifest = Dataset.model_validate_json(into.read_bytes())
    third = manifest.entries[0].model_copy(update={"case_id": "legacy-row"})
    into.write_text(Dataset(entries=[*manifest.entries, third]).model_dump_json())
    directory = evals / "datasets/reviews/t2"
    later = DatasetReview(
        manifest="evals/datasets/t2.json",
        draft_id="later",
        split="held_out",
        recorded_at=datetime(2999, 1, 1, tzinfo=UTC),
        entries=[
            DatasetReviewEntry(
                case_id="ih-python-demo-b",
                decision="accept",
                reviewer="owner",
                frozen_oracle_digest=DIGEST,
            ),
            DatasetReviewEntry(case_id="ih-python-demo-a", decision="reject", reviewer="owner"),
        ],
    )
    (directory / "a-later.json").write_text(later.model_dump_json())
    (directory / "broken.json").write_text("{}")
    audit = reviews.audit_manifests([into])
    rows = _rows(audit)

    assert rows["legacy-row"]["status"] == "unreviewed" and rows["legacy-row"]["record"] is None
    assert rows["ih-python-demo-b"]["flags"] == ["oracle_changed"]
    assert rows["ih-python-demo-b"]["record"].endswith("a-later.json")
    assert rows["ih-python-demo-a"]["flags"] == ["rejected_but_frozen"]
    (problem,) = audit["manifests"][0]["problems"]
    assert problem.startswith("broken.json: unreadable review record")


def test_audit_reports_an_unreadable_manifest_without_failing(tmp_path):
    missing = tmp_path / "missing.json"
    audit = reviews.audit_manifests([missing])
    assert audit["manifests"][0]["rows"] == []
    assert audit["counts"]["problems"] == 1


async def test_cli_audit_exits_zero_with_json_and_a_code_owned_human_table(tmp_path, evals, capsys):
    into = _audited_manifest(tmp_path, evals)
    records = evals / "datasets/reviews/t2"
    (records / "draft-held_out.json").write_text(
        (records / "draft-held_out.json")
        .read_text()
        .replace('"reviewer": "owner"', '"reviewer": "owner\\u001b[31m", "reason": "REASON-TEXT"')
    )
    args = _arguments("dataset", "audit", str(into), str(tmp_path / "missing.json"))
    assert await cli.execute(args, Terminal(args)) == 0
    audit = json.loads(capsys.readouterr().out)
    assert set(audit) == {"dataset_audit", "manifests", "counts"}
    assert audit["counts"]["problems"] == 1

    human = cli.parser().parse_args(
        ["--format", "human", "--no-color", "dataset", "audit", str(into)],
        namespace=cli.CliArguments(),
    )
    assert await cli.execute(human, Terminal(human)) == 0
    shown = capsys.readouterr().out
    assert "Review audit" in shown and "pending_owner_audit" in shown
    assert "REASON-TEXT" not in shown and "\x1b[31m" not in shown
    assert "hidden" in shown


def test_audit_and_freeze_parse_their_arguments():
    audit = cli.parser().parse_args(["dataset", "audit", "a.json", "--reviews", "r"])
    assert (audit.manifests, audit.reviews) == (["a.json"], "r")
    default = cli.parser().parse_args(["dataset", "audit"])
    assert (default.manifests, default.reviews) == ([], None)
    freeze = cli.parser().parse_args(
        ["dataset", "freeze", "d", "--review", "r.md", "--into", "x.json", "--against", "a"]
    )
    assert freeze.record_review is None


# The checked-in tiers and their reconstructed wave-4 records


def test_the_checked_in_records_are_valid_and_match_their_manifests():
    directory = ROOT / "evals/datasets/reviews"
    paths = sorted(directory.rglob("*.json"))
    assert paths
    for path in paths:
        record = DatasetReview.model_validate_json(path.read_bytes())
        manifest = Dataset.model_validate_json((ROOT / record.manifest).read_bytes())
        assert path.parent.name == Path(record.manifest).stem
        oracles = {entry.case_id: entry.oracle_digest for entry in manifest.entries}
        for entry in record.entries:
            if entry.decision is not ReviewDecision.REJECT:
                assert oracles[entry.case_id] == entry.frozen_oracle_digest


def test_the_tier_audit_shows_the_wave4_rows_pending_and_earlier_rows_unreviewed():
    tiers = [ROOT / "evals/datasets" / f"gym-tier{n}.json" for n in range(3)]
    audit = reviews.audit_manifests(tiers)
    for item in audit["manifests"]:
        name = Path(item["manifest"]).name
        pending = {row["case_id"] for row in item["rows"] if row["status"] == "pending_owner_audit"}
        assert pending == WAVE4.get(name, set())
        assert all(
            row["status"] == "unreviewed" for row in item["rows"] if row["case_id"] not in pending
        )
        assert item["problems"] == []
    assert audit["counts"]["pending_owner_audit"] == 10
