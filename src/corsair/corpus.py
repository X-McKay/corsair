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
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationError, field_validator, model_validator

from .case import Frozen, GitSource, SafePath, _Request, _has_ascii_control, tree_sha256
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
SIMILARITY_READ_LIMIT = 256 * 1024
MANDATORY_QUARANTINE = {
    "evals/e2e": frozenset({"rights_unreviewed", "stale_probe_contract", "stale_oracle_semantics",
                             "answer_bearing_metadata", "unsupported_scope"}),
    "benchmarks/corpus/infosec-harness": frozenset({"rights_unreviewed", "stale_oracle_semantics",
                                                     "answer_bearing_metadata"}),
}


def _https(value: str) -> str:
    if (_has_ascii_control(value) or not value.startswith("https://")
            or any(character.isspace() for character in value)):
        raise ValueError("an HTTPS URL without ASCII control characters is required")
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
    harness_path: SafePath | None = None
    harness_sha256: Sha256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _paired_harness_identity(self) -> "ArtifactHashes":
        if (self.harness_path is None) != (self.harness_sha256 is None):
            raise ValueError("harness_path and harness_sha256 must be declared together")
        return self


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


def _normal_repository(value: str) -> str | None:
    """Return one conservative HTTPS repository identity, or ``None`` for an adorned/invalid URL."""
    if _has_ascii_control(value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme.lower() != "https" or not parsed.netloc or parsed.hostname is None
            or parsed.username is not None or parsed.password is not None or (port is not None and port < 1)
            or "?" in value or "#" in value or any(character.isspace() for character in value)
            or not parsed.path.startswith("/") or parsed.path in {"", "/"} or parsed.path.endswith("//")):
        return None
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    if path.endswith(".git"):
        path = path[:-4]
    if not path or path == "/" or path.endswith("/"):
        return None
    return urlunsplit(("https", parsed.netloc.lower(), path, "", ""))


def _same_repository(left: str, right: str) -> bool:
    normalized_left = _normal_repository(left)
    normalized_right = _normal_repository(right)
    return normalized_left is not None and normalized_right is not None and normalized_left == normalized_right


def _run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Run a read-only Git command without lazy object acquisition or an interactive prompt."""
    environment = os.environ.copy()
    for name in tuple(environment):
        if (name in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CEILING_DIRECTORIES",
                     "GIT_CONFIG"} or name.startswith("GIT_CONFIG_")):
            environment.pop(name, None)
    environment.update({
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    })
    return subprocess.run(["git", "-C", str(root), *arguments], env=environment, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


class _GitTreeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _git_tree_sha256(source_root: Path, declared: SourceRevision) -> str:
    """Hash the declared source subtree directly from locally available Git objects."""
    top_level_result = _run_git(source_root, "rev-parse", "--show-toplevel")
    inside_result = _run_git(source_root, "rev-parse", "--is-inside-work-tree")
    if (top_level_result.returncode != 0 or inside_result.returncode != 0
            or inside_result.stdout.strip() != b"true"):
        raise _GitTreeError("LOCAL_SOURCE_GIT_UNAVAILABLE",
                            "local source is not inside a readable Git worktree")
    try:
        top_level = Path(top_level_result.stdout.decode("utf-8").strip()).resolve(strict=True)
        relative_source = source_root.relative_to(top_level).as_posix()
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as error:
        raise _GitTreeError("LOCAL_SOURCE_GIT_UNAVAILABLE",
                            "local source cannot be tied to its containing Git worktree") from error
    if not relative_source or relative_source == ".":
        raise _GitTreeError("LOCAL_SOURCE_TREE_UNSUPPORTED",
                            "the repository root cannot be used as a local source snapshot")

    origin_result = _run_git(top_level, "config", "--get-all", "remote.origin.url")
    try:
        origins = [line for line in origin_result.stdout.decode("utf-8").splitlines() if line]
    except UnicodeDecodeError as error:
        raise _GitTreeError("LOCAL_SOURCE_REPOSITORY_MISMATCH",
                            "the Git origin is not a valid repository identity") from error
    if (origin_result.returncode != 0 or not origins
            or any(not _same_repository(origin, declared.repository) for origin in origins)):
        raise _GitTreeError("LOCAL_SOURCE_REPOSITORY_MISMATCH",
                            "the containing Git worktree origin differs from the declared repository")

    commit_result = _run_git(top_level, "cat-file", "-e", f"{declared.commit}^{{commit}}")
    if commit_result.returncode != 0:
        raise _GitTreeError("LOCAL_SOURCE_COMMIT_UNAVAILABLE",
                            "the declared commit object is unavailable offline")

    treeish = f"{declared.commit}:{relative_source}"
    type_result = _run_git(top_level, "cat-file", "-t", treeish)
    if type_result.returncode != 0:
        raise _GitTreeError("LOCAL_SOURCE_COMMIT_PATH_MISSING",
                            "the local source path is absent from the declared commit")
    if type_result.stdout.strip() != b"tree":
        raise _GitTreeError("LOCAL_SOURCE_TREE_UNSUPPORTED",
                            "the local source path is not a tree at the declared commit")

    listing = _run_git(top_level, "ls-tree", "-r", "-z", treeish)
    if listing.returncode != 0:
        raise _GitTreeError("LOCAL_SOURCE_COMMIT_PATH_MISSING",
                            "the declared source tree cannot be read offline")
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw_entry in listing.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            header, raw_path = raw_entry.split(b"\t", 1)
            mode_bytes, kind, object_id = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            relative = raw_path.decode("utf-8")
            oid = object_id.decode("ascii")
        except (UnicodeDecodeError, ValueError) as error:
            raise _GitTreeError("LOCAL_SOURCE_TREE_UNSUPPORTED",
                                "the declared source tree has an invalid entry") from error
        path = PurePosixPath(relative)
        if (kind != b"blob" or mode not in {"100644", "100755", "120000"}
                or path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts)
                or relative in seen):
            raise _GitTreeError("LOCAL_SOURCE_TREE_UNSUPPORTED",
                                "the declared source tree contains a non-blob, unsupported mode or unsafe path")
        seen.add(relative)
        blob = _run_git(top_level, "cat-file", "blob", oid)
        if blob.returncode != 0:
            raise _GitTreeError("LOCAL_SOURCE_COMMIT_UNAVAILABLE",
                                "a declared source blob is unavailable offline")
        entries.append((relative, mode, hashlib.sha256(blob.stdout).hexdigest()))

    digest = hashlib.sha256()
    for relative, mode, content in sorted(entries):
        digest.update(f"{relative}\0{mode}\0{content}\n".encode())
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _answer_bearing_identity(value: str) -> bool:
    return bool(ANSWER_WORDS.intersection(re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)*", value.lower())))


def _answer_bearing_finding(value: str) -> bool:
    """Reject explicit evaluator labels and status fields while allowing ordinary security prose."""
    label = r"(?:likely[_ -]+not[_ -]+exploitable|likely[_ -]+exploitable|inconclusive|unable[_ -]+to[_ -]+run)"
    status = r"(?:verified|not[_ -]+verified)"
    return bool(re.search(rf"\b{label}\b", value, re.IGNORECASE)
                or re.search(r"\b(?:expected_label|expected_fix|oracle[_ ]+label|ground[_ ]+truth)\b",
                             value, re.IGNORECASE)
                or re.search(
                    rf"(?<!\w)[\"']?(?:fix|fix[_ ]+status|status)[\"']?\s*[:=]\s*"
                    rf"[\"']?(?:{label}|{status})[\"']?(?!\w)", value, re.IGNORECASE))


def _license_tokens(expression: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Z0-9]+", expression.upper()))


def _git_url_variants(url: str) -> tuple[str, ...]:
    """Return equivalent repository spellings while preserving every other URL component."""
    if _has_ascii_control(url):
        return ()
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ()
    path = parsed.path.rstrip("/")
    repository_path = path[:-4] if path.endswith(".git") else path
    paths = (repository_path, f"{repository_path}/", f"{repository_path}.git", f"{repository_path}.git/")
    variants: list[str] = []
    for candidate_path in paths:
        candidate = urlunsplit((parsed.scheme, parsed.netloc, candidate_path, parsed.query, parsed.fragment))
        if candidate not in variants:
            variants.append(candidate)
    return tuple(variants)


def _offline_git_source(root: Path, source: GitSource) -> Path | None:
    cache_root = Path(os.environ.get("CORSAIR_SOURCES") or root / ".runs/sources")
    try:
        cache_boundary = cache_root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    for candidate_url in _git_url_variants(source.url):
        key = hashlib.sha256(f"{candidate_url}\n{source.commit}".encode()).hexdigest()[:24]
        checkout = cache_root / key
        try:
            boundary = checkout.resolve(strict=True)
            if boundary == cache_boundary or not boundary.is_relative_to(cache_boundary):
                continue
            marker = boundary / ".corsair-complete"
            if (not _regular_file(marker, boundary)
                    or marker.read_bytes() != f"{candidate_url}\n{source.commit}\n".encode()):
                continue
            tree = (boundary / source.subdir).resolve(strict=True) if source.subdir else boundary
            if tree.is_dir() and tree.is_relative_to(boundary):
                return tree
        except (OSError, RuntimeError, ValueError):
            continue
    return None


def _local_source(root: Path, case_dir: Path, value: str) -> Path | None:
    relative = Path(value)
    if (not value or _has_ascii_control(value) or relative.is_absolute() or relative.as_posix() != value
            or ".." in relative.parts
            or any((case_dir.joinpath(*relative.parts[:index])).is_symlink()
                   for index in range(1, len(relative.parts) + 1))):
        return None
    try:
        candidate = (case_dir / relative).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    return (candidate if candidate.is_dir() and candidate != case_dir and candidate.is_relative_to(case_dir)
            and candidate.is_relative_to(root) else None)


def _regular_file(path: Path, boundary: Path) -> bool:
    try:
        return (path.resolve(strict=True).is_relative_to(boundary) and path.is_file() and not path.is_symlink()
                and stat.S_ISREG(path.stat().st_mode))
    except (OSError, RuntimeError, ValueError):
        return False


def _aliases_file_in_tree(path: Path, root: Path) -> bool:
    """Return whether a regular path shares an inode with any file in a source snapshot."""
    try:
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name != ".git")
            for filename in sorted(filenames):
                if os.path.samefile(path, Path(directory) / filename):
                    return True
    except (OSError, ValueError):
        return True
    return False


EvidenceResolver = Callable[[str, str], bytes | None]


def _immutable_evidence_url(url: str, revision: str) -> bool:
    if _has_ascii_control(url):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    marker = revision.removeprefix("sha256:")
    segments = [part for part in parsed.path.split("/") if part]
    return not (parsed.username or parsed.password or parsed.query or parsed.fragment or marker not in segments
                or any(part.lower() in {"main", "master", "head", "latest"} for part in segments))


def _evidence_location(url: str, revision: str) -> tuple[str, str] | None:
    """Extract the repository identity and file from a supported immutable evidence URL."""
    if _has_ascii_control(url):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    raw_revision = revision.removeprefix("sha256:")
    if revision.startswith("sha256:"):
        return None
    if parsed.netloc.lower() == "raw.githubusercontent.com" and len(parts) >= 4:
        owner, repository, marker_revision = parts[0], parts[1], parts[2]
        evidence_path = "/".join(parts[3:])
        repository_url = f"https://github.com/{owner}/{repository}"
    elif len(parts) >= 5 and parts[2] == "blob":
        owner, repository, marker_revision = parts[0], parts[1], parts[3]
        evidence_path = "/".join(parts[4:])
        repository_url = f"{parsed.scheme}://{parsed.netloc}/{owner}/{repository}"
    elif len(parts) >= 6 and parts[2:4] == ["-", "blob"]:
        owner, repository, marker_revision = parts[0], parts[1], parts[4]
        evidence_path = "/".join(parts[5:])
        repository_url = f"{parsed.scheme}://{parsed.netloc}/{owner}/{repository}"
    else:
        return None
    if marker_revision != raw_revision or not evidence_path:
        return None
    return repository_url, evidence_path


def _cached_evidence(root: Path, url: str, revision: str) -> bytes | None:
    """Read immutable evidence from a local checkout or the current Git object database; never fetch."""
    raw_revision = revision.removeprefix("sha256:")
    location = _evidence_location(url, revision)
    if location is None:
        return None
    repository_url, evidence_path = location
    if _same_repository(repository_url, "https://github.com/X-McKay/corsair"):
        result = _run_git(root, "show", f"{raw_revision}:{evidence_path}")
        return result.stdout if result.returncode == 0 else None
    source = GitSource(url=repository_url, commit=raw_revision)
    checkout = _offline_git_source(root, source)
    if checkout is None:
        return None
    evidence = checkout / evidence_path
    return evidence.read_bytes() if _regular_file(evidence, checkout) else None


def _similarity_lines(path: Path) -> list[str]:
    """Read at most 256 KiB of strict UTF-8 for heuristic source comparison."""
    with path.open("rb") as stream:
        content = stream.read(SIMILARITY_READ_LIMIT + 1)
    if len(content) > SIMILARITY_READ_LIMIT:
        raise ValueError(f"source exceeds the {SIMILARITY_READ_LIMIT}-byte similarity limit")
    return [line for line in content.decode("utf-8").splitlines() if line.strip()]


def _sorted_issues(issues: list[CorpusIssue]) -> tuple[CorpusIssue, ...]:
    return tuple(sorted(issues, key=lambda issue: (issue.code, issue.path or "", issue.case_ids, issue.message)))


def validate_corpus(root: Path, *, manifest_path: Path | None = None,
                    _evidence_resolver: EvidenceResolver | None = None) -> CorpusReport:
    """Validate benchmark provenance and isolation offline, without refreshing source or evidence."""
    try:
        root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
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
    chosen_manifest = Path(manifest_path) if manifest_path is not None else dataset / "manifest.json"
    if not chosen_manifest.is_absolute():
        chosen_manifest = root / chosen_manifest
    try:
        resolved_dataset = dataset.resolve(strict=True)
        resolved_manifest = chosen_manifest.resolve(strict=True)
        if (chosen_manifest.is_symlink() or not chosen_manifest.is_file()
                or resolved_manifest.parent != resolved_dataset):
            raise ValueError("manifest must be a regular file directly below benchmarks/dataset")
        manifest = load_manifest(resolved_manifest)
    except (OSError, ValidationError, ValueError) as error:
        add("MANIFEST_INVALID", str(error), path=chosen_manifest)
        return CorpusReport(errors=_sorted_issues(errors), case_count=0, family_count=0)
    try:
        quarantine = QuarantineManifest.model_validate_json((dataset / "quarantine.json").read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        add("QUARANTINE_INVALID", str(error), path=dataset / "quarantine.json")
        quarantine = QuarantineManifest(schema="corsair-lite/quarantine/1", entries=())

    quarantined: list[Path] = []
    quarantine_by_path: dict[Path, QuarantineEntry] = {}
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
        quarantine_by_path[resolved] = entry

    for relative, reasons in MANDATORY_QUARANTINE.items():
        historical = root / relative
        if not historical.exists():
            continue
        try:
            resolved_historical = historical.resolve(strict=True)
        except (OSError, RuntimeError):
            add("QUARANTINE_REQUIRED_ENTRY_MISSING", "historical corpus root has no exact quarantine entry",
                path=historical)
            continue
        entry = quarantine_by_path.get(resolved_historical)
        if entry is None or entry.path != relative:
            add("QUARANTINE_REQUIRED_ENTRY_MISSING", "historical corpus root has no exact quarantine entry",
                path=historical)
            continue
        missing_reasons = sorted(reasons - set(entry.reason_codes))
        if missing_reasons:
            add("QUARANTINE_REASON_MISSING", f"mandatory reasons are absent: {', '.join(missing_reasons)}",
                path=historical)

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
            if _answer_bearing_identity(value):
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
            if _answer_bearing_finding(f"{finding.title} {finding.description}"):
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
        harness_path: Path | None = None
        if case.artifacts.harness_path is not None:
            harness_path = case_dir / case.artifacts.harness_path
            if not _regular_file(harness_path, resolved_case):
                add("HARNESS_MISSING", "harness is missing, nonregular or outside the exact case directory",
                    path=harness_path, case_ids=(case.case_id,))
            else:
                core_artifacts = [case_dir / name for name, _ in artifact_specs]
                try:
                    aliases_core = any(os.path.samefile(harness_path, artifact) for artifact in core_artifacts)
                except OSError:
                    aliases_core = True
                if aliases_core:
                    add("HARNESS_ALIAS", "harness aliases a core case artifact", path=harness_path,
                        case_ids=(case.case_id,))
                elif _sha256(harness_path) != case.artifacts.harness_sha256:
                    add("HARNESS_HASH_MISMATCH", "harness SHA-256 differs from the manifest", path=harness_path,
                        case_ids=(case.case_id,))
                if any(_inside(harness_path.resolve(), quarantined_root) for quarantined_root in quarantined):
                    add("QUARANTINE_SELECTION_LEAK", "harness enters a quarantined root", path=harness_path,
                        case_ids=(case.case_id,))
        reference_path = case_dir / "reference-submission.json"
        try:
            submission = Submission.model_validate_json(reference_path.read_bytes())
            hypothesis = submission.hypothesis
            if (hypothesis.target_file != case.target.file or hypothesis.target_symbol != case.target.symbol
                    or hypothesis.target_lines != case.target.lines):
                add("REFERENCE_TARGET_MISMATCH", "reference hypothesis differs from manifest target",
                    path=reference_path, case_ids=(case.case_id,))
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
        local_revisions = [False, False]
        if request is not None:
            for index, (spec, declared, commit) in enumerate((
                    (request.source, case.source_pair.vulnerable, request.commit),
                    (request.fixed_source, case.source_pair.fixed, request.fixed_commit))):
                if spec is None:
                    add("SOURCE_IDENTITY_MISMATCH", "fixed source is absent", path=input_path,
                        case_ids=(case.case_id,))
                    continue
                if commit != declared.commit:
                    add("SOURCE_IDENTITY_MISMATCH", "input commit is absent or differs from the manifest",
                        path=input_path, case_ids=(case.case_id,))
                if isinstance(spec, GitSource):
                    if (not _same_repository(spec.url, declared.repository) or spec.commit != declared.commit):
                        add("SOURCE_IDENTITY_MISMATCH", "Git source does not match manifest repository and commit",
                            path=input_path, case_ids=(case.case_id,))
                    roots[index] = _offline_git_source(root, spec)
                    if roots[index] is None:
                        add("SOURCE_NOT_ACQUIRED", "pinned Git source is absent from the offline cache",
                            path=input_path, case_ids=(case.case_id,))
                else:
                    local_revisions[index] = True
                    roots[index] = _local_source(root, case_dir, spec)
                    if roots[index] is None:
                        add("PATH_ESCAPE", "local source is missing or leaves the repository", path=input_path,
                            case_ids=(case.case_id,))
        if all(root_path is not None for root_path in roots):
            vulnerable, fixed = roots[0], roots[1]
            assert vulnerable is not None and fixed is not None
            for path in (resolved_case, vulnerable, fixed):
                if any(_inside(path, quarantined_root) for quarantined_root in quarantined):
                    add("QUARANTINE_SELECTION_LEAK", "case material enters a quarantined root", path=path,
                        case_ids=(case.case_id,))
            if harness_path is not None and _regular_file(harness_path, resolved_case):
                try:
                    aliases_source = any(
                        _inside(harness_path.resolve(strict=True), source_root.resolve(strict=True))
                        or _aliases_file_in_tree(harness_path, source_root)
                        for source_root in (vulnerable, fixed)
                    )
                    if aliases_source:
                        add("HARNESS_ALIAS", "harness aliases a declared source snapshot", path=harness_path,
                            case_ids=(case.case_id,))
                except (OSError, RuntimeError):
                    add("HARNESS_ALIAS", "harness/source nonaliasing could not be verified", path=harness_path,
                        case_ids=(case.case_id,))
            for index, (revision_name, source_root, declared) in enumerate((
                    ("vulnerable", vulnerable, case.source_pair.vulnerable),
                    ("fixed", fixed, case.source_pair.fixed))):
                actual_tree_sha256 = tree_sha256(source_root)
                if local_revisions[index]:
                    try:
                        committed_tree_sha256 = _git_tree_sha256(source_root, declared)
                    except _GitTreeError as error:
                        add(error.code, str(error), path=source_root, case_ids=(case.case_id,))
                    else:
                        if (committed_tree_sha256 != actual_tree_sha256
                                or committed_tree_sha256 != declared.tree_sha256):
                            add("LOCAL_SOURCE_COMMIT_MISMATCH",
                                f"{revision_name} local bytes do not match the declared commit tree",
                                path=source_root, case_ids=(case.case_id,))
                if actual_tree_sha256 != declared.tree_sha256:
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
                    target_text[f"{case.case_id}:{revision_name}"] = _similarity_lines(target)
                except (OSError, UnicodeDecodeError, ValueError) as error:
                    add("SOURCE_SIMILARITY_UNAVAILABLE", f"source cannot be compared safely: {error}", path=target,
                        case_ids=(case.case_id,), warning=True)
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
        for index, declared in enumerate((case.source_pair.vulnerable, case.source_pair.fixed)):
            if not local_revisions[index]:
                continue
            records = [record for record in case.rights
                       if record.layer == "target_source" and record.evidence_revision == declared.commit]
            vendored = [record for record in records if record.redistribution_mode == "vendored"]
            if not vendored:
                add("LOCAL_SOURCE_PROVENANCE_UNVERIFIED",
                    "local snapshots require vendored rights for the exact declared revision", path=case_dir,
                    case_ids=(case.case_id,))
            repositories = {normalized for record in vendored
                            if (location := _evidence_location(record.evidence_url,
                                                               record.evidence_revision)) is not None
                            if (normalized := _normal_repository(location[0])) is not None}
            declared_repository = _normal_repository(declared.repository)
            if declared_repository is None or declared_repository not in repositories:
                add("RIGHTS_SOURCE_REPOSITORY_MISMATCH",
                    "target-source rights evidence is not tied to the declared repository", path=case_dir,
                    case_ids=(case.case_id,))
        for record in case.rights:
            tokens = _license_tokens(record.license_expression)
            if {"NOASSERTION", "NONE"}.intersection(tokens):
                add("RIGHTS_NOASSERTION", "rights use NOASSERTION/NONE", path=case_dir,
                    case_ids=(case.case_id,))
            if not tokens or {"TODO", "UNKNOWN", "TBD"}.intersection(tokens):
                add("RIGHTS_PLACEHOLDER", "rights use a placeholder license", path=case_dir,
                    case_ids=(case.case_id,))
            if ("NC" in tokens or "NONCOMMERCIAL" in tokens
                    or any(tokens[index:index + 2] == ("NON", "COMMERCIAL")
                           for index in range(len(tokens) - 1))):
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
        if case.status == "qualified":
            from .benchmark import admission_from_manifest

            admission = admission_from_manifest(dataset, manifest, case)
            if not admission.ready:
                add(f"QUALIFICATION_{admission.code}",
                    f"qualified case lacks current admission evidence: {admission.code}",
                    path=case_dir, case_ids=(case.case_id,))

    families = {case.family_id for case in manifest.cases}
    family_cases: dict[str, list[DatasetCase]] = defaultdict(list)
    for case in manifest.cases:
        family_cases[case.family_id].append(case)
    for family_id, members in family_cases.items():
        if len({member.split for member in members}) > 1:
            add("FAMILY_SPLIT_LEAKAGE", f"family {family_id} spans splits",
                case_ids=tuple(member.case_id for member in members))

    def source_pair_collision_key(case: DatasetCase) -> object:
        vulnerable_repository = _normal_repository(case.source_pair.vulnerable.repository)
        fixed_repository = _normal_repository(case.source_pair.fixed.repository)
        if vulnerable_repository is None or fixed_repository is None:
            return ("INVALID_REPOSITORY", case.case_id)
        return (vulnerable_repository, fixed_repository, case.source_pair.vulnerable.commit,
                case.source_pair.fixed.commit)

    collision_specs = (
        ("ALIAS_FAMILY_COLLISION", lambda c: tuple(sorted(alias.strip().upper() for alias in c.aliases))),
        ("SOURCE_PAIR_FAMILY_COLLISION", source_pair_collision_key),
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
            same_seam = (_same_repository(first.source_pair.vulnerable.repository,
                                          second.source_pair.vulnerable.repository)
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

