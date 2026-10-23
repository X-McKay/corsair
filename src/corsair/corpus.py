"""Evaluator-only benchmark inventory.

This module owns corpus truth, provenance, rights and qualification metadata.  Nothing here is part of
``corsair.case.Case`` or an agent payload: callers select a case here, then separately load its small ``input.json``.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationError, field_validator, model_validator

from .case import Frozen, GitSource, SafePath, _Request, tree_sha256
from .kernel import Fix, Label, Submission

DATASET_SCHEMA = "corsair-lite/dataset-manifest/1"
Sha256 = str
Commit = str
Split = Literal["conformance", "development", "regression", "holdout", "quarantine"]
QualificationStatus = Literal["candidate", "qualified", "quarantined", "retired"]
EvalSet = Literal["conformance", "development", "regression", "release", "holdout"]
RIGHTS_LAYERS = frozenset({"target_source", "dataset_annotations", "advisory", "reference_probe",
                          "runtime_dependencies"})
ANSWER_WORDS = frozenset({"likely_exploitable", "likely_not_exploitable", "inconclusive", "unable_to_run",
                          "verified", "not_verified", "vulnerable", "fixed", "patched", "exploitable",
                          "conformance", "development", "regression", "release", "quarantine", "holdout"})


def _https(value: str) -> str:
    if not value.startswith("https://") or any(character.isspace() for character in value):
        raise ValueError("an HTTPS URL is required")
    return value


class ProvenanceRecord(Frozen):
    author: str = Field(min_length=1, max_length=256)
    source_url: str = Field(min_length=9, max_length=2_000)
    source_revision: str = Field(pattern=r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")

    _source_is_https = field_validator("source_url")(_https)


class SourceRevision(Frozen):
    repository: str = Field(min_length=9, max_length=2_000)
    commit: Commit = Field(pattern=r"^[0-9a-f]{40}$")
    tree_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    affected_file_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    affected_region_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")

    _repository_is_https = field_validator("repository")(_https)


class SourcePair(Frozen):
    vulnerable: SourceRevision
    fixed: SourceRevision
    patch_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")


class TargetIdentity(Frozen):
    file: SafePath
    symbol: str = Field(min_length=1, max_length=256)
    lines: tuple[int, ...] = Field(min_length=1, max_length=64)

    @field_validator("lines")
    @classmethod
    def _ordered_positive_lines(cls, lines: tuple[int, ...]) -> tuple[int, ...]:
        if any(line < 1 for line in lines):
            raise ValueError("target lines are 1-based")
        unique = tuple(sorted(set(lines)))
        if len(unique) != len(lines):
            raise ValueError("target lines must be unique")
        return unique


class DispositionExpectation(Frozen):
    label: Label
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class ExpectedPair(Frozen):
    vulnerable: DispositionExpectation
    fixed: DispositionExpectation
    fix: Fix


class AllowedVariation(Frozen):
    revision: Literal["vulnerable", "fixed"]
    label: Label
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class ArtifactHashes(Frozen):
    input_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    reference_submission_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    harness_sha256: Sha256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RightsRecord(Frozen):
    layer: Literal["target_source", "dataset_annotations", "advisory", "reference_probe", "runtime_dependencies"]
    license_expression: str = Field(min_length=1, max_length=256)
    evidence_url: str = Field(min_length=9, max_length=2_000)
    evidence_revision: str = Field(pattern=r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
    evidence_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    notice_requirements: tuple[str, ...] = Field(max_length=32)
    redistribution_mode: Literal["acquisition_recipe", "vendored", "metadata_only", "reference_only"]
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: date

    _evidence_is_https = field_validator("evidence_url")(_https)


class ReviewReceipt(Frozen):
    path: SafePath
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: date


class ReplayReceipt(Frozen):
    path: SafePath
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)


class DatasetCase(Frozen):
    case_id: str = Field(pattern=r"^cs-[0-9]{4}(?:-[a-z0-9]+)?$")
    family_id: str = Field(pattern=r"^cf-[0-9]{4}$")
    variant_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    split: Split
    status: QualificationStatus
    language: Literal["python", "javascript", "java", "perl"]
    runtime: str = Field(min_length=1, max_length=128)
    package: str = Field(min_length=1, max_length=256)
    framework: str = Field(min_length=1, max_length=256)
    execution_mode: Literal["function", "method", "script", "cli", "main"]
    vulnerability_types: tuple[str, ...] = Field(min_length=1, max_length=16)
    cwes: tuple[str, ...] = Field(min_length=1, max_length=16)
    capability_tags: tuple[str, ...] = Field(default=(), max_length=32)
    risk_tags: tuple[str, ...] = Field(default=(), max_length=32)
    aliases: tuple[str, ...] = Field(default=(), max_length=64)
    finding_provenance: ProvenanceRecord
    source_pair: SourcePair
    target: TargetIdentity
    expected: ExpectedPair
    allowed_variations: tuple[AllowedVariation, ...] = Field(default=(), max_length=16)
    artifacts: ArtifactHashes
    visibility: Literal["public", "private", "restricted"]
    retention: Literal["permanent", "review_controlled", "ephemeral"]
    redaction: Literal["none", "metadata_only", "source_and_secrets"]
    rights: tuple[RightsRecord, ...] = Field(min_length=1, max_length=32)
    review_receipt: ReviewReceipt | None = None
    replay_receipts: tuple[ReplayReceipt, ...] = Field(default=(), max_length=32)

    @field_validator("cwes")
    @classmethod
    def _cwe_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.startswith("CWE-") or not value[4:].isdigit() for value in values):
            raise ValueError("CWE values must use the CWE-<number> form")
        return values

    @model_validator(mode="after")
    def _valid_split_status(self) -> "DatasetCase":
        if (self.split == "quarantine") != (self.status == "quarantined"):
            raise ValueError("the quarantine split and quarantined status must be used together")
        return self


class DatasetManifest(Frozen):
    schema_version: Literal["corsair-lite/dataset-manifest/1"] = Field(default=DATASET_SCHEMA, alias="schema")
    dataset_version: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
    cases: tuple[DatasetCase, ...] = ()

    @model_validator(mode="after")
    def _unique_identities(self) -> "DatasetManifest":
        repeated_cases = sorted(case_id for case_id, count in Counter(case.case_id for case in self.cases).items()
                                if count > 1)
        if repeated_cases:
            raise ValueError(f"duplicate case_id: {', '.join(repeated_cases)}")
        families: dict[str, list[DatasetCase]] = defaultdict(list)
        for case in self.cases:
            families[case.family_id].append(case)
        for family_id, variants in families.items():
            if len(variants) == 1:
                continue
            if any(case.variant_id is None for case in variants):
                raise ValueError(f"family {family_id} is repeated without a variant_id on every case")
            repeated_variants = sorted(variant for variant, count in Counter(
                case.variant_id for case in variants).items() if count > 1)
            if repeated_variants:
                raise ValueError(f"family {family_id} has duplicate variant_id: {', '.join(repeated_variants)}")
            if len({case.split for case in variants}) != 1 or len({case.language for case in variants}) != 1:
                raise ValueError(f"family {family_id} variants must share one split and language")
        return self


class CorpusIssue(Frozen):
    severity: Literal["error", "review_required"]
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    path: str | None = Field(default=None, max_length=2_000)
    case_ids: tuple[str, ...] = ()
    message: str = Field(min_length=1, max_length=2_000)


class CorpusReport(Frozen):
    errors: tuple[CorpusIssue, ...] = ()
    warnings: tuple[CorpusIssue, ...] = ()
    case_count: int = Field(ge=0)
    family_count: int = Field(ge=0)

    @property
    def ok(self) -> bool:
        return not self.errors


QuarantineReason = Literal["rights_unreviewed", "stale_probe_contract", "stale_oracle_semantics",
                           "answer_bearing_metadata", "unsupported_scope"]


class QuarantineEntry(Frozen):
    path: SafePath
    reason_codes: tuple[QuarantineReason, ...] = Field(min_length=1)
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: date
    note: str = Field(min_length=1, max_length=2_000)


class QuarantineManifest(Frozen):
    schema_version: Literal["corsair-lite/quarantine/1"] = Field(alias="schema")
    entries: tuple[QuarantineEntry, ...]


def load_manifest(path: Path) -> DatasetManifest:
    """Load a strict evaluator manifest; unknown or malformed metadata fails closed."""
    return DatasetManifest.model_validate_json(Path(path).read_bytes())


def select_cases(manifest: DatasetManifest, eval_set: EvalSet) -> tuple[DatasetCase, ...]:
    """Select qualified families for a named evaluation panel in manifest order."""
    selected_splits = {
        "conformance": {"conformance"},
        "development": {"conformance", "development"},
        "regression": {"regression"},
        "release": {"conformance", "development", "regression"},
        "holdout": {"holdout"},
    }
    try:
        splits = selected_splits[eval_set]
    except KeyError as error:
        raise ValueError(f"unknown evaluation set: {eval_set}") from error
    return tuple(case for case in manifest.cases if case.status == "qualified" and case.split in splits)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_entries(root: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        here = Path(directory)
        names = [name for name in dirnames if (here / name).is_symlink()] + filenames
        for name in names:
            path = here / name
            if path.name == ".corsair-complete":
                continue
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                mode, content = "120000", os.readlink(path).encode()
            elif stat.S_ISREG(info.st_mode):
                mode = "100755" if info.st_mode & 0o111 else "100644"
                content = path.read_bytes()
            else:
                continue
            entries[path.relative_to(root).as_posix()] = (mode, hashlib.sha256(content).hexdigest())
    return entries


def _patch_sha256(vulnerable: Path, fixed: Path) -> str:
    """Canonical source-tree delta independent of Git output, mtimes and checkout roots."""
    old, new = _tree_entries(vulnerable), _tree_entries(fixed)
    digest = hashlib.sha256(b"corsair-patch-v1\0")
    for relative in sorted(set(old) | set(new)):
        before, after = old.get(relative, ("-", "-")), new.get(relative, ("-", "-"))
        if before != after:
            digest.update(f"{relative}\0{before[0]}\0{before[1]}\0{after[0]}\0{after[1]}\n".encode())
    return digest.hexdigest()


def _region_sha256(path: Path, lines: tuple[int, ...]) -> str | None:
    content = path.read_bytes().splitlines(keepends=True)
    if not lines or max(lines) > len(content):
        return None
    digest = hashlib.sha256()
    for number in lines:
        digest.update(str(number).encode() + b"\0" + content[number - 1])
    return digest.hexdigest()


def _normal_repository(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _answer_bearing(value: str) -> bool:
    return bool(ANSWER_WORDS.intersection(re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)*", value.lower())))


def _offline_git_source(root: Path, source: GitSource) -> Path | None:
    key = hashlib.sha256(f"{source.url}\n{source.commit}".encode()).hexdigest()[:24]
    cache_root = Path(os.environ.get("CORSAIR_SOURCES") or root / ".runs/sources")
    checkout = cache_root / key
    marker = checkout / ".corsair-complete"
    try:
        if marker.read_text() != f"{source.url}\n{source.commit}\n":
            return None
        tree = (checkout / source.subdir).resolve(strict=True) if source.subdir else checkout.resolve(strict=True)
        return tree if tree.is_dir() and tree.is_relative_to(checkout.resolve(strict=True)) else None
    except (OSError, RuntimeError):
        return None


def _local_source(root: Path, case_dir: Path, value: str) -> Path | None:
    relative = Path(value)
    if not value or relative.is_absolute() or "\0" in value:
        return None
    try:
        candidate = (case_dir / relative).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return (candidate if candidate.is_dir() and candidate != case_dir and candidate.is_relative_to(case_dir)
            and candidate.is_relative_to(root) else None)


def _regular_file(path: Path, boundary: Path) -> bool:
    try:
        return (path.resolve(strict=True).is_relative_to(boundary) and path.is_file() and not path.is_symlink()
                and stat.S_ISREG(path.stat().st_mode))
    except (OSError, RuntimeError):
        return False


EvidenceResolver = Callable[[str, str], bytes | None]


def _immutable_evidence_url(url: str, revision: str) -> bool:
    parsed = urlsplit(url)
    marker = revision.removeprefix("sha256:")
    segments = [part for part in parsed.path.split("/") if part]
    return not (parsed.username or parsed.password or parsed.query or parsed.fragment or marker not in segments
                or any(part.lower() in {"main", "master", "head", "latest"} for part in segments))


def _cached_evidence(root: Path, url: str, revision: str) -> bytes | None:
    """Read immutable evidence from a local checkout or the current Git object database; never fetch."""
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    raw_revision = revision.removeprefix("sha256:")
    try:
        if parsed.netloc.lower() == "github.com" and len(parts) >= 5 and parts[2] == "blob":
            owner, repository, marker_revision = parts[0], parts[1], parts[3]
            evidence_path = "/".join(parts[4:])
            repository_url = f"https://github.com/{owner}/{repository}"
        elif parsed.netloc.lower() == "raw.githubusercontent.com" and len(parts) >= 4:
            owner, repository, marker_revision = parts[0], parts[1], parts[2]
            evidence_path = "/".join(parts[3:])
            repository_url = f"https://github.com/{owner}/{repository}"
        elif len(parts) >= 6 and parts[2:4] == ["-", "blob"]:
            owner, repository, marker_revision = parts[0], parts[1], parts[4]
            evidence_path = "/".join(parts[5:])
            repository_url = f"{parsed.scheme}://{parsed.netloc}/{owner}/{repository}"
        else:
            return None
    except (IndexError, ValueError):
        return None
    if marker_revision != raw_revision or revision.startswith("sha256:"):
        return None
    corsair = _normal_repository("https://github.com/X-McKay/corsair")
    if _normal_repository(repository_url) == corsair:
        result = subprocess.run(["git", "-C", str(root), "show", f"{raw_revision}:{evidence_path}"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        return result.stdout if result.returncode == 0 else None
    source = GitSource(url=repository_url, commit=raw_revision)
    checkout = _offline_git_source(root, source)
    if checkout is None:
        return None
    evidence = checkout / evidence_path
    return evidence.read_bytes() if _regular_file(evidence, checkout) else None


def _sorted_issues(issues: list[CorpusIssue]) -> tuple[CorpusIssue, ...]:
    return tuple(sorted(issues, key=lambda issue: (issue.code, issue.path or "", issue.case_ids, issue.message)))


def validate_corpus(root: Path, *, _evidence_resolver: EvidenceResolver | None = None) -> CorpusReport:
    """Validate benchmark provenance and isolation offline, without refreshing source or evidence."""
    try:
        root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        issue = CorpusIssue(severity="error", code="PATH_ESCAPE", message=f"invalid repository root: {error}")
        return CorpusReport(errors=(issue,), case_count=0, family_count=0)
    errors: list[CorpusIssue] = []
    warnings: list[CorpusIssue] = []

    def add(code: str, message: str, *, path: Path | str | None = None,
            case_ids: tuple[str, ...] = (), warning: bool = False) -> None:
        shown = None
        if path is not None:
            try:
                shown = Path(path).relative_to(root).as_posix()
            except (ValueError, TypeError):
                shown = str(path)
        issue = CorpusIssue(severity="review_required" if warning else "error", code=code, path=shown,
                            case_ids=tuple(sorted(case_ids)), message=message)
        (warnings if warning else errors).append(issue)

    dataset = root / "benchmarks/dataset"
    try:
        manifest = load_manifest(dataset / "manifest.json")
    except (OSError, ValidationError, ValueError) as error:
        add("MANIFEST_INVALID", str(error), path=dataset / "manifest.json")
        return CorpusReport(errors=_sorted_issues(errors), case_count=0, family_count=0)
    try:
        quarantine = QuarantineManifest.model_validate_json((dataset / "quarantine.json").read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        add("QUARANTINE_INVALID", str(error), path=dataset / "quarantine.json")
        quarantine = QuarantineManifest(schema="corsair-lite/quarantine/1", entries=())

    quarantined: list[Path] = []
    for entry in quarantine.entries:
        lexical = root / entry.path
        try:
            resolved = lexical.resolve(strict=True)
        except (OSError, RuntimeError):
            add("QUARANTINE_PATH_MISSING", "quarantine path does not exist", path=lexical)
            continue
        if not _inside(resolved, root):
            add("QUARANTINE_PATH_ESCAPE", "quarantine path leaves the repository", path=lexical)
            continue
        if resolved in quarantined:
            add("QUARANTINE_DUPLICATE", "quarantine path is duplicated", path=lexical)
        if any(_inside(resolved, previous) or _inside(previous, resolved) for previous in quarantined):
            add("QUARANTINE_OVERLAP", "quarantine roots overlap", path=lexical)
        quarantined.append(resolved)

    target_text: dict[str, list[str]] = {}
    cases_root = (root / "cases").resolve()
    resolver = _evidence_resolver or (lambda url, revision: _cached_evidence(root, url, revision))
    for case in manifest.cases:
        case_dir = root / "cases" / case.case_id
        try:
            resolved_case = case_dir.resolve(strict=True)
        except (OSError, RuntimeError):
            add("CASE_DIRECTORY_MISSING", "case directory is missing", path=case_dir, case_ids=(case.case_id,))
            resolved_case = case_dir
        if (not resolved_case.is_dir() or not resolved_case.is_relative_to(cases_root)
                or resolved_case.name != case.case_id):
            add("CASE_DIRECTORY_MISSING", "case directory is not an exact child of cases", path=case_dir,
                case_ids=(case.case_id,))
        for value in (case.case_id, case.variant_id or ""):
            if _answer_bearing(value):
                add("ANSWER_BEARING_IDENTITY", "case identity contains an outcome, fix or split token",
                    path=case_dir, case_ids=(case.case_id,))
        input_path = case_dir / "input.json"
        request = None
        try:
            if not _regular_file(input_path, root):
                raise ValueError("input is missing, nonregular or outside the repository")
            request = _Request.model_validate_json(input_path.read_bytes())
        except (OSError, ValidationError, ValueError) as error:
            add("ARTIFACT_MISSING", f"invalid input.json: {error}", path=input_path, case_ids=(case.case_id,))
        if request is not None:
            if request.case_id != case.case_id:
                add("CASE_ID_MISMATCH", "input case_id differs from the manifest", path=input_path,
                    case_ids=(case.case_id,))
            finding = request.finding
            if finding.file_path != case.target.file or finding.symbol != case.target.symbol:
                add("TARGET_IDENTITY_MISMATCH", "input finding target differs from the manifest", path=input_path,
                    case_ids=(case.case_id,))
            if _answer_bearing(f"{finding.title} {finding.description}"):
                add("ANSWER_BEARING_IDENTITY", "agent-visible finding contains an outcome, fix or split token",
                    path=input_path, case_ids=(case.case_id,))

        artifact_specs = (("input.json", case.artifacts.input_sha256), ("oracle.json", case.artifacts.oracle_sha256),
                          ("reference-submission.json", case.artifacts.reference_submission_sha256))
        for filename, expected in artifact_specs:
            path = case_dir / filename
            if not _regular_file(path, root):
                add("ARTIFACT_MISSING", "artifact is missing, nonregular or outside the repository", path=path,
                    case_ids=(case.case_id,))
            elif _sha256(path) != expected:
                add("ARTIFACT_HASH_MISMATCH", "artifact SHA-256 differs from the manifest", path=path,
                    case_ids=(case.case_id,))
        reference_path = case_dir / "reference-submission.json"
        try:
            submission = Submission.model_validate_json(reference_path.read_bytes())
            hypothesis = submission.hypothesis
            if (hypothesis.target_file != case.target.file or hypothesis.target_symbol != case.target.symbol
                    or hypothesis.target_lines != case.target.lines):
                add("REFERENCE_TARGET_MISMATCH", "reference hypothesis differs from manifest target", path=reference_path,
                    case_ids=(case.case_id,))
        except (OSError, ValidationError, ValueError) as error:
            add("REFERENCE_TARGET_MISMATCH", f"invalid reference submission: {error}", path=reference_path,
                case_ids=(case.case_id,))
        oracle_path = case_dir / "oracle.json"
        try:
            oracle = json.loads(oracle_path.read_text())
            if (oracle.get("expected_label") not in (None, case.expected.vulnerable.label)
                    or oracle.get("expected_fix") not in (None, case.expected.fix)):
                add("ORACLE_EXPECTATION_MISMATCH", "oracle expectation differs from the manifest", path=oracle_path,
                    case_ids=(case.case_id,))
        except (OSError, json.JSONDecodeError) as error:
            add("ORACLE_EXPECTATION_MISMATCH", f"invalid oracle: {error}", path=oracle_path,
                case_ids=(case.case_id,))

        roots: list[Path | None] = [None, None]
        if request is not None:
            for index, (spec, declared, commit) in enumerate((
                    (request.source, case.source_pair.vulnerable, request.commit),
                    (request.fixed_source, case.source_pair.fixed, request.fixed_commit))):
                if spec is None:
                    add("SOURCE_IDENTITY_MISMATCH", "fixed source is absent", path=input_path,
                        case_ids=(case.case_id,))
                    continue
                if isinstance(spec, GitSource):
                    if (_normal_repository(spec.url) != _normal_repository(declared.repository)
                            or spec.commit != declared.commit):
                        add("SOURCE_IDENTITY_MISMATCH", "Git source does not match manifest repository and commit",
                            path=input_path, case_ids=(case.case_id,))
                    roots[index] = _offline_git_source(root, spec)
                    if roots[index] is None:
                        add("SOURCE_NOT_ACQUIRED", "pinned Git source is absent from the offline cache", path=input_path,
                            case_ids=(case.case_id,))
                else:
                    roots[index] = _local_source(root, case_dir, spec)
                    if roots[index] is None:
                        add("PATH_ESCAPE", "local source is missing or leaves the repository", path=input_path,
                            case_ids=(case.case_id,))
                    if commit is not None and commit != declared.commit:
                        add("SOURCE_IDENTITY_MISMATCH", "local source commit differs from the manifest", path=input_path,
                            case_ids=(case.case_id,))
        if all(root_path is not None for root_path in roots):
            vulnerable, fixed = roots[0], roots[1]
            assert vulnerable is not None and fixed is not None
            for path in (resolved_case, vulnerable, fixed):
                if any(_inside(path, quarantined_root) for quarantined_root in quarantined):
                    add("QUARANTINE_SELECTION_LEAK", "case material enters a quarantined root", path=path,
                        case_ids=(case.case_id,))
            for revision_name, source_root, declared in (("vulnerable", vulnerable, case.source_pair.vulnerable),
                                                          ("fixed", fixed, case.source_pair.fixed)):
                if tree_sha256(source_root) != declared.tree_sha256:
                    add("SOURCE_TREE_HASH_MISMATCH", f"{revision_name} tree hash differs", path=source_root,
                        case_ids=(case.case_id,))
                target = source_root / case.target.file
                if not _regular_file(target, source_root):
                    add("TARGET_FILE_MISSING", f"{revision_name} target is absent or nonregular", path=target,
                        case_ids=(case.case_id,))
                    continue
                if _sha256(target) != declared.affected_file_sha256:
                    add("AFFECTED_FILE_HASH_MISMATCH", f"{revision_name} target hash differs", path=target,
                        case_ids=(case.case_id,))
                region = _region_sha256(target, case.target.lines)
                if region is None:
                    add("TARGET_LINE_OUT_OF_RANGE", f"{revision_name} target lines are out of range", path=target,
                        case_ids=(case.case_id,))
                elif region != declared.affected_region_sha256:
                    add("AFFECTED_REGION_HASH_MISMATCH", f"{revision_name} region hash differs", path=target,
                        case_ids=(case.case_id,))
                try:
                    target_text[f"{case.case_id}:{revision_name}"] = [line for line in target.read_text().splitlines()
                                                                      if line.strip()]
                except OSError:
                    pass
            if _patch_sha256(vulnerable, fixed) != case.source_pair.patch_sha256:
                add("PATCH_HASH_MISMATCH", "canonical patch hash differs", path=case_dir,
                    case_ids=(case.case_id,))

        required = set(RIGHTS_LAYERS)
        present = {record.layer for record in case.rights}
        for missing in sorted(required - present):
            add("RIGHTS_LAYER_MISSING", f"missing rights layer: {missing}", path=case_dir,
                case_ids=(case.case_id,))
        source_revisions = {record.evidence_revision for record in case.rights if record.layer == "target_source"}
        for revision in (case.source_pair.vulnerable.commit, case.source_pair.fixed.commit):
            if revision not in source_revisions:
                add("RIGHTS_SOURCE_REVISION_MISSING", f"target-source rights omit revision {revision}", path=case_dir,
                    case_ids=(case.case_id,))
        for record in case.rights:
            expression = record.license_expression.strip().upper()
            if expression in {"NOASSERTION", "NONE"}:
                add("RIGHTS_NOASSERTION", "rights use NOASSERTION/NONE", path=case_dir,
                    case_ids=(case.case_id,))
            if not expression or expression in {"TODO", "UNKNOWN", "TBD"}:
                add("RIGHTS_PLACEHOLDER", "rights use a placeholder license", path=case_dir,
                    case_ids=(case.case_id,))
            if "NONCOMMERCIAL" in expression or re.search(r"(?:^|-)NC(?:-|$)", expression):
                add("RIGHTS_NONCOMMERCIAL", "noncommercial rights cannot enter a scored set", path=case_dir,
                    case_ids=(case.case_id,))
            if not _immutable_evidence_url(record.evidence_url, record.evidence_revision):
                add("RIGHTS_MUTABLE_EVIDENCE", "rights evidence URL is mutable or not revision-local", path=case_dir,
                    case_ids=(case.case_id,))
            if record.reviewed_at > date.today():
                add("RIGHTS_FUTURE_REVIEW", "rights review date is in the future", path=case_dir,
                    case_ids=(case.case_id,))
            if not record.reviewer.strip() or record.reviewer.strip().upper() in {"TODO", "TBD", "UNKNOWN", "NONE"}:
                add("RIGHTS_REVIEWER_MISSING", "rights reviewer is blank or a placeholder", path=case_dir,
                    case_ids=(case.case_id,))
            evidence = resolver(record.evidence_url, record.evidence_revision)
            if evidence is None:
                add("RIGHTS_EVIDENCE_UNAVAILABLE", "rights evidence is unavailable offline", path=case_dir,
                    case_ids=(case.case_id,))
            elif hashlib.sha256(evidence).hexdigest() != record.evidence_sha256:
                add("RIGHTS_EVIDENCE_HASH_MISMATCH", "rights evidence SHA-256 differs", path=case_dir,
                    case_ids=(case.case_id,))
        if not _immutable_evidence_url(case.finding_provenance.source_url,
                                       case.finding_provenance.source_revision):
            add("PROVENANCE_MUTABLE_EVIDENCE", "finding provenance is mutable or not revision-local", path=case_dir,
                case_ids=(case.case_id,))
        provenance = resolver(case.finding_provenance.source_url, case.finding_provenance.source_revision)
        if provenance is None:
            add("PROVENANCE_EVIDENCE_UNAVAILABLE", "finding provenance is unavailable offline", path=case_dir,
                case_ids=(case.case_id,))
        elif hashlib.sha256(provenance).hexdigest() != case.finding_provenance.sha256:
            add("PROVENANCE_HASH_MISMATCH", "finding provenance SHA-256 differs", path=case_dir,
                case_ids=(case.case_id,))

        receipts = ([case.review_receipt] if case.review_receipt is not None else []) + list(case.replay_receipts)
        for receipt in receipts:
            receipt_path = dataset / receipt.path
            if not _regular_file(receipt_path, dataset.resolve()):
                add("RECEIPT_MISSING", "declared receipt is missing or escapes the dataset", path=receipt_path,
                    case_ids=(case.case_id,))
            elif _sha256(receipt_path) != receipt.sha256:
                add("RECEIPT_HASH_MISMATCH", "receipt SHA-256 differs", path=receipt_path,
                    case_ids=(case.case_id,))
            try:
                resolved_receipt = receipt_path.resolve(strict=True)
                if any(_inside(resolved_receipt, q) for q in quarantined):
                    add("QUARANTINE_SELECTION_LEAK", "receipt enters a quarantined root", path=receipt_path,
                        case_ids=(case.case_id,))
            except (OSError, RuntimeError):
                pass

    families = {case.family_id for case in manifest.cases}
    family_cases: dict[str, list[DatasetCase]] = defaultdict(list)
    for case in manifest.cases:
        family_cases[case.family_id].append(case)
    for family_id, members in family_cases.items():
        if len({member.split for member in members}) > 1:
            add("FAMILY_SPLIT_LEAKAGE", f"family {family_id} spans splits",
                case_ids=tuple(member.case_id for member in members))

    collision_specs = (
        ("ALIAS_FAMILY_COLLISION", lambda c: tuple(sorted(alias.strip().upper() for alias in c.aliases))),
        ("SOURCE_PAIR_FAMILY_COLLISION", lambda c: (_normal_repository(c.source_pair.vulnerable.repository),
                                                     _normal_repository(c.source_pair.fixed.repository),
                                                     c.source_pair.vulnerable.commit,
                                                     c.source_pair.fixed.commit)),
        ("PATCH_FAMILY_COLLISION", lambda c: c.source_pair.patch_sha256),
    )
    for code, key_for in collision_specs:
        groups: dict[object, list[DatasetCase]] = defaultdict(list)
        for case in manifest.cases:
            keys = key_for(case)
            if code == "ALIAS_FAMILY_COLLISION":
                for key in keys:
                    groups[key].append(case)
            else:
                groups[keys].append(case)
        for key, members in groups.items():
            distinct = {member.family_id for member in members}
            if len(distinct) > 1:
                ids = tuple(sorted({member.case_id for member in members}))
                add(code, f"distinct families share {key!r}", case_ids=ids)
    region_groups: dict[tuple[str, str], list[DatasetCase]] = defaultdict(list)
    for case in manifest.cases:
        for revision in (case.source_pair.vulnerable, case.source_pair.fixed):
            region_groups[(case.language, revision.affected_region_sha256)].append(case)
    for key, members in region_groups.items():
        if len({member.family_id for member in members}) > 1:
            add("AFFECTED_REGION_FAMILY_COLLISION", f"distinct families share region {key[1]}",
                case_ids=tuple(sorted({member.case_id for member in members})))

    for index, first in enumerate(manifest.cases):
        for second in manifest.cases[index + 1:]:
            if first.family_id == second.family_id or first.language != second.language:
                continue
            same_seam = (_normal_repository(first.source_pair.vulnerable.repository)
                         == _normal_repository(second.source_pair.vulnerable.repository)
                         and first.target.file == second.target.file and first.target.symbol == second.target.symbol)
            first_lines = target_text.get(f"{first.case_id}:vulnerable", [])
            second_lines = target_text.get(f"{second.case_id}:vulnerable", [])
            similar = (len(first_lines) >= 5 and len(second_lines) >= 5
                       and difflib.SequenceMatcher(None, first_lines, second_lines).ratio() >= 0.90)
            if same_seam or similar:
                add("SOURCE_SIMILARITY_REVIEW", "distinct families have highly similar source or the same seam",
                    case_ids=(first.case_id, second.case_id), warning=True)

    return CorpusReport(errors=_sorted_issues(errors), warnings=_sorted_issues(warnings),
                        case_count=len(manifest.cases), family_count=len(families))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the evaluator-only Corsair benchmark corpus offline")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    report = validate_corpus(Path(args.root))
    for issue in (*report.errors, *report.warnings):
        level = "ERROR" if issue.severity == "error" else "REVIEW"
        location = f" {issue.path}" if issue.path else ""
        cases = f" cases={','.join(issue.case_ids)}" if issue.case_ids else ""
        print(f"{level} {issue.code}{location}:{cases} {issue.message}")
    print(f"corpus-check: {'PASS' if report.ok else 'FAIL'}; {report.case_count} cases; "
          f"{report.family_count} families; {len(report.errors)} errors; {len(report.warnings)} review warnings")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

