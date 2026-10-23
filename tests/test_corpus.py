"""Evaluator-only corpus metadata stays strict and outside every agent boundary."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair import corpus as corpus_module, matrix
from corsair.auditor import render as render_auditor
from corsair.case import Case, GitSource, load_case, tree_sha256
from corsair.corpus import (DatasetManifest, _cached_evidence, _patch_sha256, _region_sha256, load_manifest,
                            main as corpus_main, select_cases, validate_corpus)
from corsair.kernel import Submission
from corsair.matrix import select
from corsair.producer import render_case
from corsair.benchmark import (ReplayRecord, TechnicalReviewRecord, admission_status,
                               admission_from_manifest, case_revision_sha256, executor_sha256,
                               publish_receipt, receipt_bytes, runtime_row_sha256)


ROOT = Path(__file__).resolve().parents[1]
VALID_CORPUS = ROOT / "tests/fixtures/corpus/valid"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
COMMIT_A = "1" * 40
COMMIT_B = "2" * 40


def dataset_case(*, case_id: str = "cs-1001", family_id: str = "cf-1001",
                 variant_id: str | None = None, split: str = "development",
                 status: str = "candidate", runtime: str = "python-3.12") -> dict:
    return {
        "case_id": case_id,
        "family_id": family_id,
        "variant_id": variant_id,
        "split": split,
        "status": status,
        "language": "python",
        "runtime": runtime,
        "runtime_image_id": "sha256:" + "c" * 64,
        "package": "example-package",
        "framework": "example-framework",
        "execution_mode": "method",
        "vulnerability_types": ["path-traversal"],
        "cwes": ["CWE-22"],
        "capability_tags": ["filesystem"],
        "risk_tags": ["local-read"],
        "aliases": ["CVE-2026-1001"],
        "finding_provenance": {
            "author": "Corsair benchmark maintainers",
            "source_url": "https://github.com/X-McKay/corsair",
            "source_revision": COMMIT_A,
            "sha256": SHA_A,
        },
        "source_pair": {
            "vulnerable": {
                "repository": "https://github.com/example/project.git",
                "commit": COMMIT_A,
                "tree_sha256": SHA_A,
                "affected_file_sha256": SHA_B,
                "affected_region_sha256": SHA_C,
            },
            "fixed": {
                "repository": "https://github.com/example/project.git",
                "commit": COMMIT_B,
                "tree_sha256": SHA_B,
                "affected_file_sha256": SHA_C,
                "affected_region_sha256": SHA_A,
            },
            "patch_sha256": SHA_C,
        },
        "target": {"file": "src/example.py", "symbol": "read_file", "lines": [10, 11]},
        "expected": {
            "vulnerable": {"label": "LIKELY_EXPLOITABLE", "reason_code": "EXPLOIT_EXPECTATION_MET"},
            "fixed": {"label": "LIKELY_NOT_EXPLOITABLE", "reason_code": "INVARIANT_PRESERVED"},
            "fix": "verified",
        },
        "allowed_variations": [],
        "artifacts": {
            "input_sha256": SHA_A,
            "oracle_sha256": SHA_B,
            "reference_submission_sha256": SHA_C,
        },
        "visibility": "public",
        "retention": "permanent",
        "redaction": "metadata_only",
        "rights": [{
            "layer": "target_source",
            "license_expression": "Apache-2.0",
            "evidence_url": "https://github.com/example/project/blob/1111111111111111111111111111111111111111/LICENSE",
            "evidence_revision": COMMIT_A,
            "evidence_sha256": SHA_A,
            "notice_requirements": ["retain LICENSE"],
            "redistribution_mode": "acquisition_recipe",
            "reviewer": "license-reviewer",
            "reviewed_at": "2026-10-23",
        }],
        "review_receipt": None,
        "replay_receipts": [],
    }


def manifest(*cases: dict) -> dict:
    return {"schema": "corsair-lite/dataset-manifest/1", "dataset_version": "0.1.0", "cases": list(cases)}


def replay_record(case, *, run_id="qualification-1", attempt=1, outcome="complete") -> ReplayRecord:
    revision = case_revision_sha256(case)
    return ReplayRecord.model_validate({
        "schema": "corsair-lite/qualification-replay/1",
        "qualification_run_id": run_id,
        "attempt": attempt,
        "case_id": case.case_id,
        "family_id": case.family_id,
        "dataset_version": "0.1.0",
        "manifest_sha256": SHA_A,
        "case_revision_sha256": revision,
        "input_sha256": case.artifacts.input_sha256,
        "oracle_sha256": case.artifacts.oracle_sha256,
        "reference_submission_sha256": case.artifacts.reference_submission_sha256,
        "vulnerable_tree_sha256": case.source_pair.vulnerable.tree_sha256,
        "fixed_tree_sha256": case.source_pair.fixed.tree_sha256,
        "runtime_row": case.runtime,
        "runtime_row_sha256": SHA_B,
        "runtime_image_id": "sha256:" + "c" * 64,
        "executor_sha256": SHA_C,
        "started_at": "2026-10-23T10:00:00Z",
        "finished_at": "2026-10-23T10:00:01Z",
        "gate": "verified" if outcome == "complete" else "infra",
        "source_label": "LIKELY_EXPLOITABLE" if outcome == "complete" else None,
        "fixed_label": "LIKELY_NOT_EXPLOITABLE" if outcome == "complete" else None,
        "fix": "verified" if outcome == "complete" else None,
        "dispositions": ([
            {"revision": "vulnerable", "label": "LIKELY_EXPLOITABLE", "rule": "K1",
             "reason_code": "EXPLOIT_EXPECTATION_MET"},
            {"revision": "fixed", "label": "LIKELY_NOT_EXPLOITABLE", "rule": "K4",
             "reason_code": "INVARIANT_PRESERVED"},
        ] if outcome == "complete" else []),
        "roles": ([
            {"revision": "vulnerable", "role": "control", "result": "PASS", "invariant_held": True,
             "exception_type": None, "exit_code": 0, "junit_tests": 1, "covered_target": True,
             "covered_lines": list(case.target.lines), "cleanup_confirmed": True,
             "output": {"sha256": SHA_A, "size": 1}, "junit": {"sha256": SHA_B, "size": 1},
             "coverage": {"sha256": SHA_C, "size": 1}},
            {"revision": "vulnerable", "role": "exploit", "result": "PASS", "invariant_held": False,
             "exception_type": None, "exit_code": 0, "junit_tests": 1, "covered_target": True,
             "covered_lines": list(case.target.lines), "cleanup_confirmed": True,
             "output": {"sha256": SHA_A, "size": 1}, "junit": {"sha256": SHA_B, "size": 1},
             "coverage": {"sha256": SHA_C, "size": 1}},
            {"revision": "fixed", "role": "control", "result": "PASS", "invariant_held": True,
             "exception_type": None, "exit_code": 0, "junit_tests": 1, "covered_target": True,
             "covered_lines": list(case.target.lines_for("fixed")), "cleanup_confirmed": True,
             "output": {"sha256": SHA_A, "size": 1}, "junit": {"sha256": SHA_B, "size": 1},
             "coverage": {"sha256": SHA_C, "size": 1}},
            {"revision": "fixed", "role": "exploit", "result": "FAIL", "invariant_held": True,
             "exception_type": None, "exit_code": 1, "junit_tests": 1, "covered_target": True,
             "covered_lines": list(case.target.lines_for("fixed")), "cleanup_confirmed": True,
             "output": {"sha256": SHA_A, "size": 1}, "junit": {"sha256": SHA_B, "size": 1},
             "coverage": {"sha256": SHA_C, "size": 1}},
        ] if outcome == "complete" else []),
        "cleanup_confirmed": outcome == "complete",
        "outcome": outcome,
        "failure_code": None if outcome == "complete" else "SANDBOX_INFRASTRUCTURE",
        "audit_mode": "trusted_reference",
    })


def family_review(*cases) -> TechnicalReviewRecord:
    return TechnicalReviewRecord.model_validate({
        "schema": "corsair-lite/technical-review/1",
        "family_id": cases[0].family_id,
        "variants": [{"case_id": case.case_id, "case_revision_sha256": case_revision_sha256(case)}
                     for case in cases],
        "decision": "approved",
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-10-23",
        "finding_reviewed": True,
        "invariant_reviewed": True,
        "payloads_reviewed": True,
        "expected_results_reviewed": True,
        "independence_basis": "Reviewer did not author the finding or reference probe.",
    })


def test_manifest_models_are_strict_frozen_and_load_the_empty_repository_manifest(tmp_path):
    model = DatasetManifest.model_validate(manifest(dataset_case()))
    assert model.cases[0].source_pair.vulnerable.commit == COMMIT_A
    assert model.cases[0].target.lines == (10, 11)
    with pytest.raises(ValidationError, match="frozen"):
        model.dataset_version = "changed"

    unknown = manifest(dataset_case())
    unknown["secret_answer"] = "LIKELY_EXPLOITABLE"
    with pytest.raises(ValidationError, match="secret_answer"):
        DatasetManifest.model_validate(unknown)
    unknown_case = manifest(dataset_case())
    unknown_case["cases"][0]["secret_answer"] = "LIKELY_EXPLOITABLE"
    with pytest.raises(ValidationError, match="secret_answer"):
        DatasetManifest.model_validate(unknown_case)

    shipped = load_manifest(ROOT / "benchmarks/dataset/manifest.json")
    assert shipped.schema_version == "corsair-lite/dataset-manifest/1"
    assert shipped.cases == ()
    assert select_cases(shipped, "release") == ()


def test_target_identity_can_declare_distinct_fixed_revision_lines():
    case = dataset_case()
    case["target"]["fixed_lines"] = [31, 29]

    target = DatasetManifest.model_validate(manifest(case)).cases[0].target

    assert target.lines == (10, 11)
    assert target.fixed_lines == (29, 31)
    assert target.lines_for("vulnerable") == (10, 11)
    assert target.lines_for("fixed") == (29, 31)


def test_corpus_validates_each_source_region_with_its_revision_lines(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    case = data["cases"][0]
    case["target"]["fixed_lines"] = [5]
    case["source_pair"]["fixed"]["affected_region_sha256"] = _region_sha256(
        root / "cases/cs-1001/fixed/target.py", (5,))
    write_manifest(root, data)

    assert checked(root).ok


@pytest.mark.parametrize("redaction", [None, "best_effort", "private"])
def test_manifest_requires_an_explicit_supported_redaction_classification(redaction):
    case = dataset_case()
    if redaction is None:
        case.pop("redaction")
    else:
        case["redaction"] = redaction
    with pytest.raises(ValidationError, match="redaction"):
        DatasetManifest.model_validate(manifest(case))


def test_manifest_rejects_duplicate_case_and_undeclared_family_ids():
    first = dataset_case()
    duplicate_id = dataset_case(case_id="cs-1001", family_id="cf-1002")
    with pytest.raises(ValidationError, match="duplicate case_id"):
        DatasetManifest.model_validate(manifest(first, duplicate_id))

    same_family = dataset_case(case_id="cs-1002")
    with pytest.raises(ValidationError, match="variant_id"):
        DatasetManifest.model_validate(manifest(first, same_family))

    direct = dataset_case(variant_id="direct")
    script = dataset_case(case_id="cs-1001-b", variant_id="script")
    accepted = DatasetManifest.model_validate(manifest(direct, script))
    assert [case.variant_id for case in accepted.cases] == ["direct", "script"]

    repeated_variant = dataset_case(case_id="cs-1001-c", variant_id="direct")
    with pytest.raises(ValidationError, match="duplicate variant_id"):
        DatasetManifest.model_validate(manifest(direct, repeated_variant))


@pytest.mark.parametrize(("field", "value"), [
    ("case_id", "exploit-python-case"),
    ("family_id", "has spaces"),
])
def test_manifest_rejects_invalid_opaque_ids(field, value):
    case = dataset_case()
    case[field] = value
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(manifest(case))


@pytest.mark.parametrize(("path", "value"), [
    (("source_pair", "vulnerable", "commit"), "main"),
    (("source_pair", "fixed", "commit"), "abc123"),
    (("source_pair", "patch_sha256"), "not-a-hash"),
    (("artifacts", "oracle_sha256"), "f" * 63),
    (("rights", 0, "evidence_sha256"), "sha256:missing"),
])
def test_manifest_rejects_movable_revisions_and_invalid_hashes(path, value):
    case = dataset_case()
    cursor = case
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(manifest(case))


@pytest.mark.parametrize("url_field", ["source", "evidence", "provenance"])
def test_manifest_json_rejects_every_ascii_control_in_https_urls(url_field):
    for codepoint in (*range(0x20), 0x7f):
        case = dataset_case()
        hostile = f"https://example.invalid/owner/{chr(codepoint)}project"
        if url_field == "source":
            case["source_pair"]["vulnerable"]["repository"] = hostile
        elif url_field == "evidence":
            case["rights"][0]["evidence_url"] = hostile
        else:
            case["finding_provenance"]["source_url"] = hostile
        encoded = json.dumps(manifest(case))
        with pytest.raises(ValidationError, match="HTTPS URL"):
            DatasetManifest.model_validate_json(encoded)


@pytest.mark.parametrize("path_field", ["target", "harness", "receipt"])
def test_manifest_json_rejects_every_ascii_control_in_paths(path_field):
    for codepoint in (*range(0x20), 0x7f):
        case = dataset_case()
        hostile = f"path{chr(codepoint)}name.py"
        if path_field == "target":
            case["target"]["file"] = hostile
        elif path_field == "harness":
            case["artifacts"].update(harness_path=hostile, harness_sha256=SHA_A)
        else:
            case["review_receipt"] = {
                "path": hostile,
                "sha256": SHA_A,
                "reviewer": "reviewer",
                "reviewed_at": "2026-10-23",
            }
        with pytest.raises(ValidationError, match="control"):
            DatasetManifest.model_validate_json(json.dumps(manifest(case)))


def test_request_json_rejects_every_ascii_control_in_source_urls_and_paths():
    commit = "1" * 40
    for codepoint in (*range(0x20), 0x7f):
        control = chr(codepoint)
        with pytest.raises(ValidationError, match="control"):
            corpus_module._Request.model_validate_json(json.dumps({
                "finding": {"title": "t"},
                "source": f"source{control}path",
            }))
        with pytest.raises(ValidationError, match="control"):
            GitSource.model_validate_json(json.dumps({
                "url": f"https://example.invalid/{control}project",
                "commit": commit,
            }))
        with pytest.raises(ValidationError, match="control"):
            GitSource.model_validate_json(json.dumps({
                "url": "https://example.invalid/project",
                "commit": commit,
                "subdir": f"source{control}path",
            }))


def test_repository_and_evidence_normalizers_reject_controls_even_when_both_inputs_are_invalid():
    for codepoint in (*range(0x20), 0x7f):
        control = chr(codepoint)
        repository = f"https://example.invalid/owner/{control}project"
        evidence = f"https://example.invalid/owner/project/blob/{COMMIT_A}/path{control}LICENSE"
        assert corpus_module._normal_repository(repository) is None
        assert not corpus_module._same_repository(repository, repository)
        assert corpus_module._git_url_variants(repository) == ()
        assert not corpus_module._immutable_evidence_url(evidence, COMMIT_A)
        assert corpus_module._evidence_location(evidence, COMMIT_A) is None


@pytest.mark.parametrize(("split", "status"), [
    ("quarantine", "candidate"),
    ("development", "quarantined"),
    ("release", "qualified"),
])
def test_manifest_rejects_invalid_split_status_pairs(split, status):
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(manifest(dataset_case(split=split, status=status)))


def test_selection_uses_only_qualified_cases_and_keeps_family_variants_together():
    conformance = dataset_case(case_id="cs-0001-a", family_id="cf-0001", variant_id="direct",
                               split="conformance", status="qualified")
    conformance["review_receipt"] = {"path": "receipts/cs-0001/review.json", "sha256": SHA_A,
                                     "reviewer": "reviewer", "reviewed_at": "2026-10-23"}
    conformance["replay_receipts"] = [{"path": "receipts/cs-0001/replay-1.json", "sha256": SHA_B,
                                        "attempt": 1}]
    development = deepcopy(conformance)
    development.update(case_id="cs-1001", family_id="cf-1001", variant_id=None, split="development")
    candidate = dataset_case(case_id="cs-1002", family_id="cf-1002", status="candidate")
    model = DatasetManifest.model_validate(manifest(conformance, development, candidate))

    assert [case.case_id for case in select_cases(model, "conformance")] == ["cs-0001-a"]
    assert [case.case_id for case in select_cases(model, "development")] == ["cs-0001-a", "cs-1001"]
    assert [case.case_id for case in select_cases(model, "release")] == ["cs-0001-a", "cs-1001"]
    assert select_cases(model, "regression") == ()


def test_admission_requires_three_complete_replays_and_one_family_review():
    direct = DatasetManifest.model_validate(manifest(
        dataset_case(case_id="cs-1001-a", family_id="cf-1001", variant_id="direct",
                     runtime="pytest-cpython312")
    )).cases[0]
    script_data = dataset_case(case_id="cs-1001-b", family_id="cf-1001", variant_id="script")
    script_data["runtime"] = "pytest-cpython312"
    script = DatasetManifest.model_validate(manifest(script_data)).cases[0]
    review = family_review(direct, script)
    records = tuple(replay_record(direct, attempt=attempt) for attempt in (1, 2, 3))

    assert not admission_status(direct, records[:2], review, family_cases=(direct, script)).ready
    assert admission_status(direct, records, review, family_cases=(direct, script)).ready
    assert not admission_status(
        direct, (records[0], records[1], replay_record(direct, run_id="other", attempt=3)), review,
        family_cases=(direct, script),
    ).ready
    assert not admission_status(
        direct, (records[0], replay_record(direct, attempt=2, outcome="infrastructure"), records[2]), review,
        family_cases=(direct, script),
    ).ready

    incomplete_review = review.model_copy(update={"variants": review.variants[:1]})
    assert not admission_status(direct, records, incomplete_review, family_cases=(direct, script)).ready

    second_author = script.model_copy(update={
        "finding_provenance": script.finding_provenance.model_copy(update={"author": "second-author"})
    })
    author_review = family_review(direct, second_author).model_copy(update={"reviewer": "second-author"})
    assert admission_status(direct, records, author_review,
                            family_cases=(direct, second_author)).code == "REVIEW_NOT_INDEPENDENT"

    attached = direct.model_copy(update={
        "status": "qualified",
        "review_receipt": {"path": "receipts/review.json", "sha256": SHA_A,
                           "reviewer": "independent-reviewer", "reviewed_at": date(2026, 10, 23)},
        "replay_receipts": tuple({"path": f"receipts/replay-{attempt}.json", "sha256": SHA_B,
                                  "attempt": attempt} for attempt in (1, 2, 3)),
    })
    assert case_revision_sha256(attached) == case_revision_sha256(direct)


def test_admission_binds_receipt_coverage_to_each_revision_target_lines():
    data = dataset_case(runtime="pytest-cpython312")
    data["target"]["fixed_lines"] = [29, 31]
    case = DatasetManifest.model_validate(manifest(data)).cases[0]
    records = tuple(replay_record(case, attempt=attempt) for attempt in (1, 2, 3))
    review = family_review(case)

    assert admission_status(case, records, review, family_cases=(case,)).ready

    wrong = tuple(record.model_copy(update={
        "roles": tuple(role.model_copy(update={"covered_lines": case.target.lines})
                       if role.revision == "fixed" else role for role in record.roles)
    }) for record in records)
    assert admission_status(case, wrong, review, family_cases=(case,)).code == "REPLAY_EXPECTATION_MISMATCH"


def test_changed_oracle_invalidates_receipts():
    original = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    records = tuple(replay_record(original, attempt=attempt) for attempt in (1, 2, 3))
    changed = original.model_copy(update={
        "artifacts": original.artifacts.model_copy(update={"oracle_sha256": "d" * 64})
    })

    assert case_revision_sha256(changed) != case_revision_sha256(original)
    assert not admission_status(changed, records, family_review(original), family_cases=(changed,)).ready


@pytest.mark.parametrize("field", ["source", "probe", "runtime", "image"])
def test_changed_source_or_probe_runtime_or_image_invalidates_receipts(field):
    original = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    records = tuple(replay_record(original, attempt=attempt) for attempt in (1, 2, 3))
    if field == "source":
        changed = original.model_copy(update={
            "source_pair": original.source_pair.model_copy(update={
                "vulnerable": original.source_pair.vulnerable.model_copy(update={"tree_sha256": "d" * 64})
            })
        })
    elif field == "probe":
        changed = original.model_copy(update={
            "artifacts": original.artifacts.model_copy(update={"reference_submission_sha256": "d" * 64})
        })
    elif field == "runtime":
        changed = original.model_copy(update={"runtime": "another-runtime-row"})
    else:
        changed = original.model_copy(update={"runtime_image_id": "sha256:" + "d" * 64})

    assert case_revision_sha256(changed) != case_revision_sha256(original)
    assert not admission_status(changed, records, family_review(original), family_cases=(changed,)).ready


def test_receipt_publication_is_exclusive_atomic_and_rejects_symlink_roots(tmp_path):
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    record = replay_record(case)
    receipts = tmp_path / "receipts"
    receipts.mkdir()

    published = publish_receipt(receipts, case_revision_sha256(case), "replay-run-1.json", record)
    original = published.read_bytes()
    with pytest.raises(FileExistsError):
        publish_receipt(receipts, case_revision_sha256(case), "replay-run-1.json",
                        record.model_copy(update={"attempt": 2}))
    assert published.read_bytes() == original
    assert not list(published.parent.glob(".*.tmp"))

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        publish_receipt(linked, case_revision_sha256(case), "replay-run-2.json", record)


def test_receipt_publication_detects_a_directory_swap_without_writing_into_the_replacement(tmp_path, monkeypatch):
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    record = replay_record(case)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    revision = case_revision_sha256(case)
    revision_dir = receipts / revision
    moved = receipts / f"{revision}-moved"
    real_link = corpus_module.os.link

    def swap_then_link(source, destination, **kwargs):
        revision_dir.rename(moved)
        revision_dir.mkdir()
        return real_link(source, destination, **kwargs)

    monkeypatch.setattr("corsair.benchmark.os.link", swap_then_link)
    with pytest.raises(ValueError, match="identity changed"):
        publish_receipt(receipts, revision, "replay-swapped-1.json", record)
    assert not (revision_dir / "replay-swapped-1.json").exists()
    assert not (moved / "replay-swapped-1.json").exists()


def test_receipt_publication_rejects_a_replaced_final_filename_without_deleting_the_replacement(
        tmp_path, monkeypatch):
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    record = replay_record(case)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    revision = case_revision_sha256(case)
    filename = "replay-replaced-1.json"
    final = receipts / revision / filename
    replacement = b"concurrent replacement\n"
    real_open = corpus_module.os.open
    replaced = False

    def replace_then_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal replaced
        if path == filename and dir_fd is not None and flags & os.O_ACCMODE == os.O_RDONLY and not replaced:
            replaced = True
            final.unlink()
            final.write_bytes(replacement)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("corsair.benchmark.os.open", replace_then_open)
    with pytest.raises(ValueError, match="file identity changed"):
        publish_receipt(receipts, revision, filename, record)
    assert replaced and final.read_bytes() == replacement


def test_complete_replay_record_rejects_duplicate_or_inconsistent_role_evidence():
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    data = replay_record(case).model_dump(mode="json", by_alias=True)
    data["roles"][3] = data["roles"][2]
    with pytest.raises(ValidationError, match="role evidence"):
        ReplayRecord.model_validate(data)


@pytest.mark.parametrize(("field", "value"), [
    ("reviewer", "   "),
    ("reviewer", "TODO"),
    ("independence_basis", "  "),
    ("independence_basis", "unknown"),
])
def test_technical_review_rejects_blank_or_placeholder_identity_fields(field, value):
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    data = family_review(case).model_dump(mode="json", by_alias=True)
    data[field] = value
    with pytest.raises(ValidationError):
        TechnicalReviewRecord.model_validate(data)


def test_admission_rejects_an_unattached_failure_in_the_selected_run(tmp_path):
    case = DatasetManifest.model_validate(manifest(dataset_case(runtime="pytest-cpython312"))).cases[0]
    row = next(row for row in matrix.load() if row.id == case.runtime)
    environment = {"dataset_version": "0.1.0", "runtime_row_sha256": runtime_row_sha256(row),
                   "executor_sha256": executor_sha256()}
    records = tuple(replay_record(case, attempt=attempt).model_copy(update=environment)
                    for attempt in (1, 2, 3))
    review = family_review(case)
    dataset = tmp_path / "benchmarks/dataset"
    revision_dir = dataset / "receipts" / case_revision_sha256(case)
    revision_dir.mkdir(parents=True)
    pointers = []
    for record in records:
        path = revision_dir / f"replay-run-{record.attempt}.json"
        path.write_bytes(receipt_bytes(record))
        pointers.append({"path": path.relative_to(dataset).as_posix(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "attempt": record.attempt})
    review_path = dataset / "receipts/review.json"
    review_path.write_bytes(receipt_bytes(review))
    attached_data = case.model_dump(mode="json")
    attached_data.update({
        "status": "qualified",
        "replay_receipts": pointers,
        "review_receipt": {"path": "receipts/review.json",
                           "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
                           "reviewer": review.reviewer, "reviewed_at": review.reviewed_at.isoformat()},
    })
    attached = corpus_module.DatasetCase.model_validate(attached_data)
    attached_manifest = DatasetManifest.model_validate(
        manifest(attached.model_dump(mode="json")))
    assert admission_from_manifest(dataset, attached_manifest, attached).ready

    changed_version = attached_manifest.model_copy(update={"dataset_version": "0.2.0"})
    assert admission_from_manifest(dataset, changed_version, attached).ready

    changed_image = attached.model_copy(update={"runtime_image_id": "sha256:" + "d" * 64})
    changed_image_manifest = attached_manifest.model_copy(update={"cases": (changed_image,)})
    assert not admission_from_manifest(dataset, changed_image_manifest, changed_image).ready

    hardlink = tmp_path / "linked-receipt.json"
    hardlink.hardlink_to(revision_dir / "replay-run-1.json")
    assert admission_from_manifest(dataset, attached_manifest, attached).code == "RECEIPT_INVALID"
    hardlink.unlink()

    hidden_failure = records[-1].model_copy(update={"attempt": 4, "outcome": "failed",
                                                     "failure_code": "EXPECTED_DISPOSITION_MISMATCH"})
    (revision_dir / "failure-hidden.json").write_bytes(receipt_bytes(hidden_failure))
    assert admission_from_manifest(dataset, attached_manifest, attached).code == "REPLAY_RUN_LEDGER_INVALID"


def test_oracle_fields_never_cross_agent_boundary(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.py").write_text("def target(value):\n    return value\n")
    request = {
        "case_id": "cs-boundary",
        "finding": {"title": "A finding", "description": "Only agent-visible text",
                    "file_path": "target.py", "start_line": 1, "symbol": "target", "cwe": "CWE-20"},
        "source": "source",
    }
    request_path = tmp_path / "input.json"
    request_path.write_text(json.dumps(request))
    case = load_case(request_path)

    for forbidden in ("expected_label", "split", "rights", "qualification_status", "family_id"):
        poisoned = {**request, forbidden: "EVALUATOR_SECRET_71b32"}
        request_path.write_text(json.dumps(poisoned))
        with pytest.raises(ValidationError, match=forbidden):
            load_case(request_path)
    request_path.write_text(json.dumps(request))

    serialized = case.model_dump(mode="json")
    with pytest.raises(ValidationError, match="expected_label"):
        Case.model_validate({**serialized, "expected_label": "EVALUATOR_SECRET_71b32"})

    row = select(case)
    assert row is not None
    producer_payload = render_case(case, row)
    submission = Submission.model_validate_json(
        (ROOT / "cases/cs-0001-a/reference-submission.json").read_text())
    auditor_payload = render_auditor(submission)
    for payload in (producer_payload, auditor_payload):
        assert "EVALUATOR_SECRET_71b32" not in payload
        assert "cf-secret-family" not in payload


def corpus_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(VALID_CORPUS, root)
    _test_git(root, "init", "-q", "-b", "main")
    _test_git(root, "config", "user.name", "Corpus fixture")
    _test_git(root, "config", "user.email", "corpus-fixture@example.invalid")
    _test_git(root, "remote", "add", "origin", "https://fixture.invalid/owner/project.git/")
    _test_git(root, "add", ".")
    _test_git(root, "commit", "-q", "-m", "vulnerable source fixture")
    vulnerable_commit = _test_git(root, "rev-parse", "HEAD")
    (root / ".fixture-second-commit").write_text("fixed revision\n")
    _test_git(root, "add", ".fixture-second-commit")
    _test_git(root, "commit", "-q", "-m", "fixed source fixture")
    fixed_commit = _test_git(root, "rev-parse", "HEAD")

    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request.update(commit=vulnerable_commit, fixed_commit=fixed_commit)
    request_path.write_text(json.dumps(request, indent=2) + "\n")

    data = read_manifest(root)
    case = data["cases"][0]
    case["source_pair"]["vulnerable"]["commit"] = vulnerable_commit
    case["source_pair"]["fixed"]["commit"] = fixed_commit
    target_rights = [record for record in case["rights"] if record["layer"] == "target_source"]
    for record, commit in zip(target_rights, (vulnerable_commit, fixed_commit), strict=True):
        record["evidence_revision"] = commit
        record["evidence_url"] = record["evidence_url"].replace(COMMIT_A, commit).replace(COMMIT_B, commit)
    case["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    bind_vendored_rights_evidence(root)
    return root


def _test_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], check=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip()


def fixture_evidence(root: Path):
    def resolve(url: str, revision: str) -> bytes | None:
        path = root / "evidence" / url.rsplit("/", 1)[-1]
        return path.read_bytes() if path.is_file() else None
    return resolve


def checked(root: Path):
    return validate_corpus(root, _evidence_resolver=fixture_evidence(root))


def read_manifest(root: Path) -> dict:
    return json.loads((root / "benchmarks/dataset/manifest.json").read_text())


def write_manifest(root: Path, data: dict) -> None:
    (root / "benchmarks/dataset/manifest.json").write_text(json.dumps(data, indent=2) + "\n")


def write_request(root: Path, request: dict) -> None:
    path = root / "cases/cs-1001/input.json"
    path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_manifest(root, data)


def set_local_snapshot_commit(root: Path, revision: str, commit: str) -> None:
    data = read_manifest(root)
    declared = data["cases"][0]["source_pair"][revision]
    declared["vendored_snapshot"]["commit"] = commit
    write_manifest(root, data)


def declare_vendored_snapshots(root: Path, *, distinct_upstream: bool = False) -> None:
    """Bind local source paths to foundation commits without replacing upstream identity."""
    data = read_manifest(root)
    case = data["cases"][0]
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    snapshot_repository = "https://fixture.invalid/owner/project"
    upstream_repository = ("https://upstream.invalid/example/project" if distinct_upstream
                           else snapshot_repository)
    upstream_commits = ("a" * 40, "b" * 40) if distinct_upstream else (
        case["source_pair"]["vulnerable"]["commit"], case["source_pair"]["fixed"]["commit"])
    snapshot_commits = tuple(
        case["source_pair"][revision].get("vendored_snapshot", {}).get(
            "commit", case["source_pair"][revision]["commit"])
        for revision in ("vulnerable", "fixed"))
    for revision, local_path, snapshot_commit, upstream_commit in zip(
            ("vulnerable", "fixed"),
            ("cases/cs-1001/vulnerable", "cases/cs-1001/fixed"),
            snapshot_commits, upstream_commits, strict=True):
        declared = case["source_pair"][revision]
        declared["vendored_snapshot"] = {
            "repository": snapshot_repository,
            "commit": snapshot_commit,
            "path": local_path,
            "tree_sha256": declared["tree_sha256"],
        }
        declared["repository"] = upstream_repository
        declared["commit"] = upstream_commit
    request["commit"], request["fixed_commit"] = upstream_commits
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    target_rights = [record for record in case["rights"] if record["layer"] == "target_source"]
    for record, upstream_commit in zip(target_rights, upstream_commits, strict=True):
        binding = record.get("origin", record)
        binding["revision" if "origin" in record else "evidence_revision"] = upstream_commit
        url_key = "url" if "origin" in record else "evidence_url"
        binding[url_key] = (
            f"{upstream_repository}/blob/{upstream_commit}/{binding[url_key].rsplit('/', 1)[-1]}")
    case["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)


def bind_vendored_rights_evidence(root: Path) -> str:
    """Commit local evidence copies while retaining their immutable upstream identity."""
    declare_vendored_snapshots(root, distinct_upstream=True)
    data = read_manifest(root)
    records = [record for record in data["cases"][0]["rights"] if record["layer"] == "target_source"]
    if records and all(record.get("origin") is not None
                       and "/cases/cs-1001/evidence/" in record["evidence_url"] for record in records):
        revisions = {record["evidence_revision"] for record in records}
        assert len(revisions) == 1
        return revisions.pop()
    relative_paths = []
    for record in records:
        filename = record["evidence_url"].rsplit("/", 1)[-1]
        relative = Path("cases/cs-1001/evidence") / filename
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "evidence" / filename, destination)
        relative_paths.append(relative.as_posix())
        record["origin"] = {
            "url": record["evidence_url"],
            "revision": record["evidence_revision"],
            "sha256": record["evidence_sha256"],
        }
    _test_git(root, "add", "--", *relative_paths)
    _test_git(root, "commit", "-q", "-m", "commit rights evidence copies")
    foundation = _test_git(root, "rev-parse", "HEAD")
    for record, relative in zip(records, relative_paths, strict=True):
        record["evidence_url"] = \
            f"https://fixture.invalid/owner/project/blob/{foundation}/{relative}"
        record["evidence_revision"] = foundation
    write_manifest(root, data)
    return foundation


def configure_mixed_shared_commit_sources(root: Path, monkeypatch, *, local_revision: str) -> None:
    """Make one source local and one Git-backed at the same upstream identity."""
    data = read_manifest(root)
    case = data["cases"][0]
    remote_revision = "fixed" if local_revision == "vulnerable" else "vulnerable"
    shared_repository = case["source_pair"]["vulnerable"]["repository"]
    shared_commit = case["source_pair"]["vulnerable"]["commit"]
    for revision in ("vulnerable", "fixed"):
        declared = case["source_pair"][revision]
        declared["repository"] = shared_repository
        declared["commit"] = shared_commit
    case["source_pair"][remote_revision].pop("vendored_snapshot")

    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["commit"] = shared_commit
    request["fixed_commit"] = shared_commit
    request_field = "source" if remote_revision == "vulnerable" else "fixed_source"
    request[request_field] = {"url": shared_repository, "commit": shared_commit}
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    case["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()

    records = [record for record in case["rights"] if record["layer"] == "target_source"]
    direct_origin = records[0].pop("origin")
    records[0].update(
        evidence_url=direct_origin["url"],
        evidence_revision=direct_origin["revision"],
        evidence_sha256=direct_origin["sha256"],
        redistribution_mode="acquisition_recipe",
    )
    records[1]["origin"]["url"] = records[1]["origin"]["url"].replace("b" * 40, shared_commit)
    records[1]["origin"]["revision"] = shared_commit
    write_manifest(root, data)

    remote_source = root / "cases/cs-1001" / remote_revision
    monkeypatch.setattr(corpus_module, "_offline_git_source", lambda *_args, **_kwargs: remote_source)


def add_valid_self_authored_conformance_pair(root: Path) -> None:
    """Create two complete local conformance cases at one Corsair foundation commit."""
    first_dir = root / "cases/cs-1001"
    second_dir = root / "cases/cs-1002"
    shutil.copytree(first_dir, second_dir)
    (second_dir / "vulnerable/target.py").write_text(
        "def parse_variant(value):\n"
        "    suffix = '!'\n"
        "    normalized = value.strip()\n"
        "    if normalized.endswith(suffix):\n"
        "        return normalized + suffix\n"
        "    return normalized\n")
    (second_dir / "fixed/target.py").write_text(
        "def parse_variant(value):\n"
        "    suffix = '!'\n"
        "    normalized = value.strip()\n"
        "    if normalized.endswith(suffix):\n"
        "        return normalized\n"
        "    return normalized\n")
    reference_path = second_dir / "reference-submission.json"
    reference = json.loads(reference_path.read_text())
    reference["hypothesis"]["target_symbol"] = "parse_variant"
    reference_path.write_text(json.dumps(reference, indent=2) + "\n")
    _test_git(root, "add", "--", "cases/cs-1002")
    _test_git(root, "commit", "-q", "-m", "add second conformance source")
    foundation = _test_git(root, "rev-parse", "HEAD")

    data = read_manifest(root)
    first = data["cases"][0]
    first["split"] = "conformance"
    repository = first["source_pair"]["vulnerable"]["vendored_snapshot"]["repository"]

    def bind_case(case: dict, case_id: str, directory: Path) -> None:
        request_path = directory / "input.json"
        request = json.loads(request_path.read_text())
        request.update(case_id=case_id, commit=foundation, fixed_commit=foundation)
        if case_id == "cs-1002":
            request["finding"]["symbol"] = "parse_variant"
            request["finding"]["title"] = "Path handling in parse_variant"
        request_path.write_text(json.dumps(request, indent=2) + "\n")
        case["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
        for revision, filename in (("vulnerable", "source-v-LICENSE"),
                                   ("fixed", "source-f-LICENSE")):
            source_root = directory / revision
            declared = case["source_pair"][revision]
            declared.update(
                repository=repository,
                commit=foundation,
                tree_sha256=tree_sha256(source_root),
                affected_file_sha256=hashlib.sha256((source_root / "target.py").read_bytes()).hexdigest(),
                affected_region_sha256=_region_sha256(source_root / "target.py", (4,)),
                vendored_snapshot={
                    "repository": repository,
                    "commit": foundation,
                    "path": f"cases/{case_id}/{revision}",
                    "tree_sha256": tree_sha256(source_root),
                },
            )
            record = [record for record in case["rights"] if record["layer"] == "target_source"
                      and record["evidence_url"].endswith(filename)][0]
            record["origin"].update(
                url=f"{repository}/blob/{foundation}/evidence/{filename}",
                revision=foundation,
            )
            if case_id == "cs-1002":
                record.update(
                    evidence_url=f"{repository}/blob/{foundation}/cases/{case_id}/evidence/{filename}",
                    evidence_revision=foundation,
                )
        case["source_pair"]["patch_sha256"] = _patch_sha256(
            directory / "vulnerable", directory / "fixed")

    bind_case(first, "cs-1001", first_dir)
    second = deepcopy(first)
    second.update(case_id="cs-1002", family_id="cf-1002", aliases=["CVE-2026-2002"])
    second["target"]["symbol"] = "parse_variant"
    second["artifacts"]["reference_submission_sha256"] = hashlib.sha256(
        (second_dir / "reference-submission.json").read_bytes()).hexdigest()
    bind_case(second, "cs-1002", second_dir)
    data["cases"].append(second)
    write_manifest(root, data)


def issue_codes(report) -> set[str]:
    return {issue.code for issue in (*report.errors, *report.warnings)}


def test_control_character_in_repository_root_becomes_one_path_escape_issue():
    report = validate_corpus(Path("bad\0root"))

    assert report.case_count == 0
    assert report.family_count == 0
    assert report.warnings == ()
    assert len(report.errors) == 1
    assert report.errors[0].code == "PATH_ESCAPE"


@pytest.mark.parametrize("codepoint", [0x00, 0x01, 0x1f, 0x7f],
                         ids=["nul", "soh", "unit-separator", "del"])
@pytest.mark.parametrize("location", [
    "source_repository", "evidence_url", "provenance_url", "target_path",
    "request_source_path", "request_source_url", "request_subdir",
])
def test_control_characters_become_deterministic_corpus_issues(tmp_path, location, codepoint):
    root = corpus_fixture(tmp_path)
    control = chr(codepoint)
    expected = "MANIFEST_INVALID"
    if location.startswith("request_"):
        request = json.loads((root / "cases/cs-1001/input.json").read_text())
        if location == "request_source_path":
            request["source"] = f"vulnerable{control}alias"
        else:
            source = {
                "url": "https://fixture.invalid/owner/project",
                "commit": request["commit"],
            }
            if location == "request_source_url":
                source["url"] = f"https://fixture.invalid/owner/{control}project"
            else:
                source["subdir"] = f"source{control}path"
            request["source"] = source
        write_request(root, request)
        expected = "ARTIFACT_MISSING"
    else:
        data = read_manifest(root)
        case = data["cases"][0]
        if location == "source_repository":
            case["source_pair"]["vulnerable"]["repository"] = \
                f"https://fixture.invalid/owner/{control}project"
        elif location == "evidence_url":
            record = case["rights"][0]
            record["evidence_url"] = record["evidence_url"].replace(
                "source-v-LICENSE", f"source-v-{control}LICENSE")
        elif location == "provenance_url":
            provenance = case["finding_provenance"]
            provenance["source_url"] = provenance["source_url"].replace(
                "finding.md", f"finding{control}.md")
        else:
            case["target"]["file"] = f"target{control}.py"
        write_manifest(root, data)

    report = checked(root)
    assert expected in issue_codes(report)


def test_rights_require_revision_and_evidence_hash(tmp_path):
    root = corpus_fixture(tmp_path)
    assert checked(root).ok

    data = read_manifest(root)
    data["cases"][0]["rights"] = [r for r in data["cases"][0]["rights"] if r["layer"] != "advisory"]
    write_manifest(root, data)
    assert "RIGHTS_LAYER_MISSING" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "mutable")
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["evidence_url"] = "https://fixture.invalid/evidence/main/source-v-LICENSE"
    write_manifest(root, data)
    assert "RIGHTS_MUTABLE_EVIDENCE" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "wrong-hash")
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["evidence_sha256"] = "f" * 64
    write_manifest(root, data)
    assert "RIGHTS_EVIDENCE_HASH_MISMATCH" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "single-source")
    data = read_manifest(root)
    fixed_commit = data["cases"][0]["source_pair"]["fixed"]["commit"]
    data["cases"][0]["rights"] = [r for r in data["cases"][0]["rights"]
                                      if not (r["layer"] == "target_source"
                                              and r.get("origin", {}).get(
                                                  "revision", r["evidence_revision"]) == fixed_commit)]
    write_manifest(root, data)
    assert "RIGHTS_SOURCE_REVISION_MISSING" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "review")
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["reviewed_at"] = "2999-01-01"
    data["cases"][0]["rights"][1]["reviewer"] = "TODO"
    write_manifest(root, data)
    assert {"RIGHTS_FUTURE_REVIEW", "RIGHTS_REVIEWER_MISSING"} <= issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "blank")
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["license_expression"] = "   "
    data["cases"][0]["rights"][1]["reviewer"] = "   "
    write_manifest(root, data)
    assert {"RIGHTS_PLACEHOLDER", "RIGHTS_REVIEWER_MISSING"} <= issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "notice")
    data = read_manifest(root)
    data["cases"][0]["rights"][0].pop("notice_requirements")
    write_manifest(root, data)
    assert "MANIFEST_INVALID" in issue_codes(checked(root))


def test_finding_provenance_requires_an_immutable_revision_and_matching_hash(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["finding_provenance"]["source_url"] = \
        "https://fixture.invalid/finding/main/finding.md"
    write_manifest(root, data)
    assert "PROVENANCE_MUTABLE_EVIDENCE" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "hash")
    data = read_manifest(root)
    data["cases"][0]["finding_provenance"]["sha256"] = "f" * 64
    write_manifest(root, data)
    assert "PROVENANCE_HASH_MISMATCH" in issue_codes(checked(root))


@pytest.mark.parametrize(("field", "code"), [
    ("aliases", "ALIAS_FAMILY_COLLISION"),
    ("source_pair", "SOURCE_PAIR_FAMILY_COLLISION"),
    ("patch_sha256", "PATCH_FAMILY_COLLISION"),
    ("affected_region_sha256", "AFFECTED_REGION_FAMILY_COLLISION"),
])
def test_family_leakage_is_rejected(tmp_path, field, code):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    first = data["cases"][0]
    second = deepcopy(first)
    second.update(case_id="cs-1002", family_id="cf-1002", aliases=["CVE-2026-2002"])
    second["source_pair"]["vulnerable"]["repository"] = "https://fixture.invalid/other"
    second["source_pair"]["fixed"]["repository"] = "https://fixture.invalid/other"
    second["source_pair"]["patch_sha256"] = "d" * 64
    second["source_pair"]["vulnerable"]["affected_region_sha256"] = "d" * 64
    second["source_pair"]["fixed"]["affected_region_sha256"] = "e" * 64
    if field == "aliases":
        second["aliases"] = list(first["aliases"])
    elif field == "source_pair":
        second["source_pair"]["vulnerable"]["repository"] = first["source_pair"]["vulnerable"]["repository"]
        second["source_pair"]["fixed"]["repository"] = first["source_pair"]["fixed"]["repository"]
    elif field == "patch_sha256":
        second["source_pair"]["patch_sha256"] = first["source_pair"]["patch_sha256"]
    else:
        second["source_pair"]["vulnerable"]["affected_region_sha256"] = \
            first["source_pair"]["vulnerable"]["affected_region_sha256"]
    data["cases"].append(second)
    write_manifest(root, data)
    report = checked(root)
    assert code in issue_codes(report)
    assert any(set(issue.case_ids) == {"cs-1001", "cs-1002"} for issue in report.errors if issue.code == code)


def test_distinct_conformance_subtrees_at_their_foundation_commit_do_not_collide(tmp_path):
    root = corpus_fixture(tmp_path)
    add_valid_self_authored_conformance_pair(root)

    report = checked(root)

    assert report.ok, report.errors
    assert "SOURCE_PAIR_FAMILY_COLLISION" not in issue_codes(report)


def test_nonconformance_cases_cannot_use_distinct_paths_to_hide_a_source_pair_collision(tmp_path):
    root = corpus_fixture(tmp_path)
    add_valid_self_authored_conformance_pair(root)
    data = read_manifest(root)
    for case in data["cases"]:
        case["split"] = "development"
    write_manifest(root, data)

    assert "SOURCE_PAIR_FAMILY_COLLISION" in issue_codes(checked(root))


def test_conformance_collision_exception_does_not_cross_split_boundary(tmp_path):
    root = corpus_fixture(tmp_path)
    add_valid_self_authored_conformance_pair(root)
    data = read_manifest(root)
    data["cases"][1]["split"] = "development"
    write_manifest(root, data)

    assert "SOURCE_PAIR_FAMILY_COLLISION" in issue_codes(checked(root))


def test_conformance_paths_only_distinguish_the_exact_foundation_revision(tmp_path):
    root = corpus_fixture(tmp_path)
    add_valid_self_authored_conformance_pair(root)
    data = read_manifest(root)
    for case in data["cases"]:
        for revision in ("vulnerable", "fixed"):
            case["source_pair"][revision]["vendored_snapshot"]["commit"] = "f" * 40
    write_manifest(root, data)

    assert "SOURCE_PAIR_FAMILY_COLLISION" in issue_codes(checked(root))


def test_source_and_patch_hashes_are_verified(tmp_path):
    root = corpus_fixture(tmp_path)
    assert checked(root).ok
    target = root / "cases/cs-1001/vulnerable/target.py"
    target.write_text(target.read_text() + "# changed\n")
    codes = issue_codes(checked(root))
    assert {"SOURCE_TREE_HASH_MISMATCH", "AFFECTED_FILE_HASH_MISMATCH", "PATCH_HASH_MISMATCH"} <= codes

    root = corpus_fixture(tmp_path / "patch")
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["patch_sha256"] = "0" * 64
    write_manifest(root, data)
    assert "PATCH_HASH_MISMATCH" in issue_codes(checked(root))

    left = root / "cases/cs-1001/vulnerable"
    right = root / "cases/cs-1001/fixed"
    before = _patch_sha256(left, right)
    left.touch()
    right.touch()
    assert _patch_sha256(left, right) == before


def test_local_sources_cannot_escape_the_case_directory(tmp_path):
    root = corpus_fixture(tmp_path)
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["source"] = "../../quarantine/legacy"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = \
        __import__("hashlib").sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "PATH_ESCAPE" in issue_codes(checked(root))


@pytest.mark.parametrize(("commit_field", "value"), [
    ("commit", None),
    ("fixed_commit", None),
    ("commit", "3" * 40),
    ("fixed_commit", "3" * 40),
])
def test_local_sources_require_both_declared_commits(tmp_path, commit_field, value):
    root = corpus_fixture(tmp_path)
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    if value is None:
        request.pop(commit_field)
    else:
        request[commit_field] = value
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "SOURCE_IDENTITY_MISMATCH" in issue_codes(checked(root))


def test_local_source_bytes_must_match_the_declared_git_commit(tmp_path):
    root = corpus_fixture(tmp_path)
    vulnerable = root / "cases/cs-1001/vulnerable"
    (vulnerable / "fabricated.py").write_text("FABRICATED = True\n")
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["tree_sha256"] = tree_sha256(vulnerable)
    data["cases"][0]["source_pair"]["patch_sha256"] = _patch_sha256(
        vulnerable, root / "cases/cs-1001/fixed")
    write_manifest(root, data)

    assert "LOCAL_SOURCE_COMMIT_MISMATCH" in issue_codes(checked(root))


def test_local_source_requires_the_declared_path_at_the_snapshot_commit(tmp_path):
    root = corpus_fixture(tmp_path)
    current_only = root / "cases/cs-1001/current-only"
    shutil.copytree(root / "cases/cs-1001/vulnerable", current_only)
    request = json.loads((root / "cases/cs-1001/input.json").read_text())
    request["source"] = "current-only"
    write_request(root, request)
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["vendored_snapshot"]["path"] = \
        "cases/cs-1001/current-only"
    write_manifest(root, data)

    assert "LOCAL_SOURCE_COMMIT_PATH_MISSING" in issue_codes(checked(root))


def test_local_source_rejects_a_symlink_alias(tmp_path):
    root = corpus_fixture(tmp_path)
    (root / "cases/cs-1001/alias").symlink_to("vulnerable", target_is_directory=True)
    request = json.loads((root / "cases/cs-1001/input.json").read_text())
    request["source"] = "alias"
    write_request(root, request)

    assert "PATH_ESCAPE" in issue_codes(checked(root))


@pytest.mark.parametrize("alias", ["./vulnerable", "vulnerable/", "vulnerable//", "vulnerable/."])
def test_local_source_rejects_noncanonical_lexical_aliases(tmp_path, alias):
    root = corpus_fixture(tmp_path)
    request = json.loads((root / "cases/cs-1001/input.json").read_text())
    request["source"] = alias
    write_request(root, request)

    assert "PATH_ESCAPE" in issue_codes(checked(root))


def test_local_source_requires_a_real_containing_git_worktree(tmp_path):
    root = corpus_fixture(tmp_path)
    shutil.rmtree(root / ".git")

    assert "LOCAL_SOURCE_GIT_UNAVAILABLE" in issue_codes(checked(root))


def test_local_source_requires_a_matching_normalized_origin(tmp_path):
    root = corpus_fixture(tmp_path)
    assert checked(root).ok  # ``.git/`` and slash variants normalize to the declared identity.
    _test_git(root, "remote", "set-url", "origin", "https://fixture.invalid/unrelated/project.git")

    assert "LOCAL_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


def test_vendored_snapshot_preserves_upstream_identity_while_binding_local_git_bytes(tmp_path):
    root = corpus_fixture(tmp_path)
    declare_vendored_snapshots(root, distinct_upstream=True)

    report = checked(root)

    assert report.ok, report.errors
    case = load_manifest(root / "benchmarks/dataset/manifest.json").cases[0]
    assert case.source_pair.vulnerable.repository == "https://upstream.invalid/example/project"
    assert case.source_pair.vulnerable.commit == "a" * 40
    assert case.source_pair.vulnerable.vendored_snapshot is not None
    assert case.source_pair.vulnerable.vendored_snapshot.repository == \
        "https://fixture.invalid/owner/project"

    changed_snapshot = case.source_pair.vulnerable.vendored_snapshot.model_copy(
        update={"commit": "c" * 40})
    changed = case.model_copy(update={
        "source_pair": case.source_pair.model_copy(update={
            "vulnerable": case.source_pair.vulnerable.model_copy(
                update={"vendored_snapshot": changed_snapshot})
        })
    })
    assert case_revision_sha256(changed) != case_revision_sha256(case)


def test_local_source_requires_an_explicit_vendored_snapshot_binding(tmp_path):
    root = corpus_fixture(tmp_path)
    declare_vendored_snapshots(root)
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"].pop("vendored_snapshot")
    write_manifest(root, data)

    assert "LOCAL_SOURCE_VENDORED_BINDING_MISSING" in issue_codes(checked(root))


@pytest.mark.parametrize(("field", "value", "code"), [
    ("repository", "https://fixture.invalid/unrelated/project", "LOCAL_SOURCE_REPOSITORY_MISMATCH"),
    ("commit", "f" * 40, "LOCAL_SOURCE_COMMIT_UNAVAILABLE"),
    ("path", "cases/cs-1001/fixed", "LOCAL_SOURCE_SNAPSHOT_PATH_MISMATCH"),
    ("tree_sha256", "f" * 64, "LOCAL_SOURCE_COMMIT_MISMATCH"),
])
def test_local_source_rejects_incorrect_vendored_snapshot_identity(tmp_path, field, value, code):
    root = corpus_fixture(tmp_path)
    declare_vendored_snapshots(root, distinct_upstream=True)
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["vendored_snapshot"][field] = value
    write_manifest(root, data)

    assert code in issue_codes(checked(root))


def test_local_source_snapshot_commit_must_be_in_the_current_history(tmp_path):
    root = corpus_fixture(tmp_path)
    tree = _test_git(root, "rev-parse", "HEAD^{tree}")
    detached = _test_git(root, "commit-tree", tree, "-m", "detached snapshot")
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["vendored_snapshot"]["commit"] = detached
    write_manifest(root, data)

    assert "LOCAL_SOURCE_COMMIT_NOT_ANCESTOR" in issue_codes(checked(root))


def test_git_source_rejects_vendored_snapshot_metadata(tmp_path):
    root = corpus_fixture(tmp_path)
    declare_vendored_snapshots(root, distinct_upstream=True)
    request = json.loads((root / "cases/cs-1001/input.json").read_text())
    request_upstream = read_manifest(root)["cases"][0]["source_pair"]["vulnerable"]["repository"]
    request["source"] = {
        "url": request_upstream,
        "commit": request["commit"],
    }
    write_request(root, request)

    assert request_upstream == "https://upstream.invalid/example/project"
    assert "VENDORED_SNAPSHOT_UNEXPECTED" in issue_codes(checked(root))


@pytest.mark.parametrize("origin", [
    "https://fixture.invalid/owner/project",
    "https://fixture.invalid/owner/project/",
    "https://fixture.invalid/owner/project.git",
    "https://fixture.invalid/owner/project.git/",
])
def test_local_source_accepts_only_conservative_repository_aliases(tmp_path, origin):
    root = corpus_fixture(tmp_path)
    _test_git(root, "remote", "set-url", "origin", origin)

    assert checked(root).ok


@pytest.mark.parametrize("origin", [
    "https://fixture.invalid/owner/project?mirror=true",
    "https://fixture.invalid/owner/project#mirror",
    "https://user:secret@fixture.invalid/owner/project",
    "https://fixture.invalid/owner/project//",
    "http://fixture.invalid/owner/project",
    "ssh://fixture.invalid/owner/project",
])
def test_local_source_rejects_adorned_origin_urls(tmp_path, origin):
    root = corpus_fixture(tmp_path)
    _test_git(root, "remote", "set-url", "origin", origin)

    assert "LOCAL_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


@pytest.mark.parametrize("repository", [
    "https://fixture.invalid/owner/project?mirror=true",
    "https://fixture.invalid/owner/project#mirror",
    "https://user:secret@fixture.invalid/owner/project",
    "https://fixture.invalid/owner/project//",
])
def test_invalid_declared_and_origin_urls_never_compare_equal(tmp_path, repository):
    root = corpus_fixture(tmp_path)
    _test_git(root, "remote", "set-url", "origin", repository)
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["repository"] = repository
    data["cases"][0]["source_pair"]["fixed"]["repository"] = repository
    write_manifest(root, data)

    assert "LOCAL_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


@pytest.mark.parametrize("repository", [
    "https://fixture.invalid/owner/project?mirror=true",
    "https://fixture.invalid/owner/project#mirror",
    "https://user:secret@fixture.invalid/owner/project",
    "https://fixture.invalid/owner/project//",
])
def test_invalid_declared_and_git_source_urls_never_compare_equal(tmp_path, repository):
    root = corpus_fixture(tmp_path)
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["source"] = {"url": repository, "commit": request["commit"]}
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["source_pair"]["vulnerable"]["repository"] = repository
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)

    assert "SOURCE_IDENTITY_MISMATCH" in issue_codes(checked(root))


def test_local_source_requires_the_declared_commit_object_offline(tmp_path):
    root = corpus_fixture(tmp_path)
    set_local_snapshot_commit(root, "vulnerable", "3" * 40)

    assert "LOCAL_SOURCE_COMMIT_UNAVAILABLE" in issue_codes(checked(root))


def test_local_source_rejects_a_submodule_in_the_declared_tree(tmp_path):
    root = corpus_fixture(tmp_path)
    head = _test_git(root, "rev-parse", "HEAD")
    _test_git(root, "update-index", "--add", "--cacheinfo", "160000", head,
              "cases/cs-1001/vulnerable/vendor")
    _test_git(root, "commit", "-q", "-m", "add unsupported gitlink")
    set_local_snapshot_commit(root, "vulnerable", _test_git(root, "rev-parse", "HEAD"))

    assert "LOCAL_SOURCE_TREE_UNSUPPORTED" in issue_codes(checked(root))


def test_local_source_rejects_a_non_tree_at_the_declared_path(tmp_path):
    root = corpus_fixture(tmp_path)
    source_path = "cases/cs-1001/vulnerable"
    _test_git(root, "rm", "-q", "--cached", "-r", "--", source_path)
    replacement = root / "replacement-source"
    replacement.write_text("a source directory cannot be replaced by a blob\n")
    blob = _test_git(root, "hash-object", "-w", str(replacement))
    _test_git(root, "update-index", "--add", "--cacheinfo", "100644", blob, source_path)
    _test_git(root, "commit", "-q", "-m", "replace source tree with blob")
    set_local_snapshot_commit(root, "vulnerable", _test_git(root, "rev-parse", "HEAD"))

    assert "LOCAL_SOURCE_TREE_UNSUPPORTED" in issue_codes(checked(root))


def test_local_snapshots_require_vendored_revision_rights(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    for record in data["cases"][0]["rights"]:
        if record["layer"] == "target_source":
            record["redistribution_mode"] = "acquisition_recipe"
    write_manifest(root, data)
    assert "LOCAL_SOURCE_PROVENANCE_UNVERIFIED" in issue_codes(checked(root))


def test_local_source_rights_cannot_be_substituted_from_an_unrelated_repository(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    vulnerable_commit = data["cases"][0]["source_pair"]["vulnerable"]["commit"]
    acquisition_only = deepcopy(data["cases"][0]["rights"][0])
    acquisition_only["redistribution_mode"] = "acquisition_recipe"
    data["cases"][0]["rights"][0]["origin"]["url"] = \
        f"https://fixture.invalid/unrelated/project/blob/{vulnerable_commit}/source-v-LICENSE"
    data["cases"][0]["rights"].append(acquisition_only)
    write_manifest(root, data)
    assert "RIGHTS_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


def test_vendored_rights_evidence_is_bound_to_upstream_origin_and_local_git_bytes(tmp_path):
    root = corpus_fixture(tmp_path)
    foundation = bind_vendored_rights_evidence(root)
    fallback = fixture_evidence(root)
    local_resolution_calls = []

    def resolve(url: str, revision: str) -> bytes | None:
        if "/cases/cs-1001/evidence/" in url:
            local_resolution_calls.append((url, revision))
            return None
        return fallback(url, revision)

    report = validate_corpus(root, _evidence_resolver=resolve)

    assert report.ok, report.errors
    assert local_resolution_calls == []
    case = load_manifest(root / "benchmarks/dataset/manifest.json").cases[0]
    records = [record for record in case.rights if record.layer == "target_source"]
    assert {record.evidence_revision for record in records} == {foundation}
    assert {record.origin.revision for record in records if record.origin is not None} == {"a" * 40, "b" * 40}


def test_local_target_source_rights_require_an_origin_binding(tmp_path):
    root = corpus_fixture(tmp_path)
    bind_vendored_rights_evidence(root)
    data = read_manifest(root)
    data["cases"][0]["rights"][0].pop("origin")
    write_manifest(root, data)

    assert "RIGHTS_ORIGIN_MISSING" in issue_codes(checked(root))


@pytest.mark.parametrize(("mutation", "code"), [
    ("origin_repository", "RIGHTS_ORIGIN_REPOSITORY_MISMATCH"),
    ("origin_revision", "RIGHTS_ORIGIN_REVISION_MISMATCH"),
    ("origin_hash", "RIGHTS_ORIGIN_HASH_MISMATCH"),
    ("copy_hash", "RIGHTS_ORIGIN_HASH_MISMATCH"),
    ("evidence_repository", "RIGHTS_LOCAL_EVIDENCE_REPOSITORY_MISMATCH"),
    ("evidence_revision", "RIGHTS_LOCAL_EVIDENCE_COMMIT_UNAVAILABLE"),
    ("evidence_path", "RIGHTS_LOCAL_EVIDENCE_PATH_INVALID"),
    ("evidence_object", "RIGHTS_LOCAL_EVIDENCE_OBJECT_UNAVAILABLE"),
])
def test_vendored_rights_reject_inconsistent_origin_or_local_identity(tmp_path, mutation, code):
    root = corpus_fixture(tmp_path)
    foundation = bind_vendored_rights_evidence(root)
    data = read_manifest(root)
    record = data["cases"][0]["rights"][0]
    if mutation == "origin_repository":
        record["origin"]["url"] = record["origin"]["url"].replace(
            "upstream.invalid/example/project", "upstream.invalid/unrelated/project")
    elif mutation == "origin_revision":
        record["origin"]["revision"] = "c" * 40
        record["origin"]["url"] = record["origin"]["url"].replace("a" * 40, "c" * 40)
    elif mutation == "origin_hash":
        record["origin"]["sha256"] = "f" * 64
    elif mutation == "copy_hash":
        record["evidence_sha256"] = "f" * 64
    elif mutation == "evidence_repository":
        record["evidence_url"] = record["evidence_url"].replace(
            "fixture.invalid/owner/project", "fixture.invalid/unrelated/project")
    elif mutation == "evidence_revision":
        record["evidence_revision"] = "c" * 40
        record["evidence_url"] = record["evidence_url"].replace(foundation, "c" * 40)
    elif mutation == "evidence_path":
        record["evidence_url"] = record["evidence_url"].replace(
            "cases/cs-1001/evidence", "cases/cs-1001/vulnerable")
    else:
        record["evidence_url"] = record["evidence_url"].replace(
            "source-v-LICENSE", "missing-LICENSE")
    write_manifest(root, data)

    assert code in issue_codes(checked(root))


def test_vendored_rights_reject_uncommitted_evidence_drift(tmp_path):
    root = corpus_fixture(tmp_path)
    bind_vendored_rights_evidence(root)
    (root / "cases/cs-1001/evidence/source-v-LICENSE").write_text("uncommitted replacement\n")

    assert "RIGHTS_LOCAL_EVIDENCE_DRIFT" in issue_codes(checked(root))


def test_vendored_rights_reject_evidence_deleted_from_head_and_recreated_untracked(tmp_path):
    root = corpus_fixture(tmp_path)
    evidence = root / "cases/cs-1001/evidence/source-v-LICENSE"
    original = evidence.read_bytes()
    _test_git(root, "rm", "-q", "--", "cases/cs-1001/evidence/source-v-LICENSE")
    _test_git(root, "commit", "-q", "-m", "delete evidence from head")
    evidence.write_bytes(original)

    assert "RIGHTS_LOCAL_EVIDENCE_HEAD_MISMATCH" in issue_codes(checked(root))


def test_vendored_rights_reject_a_committed_replacement_masked_by_old_disk_bytes(tmp_path):
    root = corpus_fixture(tmp_path)
    evidence = root / "cases/cs-1001/evidence/source-v-LICENSE"
    original = evidence.read_bytes()
    evidence.write_text("committed replacement\n")
    _test_git(root, "add", "--", "cases/cs-1001/evidence/source-v-LICENSE")
    _test_git(root, "commit", "-q", "-m", "replace evidence in head")
    evidence.write_bytes(original)

    assert "RIGHTS_LOCAL_EVIDENCE_HEAD_MISMATCH" in issue_codes(checked(root))


def test_vendored_rights_reject_a_symlinked_evidence_copy(tmp_path):
    root = corpus_fixture(tmp_path)
    bind_vendored_rights_evidence(root)
    evidence = root / "cases/cs-1001/evidence/source-v-LICENSE"
    evidence.unlink()
    evidence.symlink_to(root / "evidence/source-v-LICENSE")

    assert "RIGHTS_LOCAL_EVIDENCE_PATH_INVALID" in issue_codes(checked(root))


@pytest.mark.parametrize("local_revision", ["vulnerable", "fixed"])
def test_mixed_sources_with_one_shared_commit_validate_rights_by_acquisition_type(
        tmp_path, monkeypatch, local_revision):
    root = corpus_fixture(tmp_path)
    configure_mixed_shared_commit_sources(root, monkeypatch, local_revision=local_revision)

    report = checked(root)

    assert report.ok, report.errors
    assert not ({"RIGHTS_ORIGIN_MISSING", "RIGHTS_ORIGIN_UNEXPECTED",
                 "LOCAL_SOURCE_PROVENANCE_UNVERIFIED"} & issue_codes(report))

    data = read_manifest(root)
    local_record = [record for record in data["cases"][0]["rights"]
                    if record["layer"] == "target_source" and record.get("origin") is not None][0]
    origin = local_record.pop("origin")
    local_record.update(
        evidence_url=origin["url"],
        evidence_revision=origin["revision"],
        evidence_sha256=origin["sha256"],
    )
    write_manifest(root, data)

    codes = issue_codes(checked(root))
    assert {"RIGHTS_ORIGIN_MISSING", "LOCAL_SOURCE_PROVENANCE_UNVERIFIED"} <= codes


def test_git_sources_reject_vendored_rights_origin_metadata(tmp_path):
    root = corpus_fixture(tmp_path)
    bind_vendored_rights_evidence(root)
    data = read_manifest(root)
    case = data["cases"][0]
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    for request_field, revision_name in (("source", "vulnerable"), ("fixed_source", "fixed")):
        declared = case["source_pair"][revision_name]
        declared.pop("vendored_snapshot")
        request[request_field] = {"url": declared["repository"], "commit": declared["commit"]}
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    case["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)

    assert "RIGHTS_ORIGIN_UNEXPECTED" in issue_codes(checked(root))


@pytest.mark.parametrize(("expression", "code"), [
    ("NOASSERTION", "RIGHTS_NOASSERTION"),
    ("NONE", "RIGHTS_NOASSERTION"),
    ("TODO", "RIGHTS_PLACEHOLDER"),
    ("CC-BY-NC-4.0", "RIGHTS_NONCOMMERCIAL"),
    ("MIT OR NOASSERTION", "RIGHTS_NOASSERTION"),
    ("Apache-2.0 AND NONE", "RIGHTS_NOASSERTION"),
    ("MIT OR UNKNOWN", "RIGHTS_PLACEHOLDER"),
    ("TODO license review", "RIGHTS_PLACEHOLDER"),
    ("MIT AND TBD", "RIGHTS_PLACEHOLDER"),
    ("CC BY-NC 4.0", "RIGHTS_NONCOMMERCIAL"),
    ("MIT OR LicenseRef-NonCommercial", "RIGHTS_NONCOMMERCIAL"),
    ("MIT OR NON COMMERCIAL", "RIGHTS_NONCOMMERCIAL"),
    ("LicenseRef-NC", "RIGHTS_NONCOMMERCIAL"),
])
def test_noassertion_cannot_be_scored(tmp_path, expression, code):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["license_expression"] = expression
    write_manifest(root, data)
    report = checked(root)
    assert not report.ok and code in issue_codes(report)


def test_reviewed_license_ref_can_be_scored(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["rights"][0]["license_expression"] = "LicenseRef-Bouncy-Castle"
    write_manifest(root, data)
    assert checked(root).ok


@pytest.mark.parametrize("location", ["case_id", "variant_id", "title", "description"])
def test_case_names_do_not_encode_answers(tmp_path, location):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    case = data["cases"][0]
    if location == "case_id":
        case["case_id"] = "cs-1001-fixed"
    elif location == "variant_id":
        case["variant_id"] = "exploitable"
    else:
        request = json.loads((root / "cases/cs-1001/input.json").read_text())
        request["finding"][location] = "This is likely_exploitable"
        (root / "cases/cs-1001/input.json").write_text(json.dumps(request, indent=2) + "\n")
        case["artifacts"]["input_sha256"] = "0" * 64
    write_manifest(root, data)
    assert "ANSWER_BEARING_IDENTITY" in issue_codes(checked(root))


def test_normal_security_finding_prose_is_not_treated_as_an_answer_oracle(tmp_path):
    root = corpus_fixture(tmp_path)
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["finding"]["description"] = \
        "The vulnerable parser was fixed during development before release."
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert checked(root).ok


@pytest.mark.parametrize("phrase", [
    "expected_label: LIKELY_EXPLOITABLE",
    "The oracle label is LIKELY_NOT_EXPLOITABLE",
    '"status": "INCONCLUSIVE"',
    "expected_fix=verified",
    '"fix": "verified"',
    '"status": "not_verified"',
])
def test_explicit_oracle_labels_and_status_fields_are_rejected_from_finding_prose(tmp_path, phrase):
    root = corpus_fixture(tmp_path)
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["finding"]["description"] = phrase
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "ANSWER_BEARING_IDENTITY" in issue_codes(checked(root))


def test_quarantine_is_never_selected(tmp_path):
    root = corpus_fixture(tmp_path)
    assert checked(root).ok
    manifest_model = load_manifest(root / "benchmarks/dataset/manifest.json")
    for eval_set in ("conformance", "development", "regression", "release", "holdout"):
        assert all(case.case_id != "legacy" for case in select_cases(manifest_model, eval_set))

    data = read_manifest(root)
    data["cases"][0]["review_receipt"] = {
        "path": "../../../quarantine/legacy/review.json", "sha256": "a" * 64,
        "reviewer": "reviewer", "reviewed_at": "2026-10-22",
    }
    write_manifest(root, data)
    assert not checked(root).ok


def test_qualified_case_without_current_admission_receipts_fails_closed(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["status"] = "qualified"
    write_manifest(root, data)

    report = checked(root)
    assert "QUALIFICATION_REPLAY_TRIO_REQUIRED" in issue_codes(report)


def test_historical_corpus_roots_require_complete_quarantine_entries(tmp_path):
    root = corpus_fixture(tmp_path)
    (root / "evals/e2e").mkdir(parents=True)
    (root / "benchmarks/corpus/infosec-harness").mkdir(parents=True)
    report = checked(root)
    assert "QUARANTINE_REQUIRED_ENTRY_MISSING" in issue_codes(report)

    quarantine_path = root / "benchmarks/dataset/quarantine.json"
    quarantine = json.loads(quarantine_path.read_text())
    quarantine["entries"].append({
        "path": "evals/e2e",
        "reason_codes": ["rights_unreviewed"],
        "reviewer": "reviewer",
        "reviewed_at": "2026-10-22",
        "note": "Historical corpus is not qualified.",
    })
    quarantine_path.write_text(json.dumps(quarantine, indent=2) + "\n")
    report = checked(root)
    assert {"QUARANTINE_REQUIRED_ENTRY_MISSING", "QUARANTINE_REASON_MISSING"} <= issue_codes(report)

    root = corpus_fixture(tmp_path / "alias")
    (root / "evals/e2e").mkdir(parents=True)
    (root / "alias-evals").symlink_to(root / "evals/e2e", target_is_directory=True)
    quarantine_path = root / "benchmarks/dataset/quarantine.json"
    quarantine = json.loads(quarantine_path.read_text())
    quarantine["entries"].append({
        "path": "alias-evals",
        "reason_codes": ["rights_unreviewed", "stale_probe_contract", "stale_oracle_semantics",
                         "answer_bearing_metadata", "unsupported_scope"],
        "reviewer": "reviewer",
        "reviewed_at": "2026-10-22",
        "note": "An alias must not replace the mandatory lexical entry.",
    })
    quarantine_path.write_text(json.dumps(quarantine, indent=2) + "\n")
    assert "QUARANTINE_REQUIRED_ENTRY_MISSING" in issue_codes(checked(root))


def test_declared_artifact_hashes_and_reference_target_are_verified(tmp_path):
    root = corpus_fixture(tmp_path)
    (root / "cases/cs-1001/oracle.json").write_text("{}\n")
    assert "ARTIFACT_HASH_MISMATCH" in issue_codes(checked(root))

    root = corpus_fixture(tmp_path / "reference")
    submission = json.loads((root / "cases/cs-1001/reference-submission.json").read_text())
    submission["hypothesis"]["target_symbol"] = "another_symbol"
    (root / "cases/cs-1001/reference-submission.json").write_text(json.dumps(submission, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["reference_submission_sha256"] = \
        __import__("hashlib").sha256((root / "cases/cs-1001/reference-submission.json").read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "REFERENCE_TARGET_MISMATCH" in issue_codes(checked(root))


@pytest.mark.parametrize("missing", ["harness_path", "harness_sha256"])
def test_harness_path_and_hash_must_be_declared_together(tmp_path, missing):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    harness = root / "cases/cs-1001/harness.py"
    harness.write_text("print('harness')\n")
    data["cases"][0]["artifacts"].update(
        harness_path="harness.py", harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest())
    data["cases"][0]["artifacts"].pop(missing)
    write_manifest(root, data)
    assert "MANIFEST_INVALID" in issue_codes(checked(root))


def test_declared_harness_is_case_relative_nonaliasing_and_hash_verified(tmp_path):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    harness = root / "cases/cs-1001/harness.py"
    harness.write_text("print('harness')\n")
    data["cases"][0]["artifacts"].update(harness_path="harness.py", harness_sha256="f" * 64)
    write_manifest(root, data)
    assert "HARNESS_HASH_MISMATCH" in issue_codes(checked(root))

    data["cases"][0]["artifacts"].update(
        harness_path="input.json", harness_sha256=hashlib.sha256(
            (root / "cases/cs-1001/input.json").read_bytes()).hexdigest())
    write_manifest(root, data)
    assert "HARNESS_ALIAS" in issue_codes(checked(root))

    harness.unlink()
    harness.write_text("print('valid harness')\n")
    data["cases"][0]["artifacts"].update(
        harness_path="harness.py", harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest())
    write_manifest(root, data)
    assert checked(root).ok

    harness.unlink()
    harness.hardlink_to(root / "cases/cs-1001/vulnerable/target.py")
    data["cases"][0]["artifacts"]["harness_sha256"] = hashlib.sha256(harness.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "HARNESS_ALIAS" in issue_codes(checked(root))

    harness.unlink()
    vulnerable = root / "cases/cs-1001/vulnerable"
    helper = vulnerable / "helper.py"
    helper.write_text("HELPER = True\n")
    harness.hardlink_to(helper)
    data["cases"][0]["source_pair"]["vulnerable"]["tree_sha256"] = tree_sha256(vulnerable)
    data["cases"][0]["source_pair"]["patch_sha256"] = _patch_sha256(
        vulnerable, root / "cases/cs-1001/fixed")
    data["cases"][0]["artifacts"]["harness_sha256"] = hashlib.sha256(harness.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "HARNESS_ALIAS" in issue_codes(checked(root))


@pytest.mark.parametrize("content", [b"\xff\xfe\xfd", b"x" * (256 * 1024 + 1)],
                         ids=["invalid-utf8", "oversized"])
def test_similarity_input_is_bounded_and_decode_failures_become_deterministic_issues(tmp_path, content):
    root = corpus_fixture(tmp_path)
    (root / "cases/cs-1001/vulnerable/target.py").write_bytes(content)
    report = checked(root)
    assert "SOURCE_SIMILARITY_UNAVAILABLE" in issue_codes(report)


def test_rights_evidence_resolution_is_offline(tmp_path, monkeypatch):
    root = corpus_fixture(tmp_path)
    calls = []
    monkeypatch.setattr("corsair.case.acquire", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert checked(root).ok and calls == []

    data = read_manifest(root)
    data["cases"][0]["rights"][0]["evidence_url"] = \
        f"https://unsupported.invalid/{COMMIT_A}/LICENSE"
    write_manifest(root, data)
    report = validate_corpus(root)
    assert "RIGHTS_EVIDENCE_UNAVAILABLE" in issue_codes(report) and calls == []

    root = corpus_fixture(tmp_path / "missing-source")
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request["source"] = {"url": "https://fixture.invalid/project", "commit": COMMIT_A}
    request["fixed_source"] = {"url": "https://fixture.invalid/project", "commit": COMMIT_B}
    request.pop("commit")
    request.pop("fixed_commit")
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    data["cases"][0]["artifacts"]["input_sha256"] = \
        __import__("hashlib").sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)
    assert "SOURCE_NOT_ACQUIRED" in issue_codes(checked(root)) and calls == []


def test_validation_git_commands_disable_lazy_fetch_prompts_and_ambient_config(tmp_path, monkeypatch):
    captured = {}

    injected = {
        "GIT_CONFIG": str(tmp_path / "injected.config"),
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_PARAMETERS": "'remote.origin.url=https://injected.invalid/project'",
        "GIT_CONFIG_KEY_0": "remote.origin.url",
        "GIT_CONFIG_VALUE_0": "https://injected.invalid/project",
        "GIT_CONFIG_KEY_custom": "include.path",
        "GIT_CONFIG_VALUE_custom": str(tmp_path / "injected.config"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "injected.config"),
        "GIT_CONFIG_GLOBAL": str(tmp_path / "injected.config"),
        "GIT_CONFIG_NOSYSTEM": "0",
    }
    for name, value in injected.items():
        monkeypatch.setenv(name, value)

    def run(command, **options):
        captured.update(command=command, options=options)
        return subprocess.CompletedProcess(command, 1, b"", b"missing")

    monkeypatch.setattr(subprocess, "run", run)
    corpus_module._run_git(tmp_path, "cat-file", "-e", "1" * 40)

    environment = captured["options"]["env"]
    assert environment["GIT_NO_LAZY_FETCH"] == "1"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GCM_INTERACTIVE"] == "never"
    assert environment["GIT_ASKPASS"] == "/bin/false"
    assert environment["SSH_ASKPASS"] == "/bin/false"
    assert "GIT_CONFIG" not in environment
    assert "GIT_CONFIG_COUNT" not in environment
    assert "GIT_CONFIG_PARAMETERS" not in environment
    assert "GIT_CONFIG_SYSTEM" not in environment
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert not any(name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) for name in environment)
    assert captured["options"]["stdin"] is subprocess.DEVNULL


@pytest.mark.parametrize("mechanism", ["count", "parameters", "config-file"])
def test_ambient_git_config_cannot_fake_the_origin(tmp_path, monkeypatch, mechanism):
    root = corpus_fixture(tmp_path)
    _test_git(root, "remote", "remove", "origin")
    declared = "https://fixture.invalid/owner/project"
    if mechanism == "count":
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "remote.origin.url")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", declared)
    elif mechanism == "parameters":
        monkeypatch.setenv("GIT_CONFIG_PARAMETERS", f"'remote.origin.url={declared}'")
    else:
        injected = tmp_path / "injected.config"
        injected.write_text(f'[remote "origin"]\nurl = {declared}\n')
        monkeypatch.setenv("GIT_CONFIG", str(injected))

    assert "LOCAL_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


def test_promisor_checkout_with_a_missing_blob_fails_without_fetching(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _test_git(upstream, "init", "-q", "-b", "main")
    _test_git(upstream, "config", "user.name", "Promisor fixture")
    _test_git(upstream, "config", "user.email", "promisor@example.invalid")
    (upstream / "payload.txt").write_text("blob omitted from the partial clone\n")
    _test_git(upstream, "add", "payload.txt")
    _test_git(upstream, "commit", "-q", "-m", "payload")
    _test_git(upstream, "config", "uploadpack.allowFilter", "true")
    commit = _test_git(upstream, "rev-parse", "HEAD")

    checkout = tmp_path / "partial"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                    upstream.as_uri(), str(checkout)], check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert _test_git(checkout, "config", "--get", "remote.origin.promisor") == "true"
    upstream.rename(tmp_path / "unavailable-upstream")
    trace = tmp_path / "git-trace.json"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))

    result = corpus_module._run_git(checkout, "show", f"{commit}:payload.txt")

    assert result.returncode != 0
    trace_text = trace.read_text()
    assert '"fetch"' not in trace_text
    assert "git-upload-pack" not in trace_text


@pytest.mark.parametrize("repository", [
    "https://github.com/example/project",
    "https://github.com/example/project/",
    "https://github.com/example/project.git",
    "https://github.com/example/project.git/",
])
def test_cached_evidence_accepts_equivalent_acquisition_identities(tmp_path, repository):
    key = hashlib.sha256(f"{repository}\n{COMMIT_A}".encode()).hexdigest()[:24]
    checkout = tmp_path / ".runs/sources" / key
    checkout.mkdir(parents=True)
    (checkout / ".corsair-complete").write_text(f"{repository}\n{COMMIT_A}\n")
    (checkout / "LICENSE").write_bytes(b"licensed\n")

    evidence_url = f"https://github.com/example/project/blob/{COMMIT_A}/LICENSE"
    assert _cached_evidence(tmp_path, evidence_url, COMMIT_A) == b"licensed\n"

    (checkout / ".corsair-complete").write_text(f"https://github.com/unrelated/project.git\n{COMMIT_A}\n")
    assert _cached_evidence(tmp_path, evidence_url, COMMIT_A) is None


def test_cached_evidence_rejects_a_symlinked_checkout_outside_the_cache(tmp_path):
    repository = "https://github.com/example/project.git"
    key = hashlib.sha256(f"{repository}\n{COMMIT_A}".encode()).hexdigest()[:24]
    cache = tmp_path / ".runs/sources"
    cache.mkdir(parents=True)
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    (outside / ".corsair-complete").write_text(f"{repository}\n{COMMIT_A}\n")
    (outside / "LICENSE").write_bytes(b"licensed\n")
    (cache / key).symlink_to(outside, target_is_directory=True)

    evidence_url = f"https://github.com/example/project/blob/{COMMIT_A}/LICENSE"
    assert _cached_evidence(tmp_path, evidence_url, COMMIT_A) is None


def test_corpus_report_is_sorted_and_cli_exit_is_fail_closed(tmp_path, capsys):
    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["rights"] = []
    write_manifest(root, data)
    assert corpus_main([str(root)]) == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(("ERROR", "REVIEW"))]
    assert lines == sorted(lines)


def test_corpus_validation_uses_the_explicit_manifest_inside_the_dataset_root(tmp_path):
    root = corpus_fixture(tmp_path)
    alternate = root / "benchmarks/dataset/conformance.json"
    alternate.write_bytes((root / "benchmarks/dataset/manifest.json").read_bytes())
    (root / "benchmarks/dataset/manifest.json").write_text("not json\n")

    report = validate_corpus(root, manifest_path=alternate, _evidence_resolver=fixture_evidence(root))
    assert report.ok and report.case_count == 1

    outside = root / "alternate.json"
    outside.write_bytes(alternate.read_bytes())
    assert "MANIFEST_INVALID" in issue_codes(
        validate_corpus(root, manifest_path=outside, _evidence_resolver=fixture_evidence(root)))


def test_makefile_exposes_provider_free_corpus_check():
    makefile = (ROOT / "Makefile").read_text()
    assert "corpus-check:" in makefile
    assert "$(PYTHON) -m corsair.corpus ." in makefile
    benchmark_target = makefile.split("benchmark-verify:", 1)[1].split("\n\n", 1)[0]
    assert "--manifest $(CORPUS_MANIFEST)" in benchmark_target
    assert "--eval-set $(EVAL_SET)" in benchmark_target and "--attempts $(ATTEMPTS)" in benchmark_target
    assert "$(PROVIDER)" not in benchmark_target and "$(wildcard" not in benchmark_target

