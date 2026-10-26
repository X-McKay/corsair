"""Offline dataset validation: one synthetic failure per class, the checked-in datasets, the CLI.

Synthetic datasets copy frozen fixtures into tmp_path, so no checked-in file is ever edited.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from corsair.contracts import digest
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.datasets import (
    case_oracle_problems,
    validate_dataset,
    validate_datasets,
)
from corsair.evaluation.scoring import Oracle

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
CHECKED_IN = sorted((EVALS / "datasets").glob("*.json"))
# Not a manifest any evaluator loads: a case-name -> digest map without schema_version.
NOT_MANIFESTS = {"held_out.json"}


def _copy_fixture(tmp_path: Path, name: str, target: str | None = None) -> Path:
    destination = tmp_path / "fixtures" / (target or name)
    shutil.copytree(EVALS / "fixtures" / name, destination)
    return destination


def _case_entry(tmp_path: Path, case: str, **overrides: Any) -> dict[str, Any]:
    entry = {
        "case_id": case,
        "family": "family01",
        "split": "dev",
        "request": f"fixtures/{case}/request.json",
        "oracle": f"fixtures/{case}/oracle.json",
    }
    entry.update(overrides)
    for name in ("request", "oracle"):
        if f"{name}_digest" not in entry:
            entry[f"{name}_digest"] = digest((tmp_path / entry[name]).read_bytes())
    return entry


def _write_dataset(tmp_path: Path, entries: list[dict[str, Any]], **fields: Any) -> Path:
    path = tmp_path / "datasets" / "synthetic.json"
    path.parent.mkdir(exist_ok=True)
    document = {"schema_version": "corsair.dataset/1", "entries": entries, **fields}
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


def _case_dataset(tmp_path: Path, *cases: str) -> Path:
    for case in cases:
        _copy_fixture(tmp_path, case)
    return _write_dataset(tmp_path, [_case_entry(tmp_path, case) for case in cases])


def _edit_json(path: Path, edit) -> None:
    document = json.loads(path.read_text())
    edit(document)
    path.write_text(json.dumps(document, indent=2) + "\n")


def _entry(report: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(item for item in report["entries"] if item["case_id"] == case_id)


def _failed(entry: dict[str, Any]) -> set[str]:
    return {name for name, status in entry["checks"].items() if status == "fail"}


# The checked-in datasets


@pytest.mark.parametrize("path", CHECKED_IN, ids=[path.name for path in CHECKED_IN])
def test_every_checked_in_dataset_manifest_validates(path):
    report = validate_dataset(path).as_dict()

    if path.name in NOT_MANIFESTS:
        assert report["status"] == "fail"
        assert report["problems"][0].startswith("not an evaluation dataset manifest")
        return
    assert report["status"] == "pass", report
    assert report["loader"] == "pass"
    assert all(item["status"] == "pass" for item in report["entries"])


def test_validation_reports_the_digest_the_evaluation_report_records():
    from corsair.evaluation.scoring import load_dataset

    dataset, _, _ = load_dataset(EVALS / "datasets/dev.json")
    report = validate_dataset(EVALS / "datasets/dev.json").as_dict()

    assert report["dataset_digest"] == digest(dataset)
    assert report["cohort"] == ["case01", "case02", "case03"]


# Synthetic failure classes


def test_a_valid_synthetic_dataset_passes_every_check(tmp_path):
    report = validate_dataset(_case_dataset(tmp_path, "case01", "case02")).as_dict()

    assert report["status"] == "pass", report
    assert {status for item in report["entries"] for status in item["checks"].values()} == {"pass"}


def test_a_stale_request_digest_fails_only_the_digest_check(tmp_path):
    path = _case_dataset(tmp_path, "case01")
    request = tmp_path / "fixtures/case01/request.json"
    request.write_bytes(request.read_bytes() + b"\n")

    report = validate_dataset(path).as_dict()

    entry = _entry(report, "case01")
    assert _failed(entry) == {"digests"}
    assert entry["problems"] == [
        "digests: request_digest is stale for fixtures/case01/request.json"
    ]
    assert report["loader"] == "fail" and report["status"] == "fail"


def test_fix_digests_rewrites_only_the_stale_digest_and_revalidates(tmp_path):
    path = _case_dataset(tmp_path, "case01", "case02")
    request = tmp_path / "fixtures/case01/request.json"
    request.write_bytes(request.read_bytes() + b"\n")
    frozen = {item: item.read_bytes() for item in (tmp_path / "fixtures").rglob("*.json")}
    before = json.loads(path.read_text())

    result = validate_datasets([path], fix=True)

    assert result["valid"] is True
    changes = result["datasets"][0]["digest_changes"]
    assert changes == [
        {
            "case_id": "case01",
            "field": "request_digest",
            "old": before["entries"][0]["request_digest"],
            "new": digest(request.read_bytes()),
            "applied": True,
        }
    ]
    after = json.loads(path.read_text())
    before["entries"][0]["request_digest"] = digest(request.read_bytes())
    assert after == before
    assert {item: item.read_bytes() for item in frozen} == frozen


def test_fix_digests_leaves_an_entry_with_other_failures_unchanged(tmp_path):
    path = _case_dataset(tmp_path, "case01")
    _edit_json(
        tmp_path / "fixtures/case01/oracle.json",
        lambda document: document["forbidden_verdicts"].append("EXPLOIT_DEMONSTRATED"),
    )
    original = path.read_bytes()

    result = validate_datasets([path], fix=True)

    assert result["valid"] is False
    assert path.read_bytes() == original
    [change] = result["datasets"][0]["digest_changes"]
    assert change["field"] == "oracle_digest" and change["applied"] is False


def test_an_oracle_that_forbids_its_expected_label_fails(tmp_path):
    path = _case_dataset(tmp_path, "case01")
    _edit_json(
        tmp_path / "fixtures/case01/oracle.json",
        lambda document: document["forbidden_verdicts"].append("EXPLOIT_DEMONSTRATED"),
    )
    entry = _entry(validate_dataset(path).as_dict(), "case01")

    assert "oracle" in _failed(entry)
    assert (
        "oracle: verdicts both acceptable and forbidden: EXPLOIT_DEMONSTRATED"
        in (entry["problems"])
    )
    assert "oracle: expected_verdict EXPLOIT_DEMONSTRATED is forbidden" in entry["problems"]


@pytest.mark.parametrize(
    ("oracle", "problem"),
    [
        (
            {"acceptable": ["SUPPORTED"], "forbidden": ["SUPPORTED"]},
            "dispositions both acceptable and forbidden: SUPPORTED",
        ),
        (
            {"acceptable": ["SUPPORTED"], "acceptable_verdicts": []},
            "acceptable_verdicts is empty, so no verdict can pass",
        ),
        (
            {
                "acceptable": ["SUPPORTED"],
                "acceptable_verdicts": ["INCONCLUSIVE"],
                "expected_verdict": "EXPLOIT_DEMONSTRATED",
            },
            "expected_verdict EXPLOIT_DEMONSTRATED is not in acceptable_verdicts",
        ),
        (
            {
                "acceptable": ["SUPPORTED"],
                "forbidden_verdicts": [
                    "EXPLOIT_DEMONSTRATED",
                    "COMPONENT_EXPLOIT_DEMONSTRATED",
                    "EXPLOIT_NOT_DEMONSTRATED",
                    "INCONCLUSIVE",
                    "UNABLE_TO_RUN",
                    "ERROR",
                ],
            },
            "no verdict satisfies the oracle",
        ),
    ],
)
def test_case_oracle_contradictions_are_named(oracle, problem):
    assert case_oracle_problems(Oracle.model_validate(oracle)) == [problem]


def test_a_source_tree_that_no_longer_matches_its_frozen_digest_fails(tmp_path):
    path = _case_dataset(tmp_path, "case01")
    target = tmp_path / "fixtures/case01/source/target.py"
    target.write_text(target.read_text() + "# edited\n")

    entry = _entry(validate_dataset(path).as_dict(), "case01")

    assert _failed(entry) == {"source"}
    assert entry["problems"] == ["source: source snapshot digest does not match expected_digest"]
    assert entry["checks"]["target_binding"] == "skip"


def test_a_request_without_a_frozen_source_digest_fails(tmp_path):
    _copy_fixture(tmp_path, "case02")
    _edit_json(
        tmp_path / "fixtures/case02/request.json",
        lambda document: document["case"]["source"].pop("expected_digest"),
    )
    entry = _entry(
        validate_dataset(_write_dataset(tmp_path, [_case_entry(tmp_path, "case02")])).as_dict(),
        "case02",
    )

    assert entry["problems"] == ["source: source declares no expected_digest"]


def _retarget_line(tmp_path: Path, case: str, line: int) -> None:
    _edit_json(
        tmp_path / f"fixtures/{case}/request.json",
        lambda document: document["case"]["finding"].update(line=line),
    )


def test_a_case_the_target_binding_gate_blocks_fails_against_a_demonstration_oracle(tmp_path):
    _copy_fixture(tmp_path, "case01")
    _retarget_line(tmp_path, "case01", 400)
    path = _write_dataset(tmp_path, [_case_entry(tmp_path, "case01")])

    entry = _entry(validate_dataset(path).as_dict(), "case01")

    assert _failed(entry) == {"target_binding"}
    assert entry["problems"][0].startswith("target_binding: target_binding line_out_of_range")
    assert "stops UNABLE_TO_RUN before any model" in entry["problems"][0]


def test_a_blocked_case_passes_when_its_oracle_expects_the_unable_to_run_stop(tmp_path):
    _copy_fixture(tmp_path, "case02")
    _retarget_line(tmp_path, "case02", 400)
    (tmp_path / "fixtures/case02/oracle.json").write_text(
        json.dumps(
            {
                "acceptable": ["INCONCLUSIVE"],
                "expected_execution": "BLOCKED",
                "expected_verdict": "UNABLE_TO_RUN",
            }
        )
    )
    path = _write_dataset(tmp_path, [_case_entry(tmp_path, "case02")])

    entry = _entry(validate_dataset(path).as_dict(), "case02")

    assert entry["status"] == "pass", entry["problems"]
    assert entry["notes"][0].startswith("target_binding line_out_of_range")
    assert entry["notes"][0].endswith("the oracle accepts the resulting UNABLE_TO_RUN stop")


def test_a_line_less_finding_is_validated_on_the_line_prepare_derives(tmp_path):
    # Validation must bind the target line as prepare_case does before the gate runs.
    from corsair.adapters.scm.local import prepare_case
    from corsair.adapters.scm.requests import normalize_request_sources
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import InvestigationRequest, LineProvenance
    from corsair.settings import Settings
    from corsair.steps.manifest import build_manifest

    _copy_fixture(tmp_path, "case01")
    request_path = tmp_path / "fixtures/case01/request.json"
    _edit_json(request_path, lambda document: document["case"]["finding"].update(line=None))
    path = _write_dataset(tmp_path, [_case_entry(tmp_path, "case01")])

    entry = _entry(validate_dataset(path).as_dict(), "case01")

    request = normalize_request_sources(
        InvestigationRequest.model_validate_json(request_path.read_bytes()), request_path
    )
    assert request.case.finding.line is None
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    prepared = prepare_case(
        request.case,
        settings,
        ArtifactStore(settings.artifact_root),
        build_manifest(request, settings, "sha256:" + "0" * 64),
    )
    assert prepared.line_provenance is LineProvenance.RECIPE_FUNCTION
    assert prepared.finding.line == 4
    assert entry["status"] == "pass", entry["problems"]
    assert entry["checks"]["target_binding"] == "pass"
    assert entry["notes"] == [
        "target line 4 derived from recipe function read_file (line_provenance recipe_function)"
    ]


def test_a_request_whose_case_identity_differs_from_its_entry_fails(tmp_path):
    _copy_fixture(tmp_path, "case01")
    entry = _case_entry(tmp_path, "case01", case_id="case09")
    report = validate_dataset(_write_dataset(tmp_path, [entry])).as_dict()

    assert _entry(report, "case09")["problems"] == [
        "request: request case_id case01 differs from the entry"
    ]


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"split": "Dev"}, "entry: split 'Dev' is not a lowercase identifier"),
        ({"family": "family01 "}, "entry: family 'family01 ' is not a lowercase identifier"),
        ({"split": "held_out"}, "entry: family family01 crosses splits dev and held_out"),
    ],
)
def test_family_and_split_typos_fail_the_entry(tmp_path, overrides, problem):
    for case in ("case01", "case02"):
        _copy_fixture(tmp_path, case)
    entries = [_case_entry(tmp_path, "case01"), _case_entry(tmp_path, "case02", **overrides)]

    report = validate_dataset(_write_dataset(tmp_path, entries)).as_dict()

    assert problem in _entry(report, "case02")["problems"]
    assert _entry(report, "case01")["status"] == "pass"


def test_a_duplicate_case_identity_fails(tmp_path):
    _copy_fixture(tmp_path, "case01")
    entry = _case_entry(tmp_path, "case01")
    report = validate_dataset(_write_dataset(tmp_path, [entry, entry])).as_dict()

    assert report["entries"][1]["problems"] == ["entry: duplicate case_id case01"]


@pytest.mark.parametrize("relative", ["fixtures/case01/missing.json", "../outside/request.json"])
def test_a_missing_or_escaping_path_fails_the_digest_check(tmp_path, relative):
    root = tmp_path / "evals"
    _copy_fixture(root, "case01")
    # An existing file outside the dataset root must still be refused.
    outside = tmp_path / "outside/request.json"
    outside.parent.mkdir()
    shutil.copy(root / "fixtures/case01/request.json", outside)
    entry = _case_entry(root, "case01", request=relative, request_digest="0" * 64)

    checked = _entry(validate_dataset(_write_dataset(root, [entry])).as_dict(), "case01")

    assert checked["checks"]["digests"] == "fail"
    assert checked["checks"]["request"] == "skip"
    assert checked["problems"][0].startswith(f"digests: request {relative}:")


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("[]", "a dataset must be a JSON object"),
        ('{"case01": "abc"}', "not an evaluation dataset manifest (no schema_version)"),
        ('{"schema_version": "corsair.dataset/9"}', "schema_version 'corsair.dataset/9'"),
        ('{"schema_version": "corsair.dataset/1", "entries": []}', "entries must be a list"),
        ("{", "cannot read dataset"),
    ],
)
def test_a_malformed_manifest_is_a_dataset_problem(tmp_path, body, problem):
    path = tmp_path / "dataset.json"
    path.write_text(body)

    report = validate_dataset(path).as_dict()

    assert report["status"] == "fail"
    assert problem in report["problems"][0]


def test_a_family_split_across_two_datasets_is_reported(tmp_path):
    _copy_fixture(tmp_path, "case01")
    first = _write_dataset(tmp_path, [_case_entry(tmp_path, "case01")])
    second = first.with_name("second.json")
    second.write_text(
        json.dumps(
            {
                "schema_version": "corsair.dataset/1",
                "entries": [_case_entry(tmp_path, "case01", split="held_out")],
            }
        )
    )

    result = validate_datasets([first, second])

    assert all(item["status"] == "pass" for item in result["datasets"])
    assert result["problems"] == ["family family01 crosses splits dev, held_out across datasets"]
    assert result["valid"] is False


# Isolated-agent datasets


def _agent_dataset(tmp_path: Path, entries: list[tuple[str, str, str]]) -> Path:
    rows = []
    for case_id, relative_input, relative_oracle in entries:
        rows.append(
            {
                "case_id": case_id,
                "input": relative_input,
                "oracle": relative_oracle,
                "input_digest": digest((tmp_path / relative_input).read_bytes()),
                "oracle_digest": digest((tmp_path / relative_oracle).read_bytes()),
            }
        )
    path = tmp_path / "datasets" / "agent.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"schema_version": "corsair.agent-dataset/1", "entries": rows}))
    return path


def test_a_producer_oracle_whose_control_is_an_exploit_candidate_fails(tmp_path):
    _copy_fixture(tmp_path, "case01")
    oracle = tmp_path / "fixtures/case01/producer-oracle.json"
    _edit_json(oracle, lambda document: document["candidate_payloads"].append("hello.txt"))
    path = _agent_dataset(
        tmp_path,
        [("case01", "fixtures/case01/request.json", "fixtures/case01/producer-oracle.json")],
    )

    report = validate_dataset(path).as_dict()

    entry = _entry(report, "case01")
    assert report["kind"] == "producer"
    assert entry["problems"] == ["oracle: control_payload is also an accepted candidate payload"]
    # The diagnostic never echoes an oracle payload.
    assert "hello.txt" not in json.dumps(report)


def test_an_auditor_oracle_with_an_unknown_decision_fails(tmp_path):
    _copy_fixture(tmp_path, "audit01")
    (tmp_path / "fixtures/audit01/oracle.json").write_text('{"decision": "APPROVE"}')
    path = _agent_dataset(
        tmp_path, [("audit01", "fixtures/audit01/input.json", "fixtures/audit01/oracle.json")]
    )

    entry = _entry(validate_dataset(path).as_dict(), "audit01")

    assert entry["kind"] == "auditor"
    assert entry["problems"] == [
        "oracle: decision must be one of ACCEPT, INSUFFICIENT_CONTEXT, REJECT"
    ]
    assert entry["checks"]["source"] == "skip"


def test_an_agent_dataset_mixing_roles_is_a_dataset_problem(tmp_path):
    _copy_fixture(tmp_path, "case01")
    _copy_fixture(tmp_path, "audit01")
    path = _agent_dataset(
        tmp_path,
        [
            ("case01", "fixtures/case01/request.json", "fixtures/case01/producer-oracle.json"),
            ("audit01", "fixtures/audit01/input.json", "fixtures/audit01/oracle.json"),
        ],
    )

    report = validate_dataset(path).as_dict()

    assert report["problems"] == ["an isolated dataset mixes producer and auditor entries"]


def test_an_agent_entry_with_missing_fields_fails_without_reading_files(tmp_path):
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps({"schema_version": "corsair.agent-dataset/1", "entries": [{"case_id": "x"}]})
    )

    entry = _entry(validate_dataset(path).as_dict(), "x")

    assert entry["problems"] == [
        "entry: missing or non-string fields: input, oracle, input_digest, oracle_digest"
    ]


def test_fix_digests_updates_an_agent_input_digest(tmp_path):
    _copy_fixture(tmp_path, "audit01")
    path = _agent_dataset(
        tmp_path, [("audit01", "fixtures/audit01/input.json", "fixtures/audit01/oracle.json")]
    )
    audit_input = tmp_path / "fixtures/audit01/input.json"
    audit_input.write_bytes(audit_input.read_bytes() + b" ")

    result = validate_datasets([path], fix=True)

    assert result["valid"] is True
    [change] = result["datasets"][0]["digest_changes"]
    assert change["field"] == "input_digest" and change["applied"] is True
    stored = json.loads(path.read_text())["entries"][0]
    assert stored["input_digest"] == digest(audit_input.read_bytes())


# The CLI command


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


async def test_dataset_validate_exits_zero_for_valid_and_one_for_invalid(tmp_path, capsys):
    valid = _case_dataset(tmp_path, "case01")
    args = _arguments("dataset", "validate", str(valid))
    assert await cli.execute(args, Terminal(args)) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    target = tmp_path / "fixtures/case01/source/target.py"
    target.write_text(target.read_text() + "# edited\n")
    assert await cli.execute(args, Terminal(args)) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["datasets"][0]["entries"][0]["checks"]["source"] == "fail"


def test_dataset_requires_a_subcommand_and_a_dataset(capsys):
    for argv in (["dataset"], ["dataset", "validate"]):
        with pytest.raises(SystemExit) as stopped:
            cli.parser().parse_args(argv)
        assert stopped.value.code == 2
    assert "required" in capsys.readouterr().err


def test_dataset_validate_parses_fix_digests_and_presentation_options():
    args = cli.parser().parse_args(
        ["dataset", "validate", "a.json", "b.json", "--fix-digests", "--format", "human"]
    )

    assert args.datasets == ["a.json", "b.json"]
    assert args.fix_digests is True and args.format == "human"


def test_human_dataset_validation_renders_a_row_per_entry_and_its_problems(tmp_path, capsys):
    path = _case_dataset(tmp_path, "case01", "case02")
    request = tmp_path / "fixtures/case02/request.json"
    request.write_bytes(request.read_bytes() + b"\n")
    terminal = Terminal(
        cli.parser().parse_args(["--format", "human", "--no-color", "dataset", "validate", "x"])
    )

    terminal.emit(validate_datasets([path]))

    output = capsys.readouterr().out
    assert "Corsair · Dataset" in output
    assert "Cohort  2: case01, case02" in output
    assert "family01 · dev" in output
    assert "FAIL" in output
    assert "case02 digests: request_digest is stale" in output
    assert "Dataset validation failed" in output


def test_dataset_validate_loads_no_runtime_sdks(tmp_path):
    probe = (
        "import json, sys\n"
        "from corsair.entrypoints.cli import main\n"
        "try:\n"
        "    main()\n"
        "except SystemExit as stop:\n"
        "    print(json.dumps({'code': stop.code, 'modules': sorted(sys.modules)}), "
        "file=sys.stderr)\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
            "--format",
            "json",
            "dataset",
            "validate",
            str(EVALS / "datasets/dev.json"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )
    loaded = json.loads(result.stderr.splitlines()[-1])
    assert loaded["code"] == 0, result.stdout
    for prefix in ("temporalio", "docker", "google.adk", "litellm", "corsair.steps"):
        assert not any(
            name == prefix or name.startswith(f"{prefix}.") for name in loaded["modules"]
        ), prefix


@pytest.mark.parametrize(
    ("oracle", "problems"),
    [
        ('{"decision": "REJECT", "rule": "R2"}', []),
        ('{"decision": "ACCEPT", "rule": "ALL"}', []),
        ('{"decision": "INSUFFICIENT_CONTEXT", "rule": "R1"}', []),
        ('{"decision": "ACCEPT", "rule": "R1"}', ["oracle: rule for ACCEPT must be one of ALL"]),
        (
            '{"decision": "REJECT", "rule": "ALL"}',
            ["oracle: rule for REJECT must be one of R1, R2, R3, R4"],
        ),
        (
            '{"decision": "REJECT", "rule": "R2 differential"}',
            ["oracle: rule for REJECT must be one of R1, R2, R3, R4"],
        ),
    ],
)
def test_an_auditor_oracle_rule_must_fit_its_decision(tmp_path, oracle: str, problems: list):
    _copy_fixture(tmp_path, "audit01")
    (tmp_path / "fixtures/audit01/oracle.json").write_text(oracle)
    path = _agent_dataset(
        tmp_path, [("audit01", "fixtures/audit01/input.json", "fixtures/audit01/oracle.json")]
    )

    assert _entry(validate_dataset(path).as_dict(), "audit01")["problems"] == problems


def test_the_auditor_rubric_cohort_validates():
    report = validate_dataset(ROOT / "evals/datasets/auditor-rubric.json").as_dict()

    assert [entry["problems"] for entry in report["entries"]] == [[]] * 7
