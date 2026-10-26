"""Scanner intake dry run and its frozen dataset: conversion, admissibility, scoring, CLI.

No model, Temporal or Docker: intake runs the real source admission and the pure
pre-model binding checks only.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from corsair.adapters.scm.local import prepare_case
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import LineProvenance, PythonRecipe, ScannerFinding, Source, digest
from corsair.entrypoints import cli
from corsair.entrypoints.requests import load_recipe_template, request_from_scanner
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation import intake
from corsair.evaluation.comparison import row_label
from corsair.evaluation.intake import (
    FindingIntake,
    admit_source,
    assess_finding,
    assess_findings,
    intake_counts,
    intake_receipt,
    report_findings,
    score_dataset,
)
from corsair.ports.scm import SourceAdmissionError
from corsair.settings import Settings
from tests.unit.test_evidence import _prepared

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
DATASET = EVALS / "datasets/intake.json"
REPORTS = EVALS / "fixtures/scan_reports"
SOURCE_DIR = EVALS / "datasets/intake/reader-source"
TEMPLATE = EVALS / "datasets/intake/recipe-read-file.json"
READER = (SOURCE_DIR / "reader.py").read_bytes()


def _raw(**overrides: object) -> dict[str, object]:
    finding: dict[str, object] = {
        "title": "read_file joins a caller path onto the root",
        "description": "read_file joins the caller's path onto the root.",
        "file": "reader.py",
        "line": 6,
        "scope": {
            "application": "[Library] reader",
            "repositories": [{"name": "reader", "url": "https://example.invalid/reader"}],
        },
    }
    finding.update(overrides)
    return {key: value for key, value in finding.items() if value is not None}


def _template() -> dict[str, object]:
    return load_recipe_template(TEMPLATE)


_DEFAULT = "default"


def _assess(
    raw: object,
    files: dict[str, bytes] | None = None,
    template: Mapping[str, object] | None | Literal["default"] = _DEFAULT,
) -> FindingIntake:
    return assess_finding(
        0,
        raw,
        case_id="intake-000",
        source=Source(path="/src", expected_digest="0" * 64),
        files={"reader.py": READER} if files is None else files,
        recipe_template=_template() if template == _DEFAULT else template,
    )


# conversion (entrypoints/requests.py)


def test_conversion_binds_the_template_to_the_finding_file_and_keeps_the_line():
    finding = ScannerFinding.model_validate(_raw(line=None))
    request = request_from_scanner(
        finding, case_id="c-000", source=Source(path="/src"), recipe_template=_template()
    )
    assert isinstance(request.case.recipe, PythonRecipe)
    assert request.case.recipe.module_file == "reader.py"
    assert request.case.recipe.function == "read_file"
    assert request.case.recipe.payload_parameter == "path"
    assert request.case.finding.line is None  # intake never invents a line
    assert request.case.finding.scanner is not None
    assert request.case.source == Source(path="/src")


def test_conversion_derives_nothing_from_the_finding_narrative():
    """A description naming another function and line changes neither recipe nor line."""
    plain = ScannerFinding.model_validate(_raw(line=None))
    loud = ScannerFinding.model_validate(
        _raw(
            line=None,
            title="exploit() at line 2",
            description="def exploit(path): the bug is on line 2 of reader.py in exploit()",
        )
    )
    built = [
        request_from_scanner(
            finding, case_id="c-000", source=Source(path="/src"), recipe_template=_template()
        )
        for finding in (plain, loud)
    ]
    assert built[0].case.recipe == built[1].case.recipe
    assert built[0].case.finding.line is built[1].case.finding.line is None
    assessed = [_assess(_raw(line=None)), _assess(loud.model_dump(mode="json"))]
    assert assessed[0].outcome == assessed[1].outcome == "admissible:recipe_function"
    assert assessed[0].line == assessed[1].line == 6


def test_recipe_template_may_not_set_module_file(tmp_path):
    template = tmp_path / "recipe.json"
    template.write_text(json.dumps({**_template(), "module_file": "other.py"}))
    with pytest.raises(ValueError, match="may not set module_file"):
        load_recipe_template(template)


@pytest.mark.parametrize(
    "body",
    [
        '["read_file"]',
        '{"function": "read_file"}',
        '{"function": "_private", "payload_parameter": "p"}',
    ],
)
def test_recipe_template_must_be_a_complete_recipe_object(tmp_path, body):
    template = tmp_path / "recipe.json"
    template.write_text(body)
    with pytest.raises((ValueError, ValidationError)):
        load_recipe_template(template)


# assessment (evaluation/intake.py)


def test_a_declared_line_that_binds_is_admissible_with_its_request():
    result = _assess(_raw())
    assert result.outcome == "admissible"
    assert result.line == 6 and result.line_provenance is LineProvenance.DECLARED
    assert result.request is not None and result.request.case.finding.line == 6


def test_a_missing_line_with_a_derivable_recipe_function_is_admissible_with_derivation():
    result = _assess(_raw(line=None))
    assert result.outcome == "admissible:recipe_function"
    assert result.line == 6 and result.line_provenance is LineProvenance.RECIPE_FUNCTION
    # The candidate request stays line-less: prepare derives the same line again.
    assert result.request is not None and result.request.case.finding.line is None


def test_intake_derives_the_line_prepare_derives(tmp_path):
    result = _assess(_raw(line=None))
    assert result.request is not None
    settings = Settings(source_root=str(EVALS), artifact_root=str(tmp_path / "artifacts"))
    case = result.request.case.model_copy(update={"source": Source(path=str(SOURCE_DIR.resolve()))})
    prepared = prepare_case(
        case, settings, ArtifactStore(settings.artifact_root), _prepared().manifest
    )
    assert prepared.finding.line == result.line
    assert prepared.line_provenance is result.line_provenance


@pytest.mark.parametrize(
    "raw,files,template,outcome",
    [
        (_raw(file="../outside/reader.py"), None, "default", "blocked:path_unsafe"),
        (_raw(file="/srv/reader.py"), None, "default", "blocked:path_unsafe"),
        (_raw(title=None), None, "default", "blocked:finding_invalid"),
        ("not a finding", None, "default", "blocked:finding_invalid"),
        (_raw(file="server.mjs"), None, "default", "blocked:unsupported_language"),
        (_raw(file="vendor/missing.py"), None, "default", "blocked:file_absent"),
        (_raw(), {"reader.py": b"\xff\xfe"}, "default", "blocked:source_not_utf8"),
        (_raw(), None, None, "blocked:recipe_missing"),
        (
            _raw(),
            None,
            {"function": "read_file", "payload_parameter": "root", "fixed_kwargs": {"root": "/"}},
            "blocked:recipe_invalid",
        ),
        (_raw(line=40), None, "default", "blocked:line_out_of_range"),
        (
            _raw(file="helpers.py", line=5),
            {"helpers.py": READER.replace(b"read_file", b"other")},
            "default",
            "blocked:function_not_defined",
        ),
        (
            _raw(file="cached.py", line=None),
            {"cached.py": (SOURCE_DIR / "cached.py").read_bytes()},
            "default",
            "blocked:line_missing",
        ),
    ],
)
def test_each_blocked_reason_is_named(raw, files, template, outcome):
    result = _assess(raw, files, template)
    assert result.outcome == outcome
    assert result.request is None and not result.admissible
    assert result.detail


def test_a_blocked_finding_keeps_its_declared_line_for_reading():
    result = _assess(_raw(file="vendor/missing.py", line=3))
    assert result.outcome == "blocked:file_absent" and result.line == 3


def test_counts_name_admissible_derived_and_blocked_reasons():
    raws = [_raw(), _raw(line=None), _raw(line=40), _raw(line=41), _raw(file="x.mjs")]
    intakes = assess_findings(
        raws,
        report_stem="report",
        source=Source(path="/src"),
        files={"reader.py": READER},
        recipe_template=_template(),
    )
    assert [item.request.case.case_id for item in intakes if item.request] == [
        "report-000",
        "report-001",
    ]
    assert intake_counts(intakes) == {
        "findings": 5,
        "admissible": 2,
        "admissible_derived_line": 1,
        "blocked": 3,
        "blocked_reasons": {"line_out_of_range": 2, "unsupported_language": 1},
    }


@pytest.mark.parametrize(
    "body,match",
    [
        (b"[]", "JSON object"),
        (b'{"scan_completed": true, "vulnerabilities_found": true, "findings": {}}', "list"),
        (
            b'{"schema_version": "other/1", "scan_completed": true, "vulnerabilities_found": true}',
            "schema_version",
        ),
        (
            json.dumps(
                {"scan_completed": True, "vulnerabilities_found": True, "findings": [{}] * 257}
            ).encode(),
            "at most 256",
        ),
    ],
)
def test_a_malformed_report_envelope_fails_the_whole_report(body, match):
    with pytest.raises((ValueError, ValidationError), match=match):
        report_findings(body)


def test_source_admission_pins_the_snapshot_digest_and_refuses_a_changed_tree():
    settings = Settings(source_root=str(EVALS))
    source, files = admit_source(SOURCE_DIR, settings)
    assert set(files) == {"cached.py", "helpers.py", "reader.py"}
    dataset = json.loads(DATASET.read_bytes())
    assert {entry["source_digest"] for entry in dataset["entries"]} == {source.expected_digest}
    with pytest.raises(SourceAdmissionError, match="expected_digest"):
        admit_source(SOURCE_DIR, settings, expected_digest="0" * 64)
    with pytest.raises(SourceAdmissionError, match="outside configured source_root"):
        admit_source(SOURCE_DIR, Settings(source_root=str(REPORTS)))


def test_intake_receipt_flags_a_report_the_envelope_loader_would_reject():
    receipt, intakes = intake_receipt(
        REPORTS / "python-reader-path-escape.json",
        SOURCE_DIR,
        Settings(source_root=str(EVALS)),
        TEMPLATE,
    )
    assert receipt["intake"]["report_admitted"] is False
    assert [item.outcome for item in intakes] == [
        "blocked:path_unsafe",
        "blocked:path_unsafe",
        "admissible",
    ]
    assert receipt["findings"][2]["request"]["case"]["recipe"]["module_file"] == "reader.py"
    assert receipt["findings"][0]["request"] is None


# frozen dataset (evals/datasets/intake.json)


def test_the_frozen_intake_dataset_scores_every_finding_against_its_oracle():
    report = score_dataset(DATASET)
    summary = report["summary"]
    assert (summary["attempts"], summary["passed"], summary["failed"]) == (12, 12, 0)
    assert (summary["admissible"], summary["admissible_derived_line"], summary["blocked"]) == (
        3,
        1,
        9,
    )
    assert summary["llm_calls"] == summary["tool_calls"] == 0
    assert summary["gate_ledger"]["blocked:path_unsafe"] == 2
    assert {row["case_id"] for row in report["rows"]} >= {
        "scan-reader-no-line.0",
        "scan-reader-mixed.4",
    }
    covered = {row["intake"] for row in report["rows"]}
    for outcome in (
        "admissible",
        "admissible:recipe_function",
        "blocked:line_missing",
        "blocked:file_absent",
        "blocked:function_not_defined",
        "blocked:path_unsafe",
    ):
        assert outcome in covered
    assert report["dataset_digest"] == digest(
        intake.IntakeDataset.model_validate_json(DATASET.read_bytes())
    )


def _copied_dataset(tmp_path: Path) -> Path:
    """A writable copy of the evals tree the intake dataset addresses."""
    root = tmp_path / "evals"
    shutil.copytree(EVALS / "datasets/intake", root / "datasets/intake")
    shutil.copytree(REPORTS, root / "fixtures/scan_reports")
    shutil.copy(DATASET, root / "datasets/intake.json")
    return root / "datasets/intake.json"


def _redigest_oracle(dataset: Path, case_id: str, expected: list[str]) -> None:
    oracle = dataset.parent / f"intake/oracles/{case_id}.json"
    oracle.write_text(json.dumps({"expected": expected}))
    manifest = json.loads(dataset.read_text())
    for entry in manifest["entries"]:
        if entry["case_id"] == case_id:
            entry["oracle_digest"] = digest(oracle.read_bytes())
    dataset.write_text(json.dumps(manifest))


def test_report_rows_label_by_their_intake_outcome():
    [row, *_] = score_dataset(DATASET)["rows"]
    assert row_label(row) == row["intake"] == "blocked:unsupported_language"


def test_a_disagreeing_oracle_fails_its_row(tmp_path):
    dataset = _copied_dataset(tmp_path)
    _redigest_oracle(dataset, "scan-reader-no-line", ["blocked:line_missing"])
    report = score_dataset(dataset)
    [row] = [row for row in report["rows"] if row["case_id"] == "scan-reader-no-line.0"]
    assert row["status"] == "fail" and row["intake"] == "admissible:recipe_function"
    assert report["summary"]["failure_stops"] == {"admissible:recipe_function": 1}


def test_an_oracle_for_a_different_number_of_findings_is_a_dataset_error(tmp_path):
    dataset = _copied_dataset(tmp_path)
    _redigest_oracle(dataset, "scan-reader-no-line", ["admissible", "admissible"])
    with pytest.raises(ValueError, match="2 outcomes for 1 findings"):
        score_dataset(dataset)


def test_a_changed_frozen_report_or_source_is_refused(tmp_path):
    dataset = _copied_dataset(tmp_path)
    report = dataset.parent.parent / "fixtures/scan_reports/python-reader-mixed.json"
    report.write_text(report.read_text().replace('"line": 40', '"line": 4'))
    with pytest.raises(ValueError, match="frozen report digest changed"):
        score_dataset(dataset)
    shutil.copy(REPORTS / "python-reader-mixed.json", report)
    (dataset.parent / "intake/reader-source/reader.py").write_text("def read_file(root, path):\n")
    with pytest.raises(SourceAdmissionError, match="expected_digest"):
        score_dataset(dataset)


def test_the_dataset_runner_saves_a_report_and_exits_zero(tmp_path, monkeypatch, capsys):
    output = tmp_path / "intake-report.json"
    # main() installs process-wide log handlers; keep them out of other tests.
    monkeypatch.setattr(intake, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["intake", str(DATASET), "--output", str(output)])
    with pytest.raises(SystemExit) as stopped:
        intake.main()
    assert stopped.value.code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["report"] == str(output)
    saved = json.loads(output.read_text())
    assert saved["summary"]["failed"] == 0 and len(saved["rows"]) == 12


# CLI (corsair intake)


def _arguments(*argv: str, output: str = "json") -> cli.CliArguments:
    return cli.parser().parse_args(["--format", output, *argv], namespace=cli.CliArguments())


def _settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(Settings(source_root=str(EVALS)).model_dump_json())
    return path


def _intake_args(tmp_path: Path, report: str, *extra: str, output: str = "json"):
    return _arguments(
        "intake",
        str(REPORTS / report),
        "--source-root",
        str(SOURCE_DIR),
        "--settings",
        str(_settings_file(tmp_path)),
        *extra,
        output=output,
    )


async def test_cli_intake_exits_zero_when_every_finding_is_admissible(tmp_path, capsys):
    args = _intake_args(tmp_path, "python-reader-no-line.json", "--recipe-template", str(TEMPLATE))
    assert await cli.execute(args, Terminal(args)) == 0
    receipt = json.loads(capsys.readouterr().out)
    [finding] = receipt["findings"]
    assert finding["outcome"] == "admissible:recipe_function"
    assert finding["line"] == 6 and finding["line_provenance"] == "recipe_function"
    assert (
        finding["request"]["case"]["source"]["expected_digest"]
        == receipt["intake"]["source_digest"]
    )
    assert receipt["counts"]["admissible_derived_line"] == 1


async def test_cli_intake_exits_one_and_names_each_blocked_reason(tmp_path, capsys):
    args = _intake_args(tmp_path, "python-reader-mixed.json", "--recipe-template", str(TEMPLATE))
    assert await cli.execute(args, Terminal(args)) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert [finding["outcome"] for finding in receipt["findings"]] == [
        "admissible",
        "blocked:line_missing",
        "blocked:file_absent",
        "blocked:function_not_defined",
        "blocked:line_out_of_range",
    ]
    assert receipt["intake"]["report_admitted"] is True


async def test_cli_intake_human_table_marks_derived_lines_and_missing_recipes(tmp_path, capsys):
    args = _intake_args(tmp_path, "python-reader-no-line.json", output="human")
    args.no_color = True
    assert await cli.execute(args, Terminal(args)) == 1
    out = capsys.readouterr().out
    assert "blocked:recipe_missing" in out
    assert "--recipe-template" in out
    args = _intake_args(
        tmp_path, "python-reader-no-line.json", "--recipe-template", str(TEMPLATE), output="human"
    )
    args.no_color = True
    assert await cli.execute(args, Terminal(args)) == 0
    out = capsys.readouterr().out
    assert "admissible:recipe_function" in out and "6 (derived)" in out
    assert "1 of 1 finding(s) admissible" in out


def test_cli_intake_requires_a_source_root():
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["intake", "report.json"])


async def test_cli_intake_refuses_a_source_outside_the_settings_source_root(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(Settings(source_root=str(tmp_path)).model_dump_json())
    args = _arguments(
        "intake",
        str(REPORTS / "python-reader-no-line.json"),
        "--source-root",
        str(SOURCE_DIR),
        "--settings",
        str(settings),
    )
    with pytest.raises(SourceAdmissionError, match="outside configured source_root"):
        await cli.execute(args, Terminal(args))


def test_dataset_validate_checks_intake_rows_and_fixes_only_a_stale_digest(tmp_path):
    from corsair.evaluation.datasets import validate_dataset, validate_datasets

    dataset = _copied_dataset(tmp_path)
    assert validate_dataset(dataset).valid
    _redigest_oracle(dataset, "scan-reader-no-line", ["admissible", "admissible"])
    oracle_count = validate_dataset(dataset).as_dict()
    [row] = [
        entry for entry in oracle_count["entries"] if entry["case_id"] == "scan-reader-no-line"
    ]
    assert row["checks"]["oracle"] == "fail"
    _redigest_oracle(dataset, "scan-reader-no-line", ["admissible:recipe_function"])
    report = dataset.parent.parent / "fixtures/scan_reports/python-reader-mixed.json"
    report.write_text(report.read_text() + "\n")
    stale = validate_dataset(dataset).as_dict()
    [row] = [entry for entry in stale["entries"] if entry["case_id"] == "scan-reader-mixed"]
    assert row["checks"]["digests"] == "fail" and stale["status"] == "fail"
    assert validate_datasets([dataset], fix=True)["valid"] is True
