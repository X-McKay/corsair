"""Evaluator-only corpus metadata stays strict and outside every agent boundary."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair import corpus as corpus_module
from corsair.auditor import render as render_auditor
from corsair.case import Case, load_case, tree_sha256
from corsair.corpus import (DatasetManifest, _cached_evidence, _patch_sha256, load_manifest,
                            main as corpus_main, select_cases, validate_corpus)
from corsair.kernel import Submission
from corsair.matrix import select
from corsair.producer import render_case


ROOT = Path(__file__).resolve().parents[1]
VALID_CORPUS = ROOT / "tests/fixtures/corpus/valid"
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


def set_local_revision_commit(root: Path, revision: str, commit: str) -> None:
    request_path = root / "cases/cs-1001/input.json"
    request = json.loads(request_path.read_text())
    request_field = "commit" if revision == "vulnerable" else "fixed_commit"
    request[request_field] = commit
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    data = read_manifest(root)
    declared = data["cases"][0]["source_pair"][revision]
    old_commit = declared["commit"]
    declared["commit"] = commit
    for record in data["cases"][0]["rights"]:
        if record["layer"] == "target_source" and record["evidence_revision"] == old_commit:
            record["evidence_revision"] = commit
            record["evidence_url"] = record["evidence_url"].replace(old_commit, commit)
    data["cases"][0]["artifacts"]["input_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
    write_manifest(root, data)


def issue_codes(report) -> set[str]:
    return {issue.code for issue in (*report.errors, *report.warnings)}


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
                                              and r["evidence_revision"] == fixed_commit)]
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


def test_local_source_requires_the_declared_path_at_the_commit(tmp_path):
    root = corpus_fixture(tmp_path)
    current_only = root / "cases/cs-1001/current-only"
    shutil.copytree(root / "cases/cs-1001/vulnerable", current_only)
    request = json.loads((root / "cases/cs-1001/input.json").read_text())
    request["source"] = "current-only"
    write_request(root, request)

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


def test_local_source_requires_the_declared_commit_object_offline(tmp_path):
    root = corpus_fixture(tmp_path)
    set_local_revision_commit(root, "vulnerable", "3" * 40)

    assert "LOCAL_SOURCE_COMMIT_UNAVAILABLE" in issue_codes(checked(root))


def test_local_source_rejects_a_submodule_in_the_declared_tree(tmp_path):
    root = corpus_fixture(tmp_path)
    head = _test_git(root, "rev-parse", "HEAD")
    _test_git(root, "update-index", "--add", "--cacheinfo", "160000", head,
              "cases/cs-1001/vulnerable/vendor")
    _test_git(root, "commit", "-q", "-m", "add unsupported gitlink")
    set_local_revision_commit(root, "vulnerable", _test_git(root, "rev-parse", "HEAD"))

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
    set_local_revision_commit(root, "vulnerable", _test_git(root, "rev-parse", "HEAD"))

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
    data["cases"][0]["rights"][0]["evidence_url"] = \
        f"https://fixture.invalid/unrelated/project/blob/{vulnerable_commit}/source-v-LICENSE"
    data["cases"][0]["rights"].append(acquisition_only)
    write_manifest(root, data)
    assert "RIGHTS_SOURCE_REPOSITORY_MISMATCH" in issue_codes(checked(root))


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


def test_validation_git_commands_disable_lazy_fetch_and_prompts(tmp_path, monkeypatch):
    captured = {}

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
    assert captured["options"]["stdin"] is subprocess.DEVNULL


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


def test_makefile_exposes_provider_free_corpus_check():
    makefile = (ROOT / "Makefile").read_text()
    assert "corpus-check:" in makefile
    assert "$(PYTHON) -m corsair.corpus ." in makefile

