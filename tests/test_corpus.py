"""Evaluator-only corpus metadata stays strict and outside every agent boundary."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.auditor import render as render_auditor
from corsair.case import Case, load_case
from corsair.corpus import DatasetManifest, load_manifest, select_cases
from corsair.kernel import Submission
from corsair.matrix import select
from corsair.producer import render_case


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
COMMIT_A = "1" * 40
COMMIT_B = "2" * 40


def dataset_case(*, case_id: str = "cs-1001", family_id: str = "cf-1001",
                 variant_id: str | None = None, split: str = "development",
                 status: str = "candidate") -> dict:
    return {
        "case_id": case_id,
        "family_id": family_id,
        "variant_id": variant_id,
        "split": split,
        "status": status,
        "language": "python",
        "runtime": "python-3.12",
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
            "vulnerable": {"label": "LIKELY_EXPLOITABLE", "reason_code": "VERIFIED"},
            "fixed": {"label": "LIKELY_NOT_EXPLOITABLE", "reason_code": "VERIFIED"},
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
        (ROOT / "cases/path-traversal-fixture/reference-submission.json").read_text())
    auditor_payload = render_auditor(submission)
    for payload in (producer_payload, auditor_payload):
        assert "EVALUATOR_SECRET_71b32" not in payload
        assert "cf-secret-family" not in payload

