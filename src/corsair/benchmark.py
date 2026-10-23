"""Evaluator-only trusted reference replay and immutable corpus admission evidence.

This module may read corpus truth, but passes only the small agent-visible :class:`Case` and the checked-in
reference :class:`Submission` to the verdict kernel.  Qualification receipts are append-only evidence; promotion
of a manifest entry remains a separate reviewed change.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from . import matrix
from .artifacts import ArtifactRef, ArtifactStore
from .case import Case, Frozen, SafePath, load_case, tree_sha256
from .corpus import (CorpusReport, DatasetCase, DatasetManifest, EvalSet, load_manifest, validate_corpus)
from .kernel import (AuditResult, Evaluation, Fix, Gate, Kernel, Label, RoleResult, Submission)
from .sandbox import Sandboxes, sandboxes

Sha256 = str
_SHA256 = r"^[0-9a-f]{64}$"
_IMAGE_ID = r"^sha256:[0-9a-f]{64}$"
_CASE_REVISION_DOMAIN = b"corsair-case-revision-v1\0"
_PLACEHOLDER_ATTESTATION = frozenset({"TODO", "TBD", "UNKNOWN", "NONE", "N/A", "NA"})


class ReceiptArtifact(Frozen):
    sha256: Sha256 = Field(pattern=_SHA256)
    size: int = Field(ge=0)


class ReceiptRoleEvidence(Frozen):
    revision: Literal["vulnerable", "fixed"]
    role: Literal["control", "exploit"]
    result: RoleResult
    invariant_held: bool | None
    exception_type: str | None = Field(default=None, max_length=256)
    exit_code: int | None
    junit_tests: int = Field(ge=0)
    covered_target: bool | None
    covered_lines: tuple[int, ...] = ()
    cleanup_confirmed: bool | None
    output: ReceiptArtifact | None = None
    junit: ReceiptArtifact | None = None
    coverage: ReceiptArtifact | None = None


class ReceiptDisposition(Frozen):
    revision: Literal["vulnerable", "fixed"]
    label: Label
    rule: str = Field(pattern=r"^K[0-9]+$")
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class ReplayRecord(Frozen):
    schema_version: Literal["corsair-lite/qualification-replay/1"] = Field(alias="schema")
    qualification_run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    attempt: int = Field(ge=1)
    case_id: str
    family_id: str
    dataset_version: str
    manifest_sha256: Sha256 = Field(pattern=_SHA256)
    case_revision_sha256: Sha256 = Field(pattern=_SHA256)
    input_sha256: Sha256 = Field(pattern=_SHA256)
    oracle_sha256: Sha256 = Field(pattern=_SHA256)
    reference_submission_sha256: Sha256 = Field(pattern=_SHA256)
    vulnerable_tree_sha256: Sha256 = Field(pattern=_SHA256)
    fixed_tree_sha256: Sha256 = Field(pattern=_SHA256)
    runtime_row: str
    runtime_row_sha256: Sha256 = Field(pattern=_SHA256)
    runtime_image_id: str | None = Field(pattern=_IMAGE_ID)
    executor_sha256: Sha256 = Field(pattern=_SHA256)
    started_at: datetime
    finished_at: datetime
    gate: Gate
    source_label: Label | None
    fixed_label: Label | None
    fix: Fix | None
    dispositions: tuple[ReceiptDisposition, ...] = ()
    roles: tuple[ReceiptRoleEvidence, ...] = ()
    cleanup_confirmed: bool
    outcome: Literal["complete", "failed", "infrastructure"]
    failure_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    audit_mode: Literal["trusted_reference"]

    @field_validator("started_at", "finished_at")
    @classmethod
    def _utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("receipt timestamps must be UTC-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _consistent_outcome(self) -> "ReplayRecord":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        if self.outcome == "complete":
            if (self.gate is not Gate.VERIFIED or self.failure_code is not None or not self.cleanup_confirmed
                    or self.source_label is None or self.fixed_label is None or self.fix is None
                    or self.runtime_image_id is None or len(self.dispositions) != 2 or len(self.roles) != 4):
                raise ValueError("a complete replay requires verified paired evidence")
            expected_roles = {("vulnerable", "control"), ("vulnerable", "exploit"),
                              ("fixed", "control"), ("fixed", "exploit")}
            if {(role.revision, role.role) for role in self.roles} != expected_roles:
                raise ValueError("complete replay role evidence must contain each revision and role exactly once")
            for role in self.roles:
                expected_result = (RoleResult.PASS if role.role == "control" or role.revision == "vulnerable"
                                   else RoleResult.FAIL)
                expected_held = role.role == "control" or role.revision == "fixed"
                if (role.result is not expected_result or role.invariant_held is not expected_held
                        or role.exception_type is not None or role.junit_tests != 1
                        or role.exit_code != (0 if role.result is RoleResult.PASS else 1)
                        or role.covered_target is not True or role.cleanup_confirmed is not True
                        or role.output is None or role.junit is None or role.coverage is None):
                    raise ValueError("complete replay role evidence is internally inconsistent")
        elif self.failure_code is None:
            raise ValueError("an incomplete replay requires a stable failure_code")
        return self


class ReviewVariant(Frozen):
    case_id: str
    case_revision_sha256: Sha256 = Field(pattern=_SHA256)


class TechnicalReviewRecord(Frozen):
    """A content-hashed named v1 attestation; no unverified decorative signature is accepted."""

    schema_version: Literal["corsair-lite/technical-review/1"] = Field(alias="schema")
    family_id: str
    variants: tuple[ReviewVariant, ...] = Field(min_length=1)
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: date
    finding_reviewed: bool
    invariant_reviewed: bool
    payloads_reviewed: bool
    expected_results_reviewed: bool
    independence_basis: str = Field(min_length=1, max_length=2_000)

    @field_validator("reviewer", "independence_basis", mode="before")
    @classmethod
    def _substantive_identity(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("review identity fields must be strings")
        normalized = value.strip()
        if not normalized or normalized.upper() in _PLACEHOLDER_ATTESTATION:
            raise ValueError("review identity fields must be substantive")
        return normalized

    @model_validator(mode="after")
    def _unique_variants(self) -> "TechnicalReviewRecord":
        identities = [(variant.case_id, variant.case_revision_sha256) for variant in self.variants]
        if len(identities) != len(set(identities)) or len({item[0] for item in identities}) != len(identities):
            raise ValueError("technical review variants must be unique")
        return self


class AdmissionStatus(Frozen):
    ready: bool
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def case_revision_sha256(case: DatasetCase) -> str:
    """Digest every material case field while excluding only promotion state and receipt pointers."""
    material = case.model_dump(mode="json", exclude={"status", "review_receipt", "replay_receipts"})
    return hashlib.sha256(_CASE_REVISION_DOMAIN + _canonical_bytes(material)).hexdigest()


def admission_status(case: DatasetCase, replays: tuple[ReplayRecord, ...],
                     review: TechnicalReviewRecord | None, *,
                     family_cases: tuple[DatasetCase, ...] | None = None,
                     runtime_row_sha256: str | None = None,
                     executor_sha256: str | None = None) -> AdmissionStatus:
    """Apply the three-fresh-replays plus independent family-review admission rule."""
    revision = case_revision_sha256(case)
    if len(replays) != 3:
        return AdmissionStatus(ready=False, code="REPLAY_TRIO_REQUIRED")
    if tuple(record.attempt for record in replays) != (1, 2, 3):
        return AdmissionStatus(ready=False, code="REPLAY_ATTEMPTS_INVALID")
    if len({record.qualification_run_id for record in replays}) != 1:
        return AdmissionStatus(ready=False, code="REPLAY_RUN_MISMATCH")
    if any(record.case_id != case.case_id or record.family_id != case.family_id
           or record.case_revision_sha256 != revision for record in replays):
        return AdmissionStatus(ready=False, code="REPLAY_REVISION_MISMATCH")
    if any(record.outcome != "complete" for record in replays):
        return AdmissionStatus(ready=False, code="REPLAY_INCOMPLETE")
    controlled = {
        (record.dataset_version, record.manifest_sha256, record.input_sha256, record.oracle_sha256,
         record.reference_submission_sha256, record.vulnerable_tree_sha256, record.fixed_tree_sha256,
         record.runtime_row, record.runtime_row_sha256, record.runtime_image_id, record.executor_sha256)
        for record in replays
    }
    if len(controlled) != 1:
        return AdmissionStatus(ready=False, code="REPLAY_ENVIRONMENT_MISMATCH")
    expected_controlled = (case.artifacts.input_sha256, case.artifacts.oracle_sha256,
                           case.artifacts.reference_submission_sha256, case.source_pair.vulnerable.tree_sha256,
                           case.source_pair.fixed.tree_sha256, case.runtime, case.runtime_image_id)
    actual = replays[0]
    if (actual.input_sha256, actual.oracle_sha256, actual.reference_submission_sha256,
            actual.vulnerable_tree_sha256, actual.fixed_tree_sha256, actual.runtime_row,
            actual.runtime_image_id) != expected_controlled:
        return AdmissionStatus(ready=False, code="REPLAY_MATERIAL_MISMATCH")
    if any(not _receipt_matches_case(case, record) for record in replays):
        return AdmissionStatus(ready=False, code="REPLAY_EXPECTATION_MISMATCH")
    if ((runtime_row_sha256 is not None and actual.runtime_row_sha256 != runtime_row_sha256)
            or (executor_sha256 is not None and actual.executor_sha256 != executor_sha256)):
        return AdmissionStatus(ready=False, code="REPLAY_ENVIRONMENT_STALE")
    if review is None:
        return AdmissionStatus(ready=False, code="REVIEW_REQUIRED")
    if review.family_id != case.family_id or review.decision != "approved":
        return AdmissionStatus(ready=False, code="REVIEW_REJECTED")
    if not all((review.finding_reviewed, review.invariant_reviewed, review.payloads_reviewed,
                review.expected_results_reviewed)):
        return AdmissionStatus(ready=False, code="REVIEW_INCOMPLETE")
    members = family_cases or (case,)
    expected_variants = {(member.case_id, case_revision_sha256(member)) for member in members
                         if member.family_id == case.family_id}
    reviewed_variants = {(variant.case_id, variant.case_revision_sha256) for variant in review.variants}
    if reviewed_variants != expected_variants:
        return AdmissionStatus(ready=False, code="REVIEW_FAMILY_MISMATCH")
    family_authors = {member.finding_provenance.author.strip().casefold() for member in members}
    if review.reviewer.casefold() in family_authors:
        return AdmissionStatus(ready=False, code="REVIEW_NOT_INDEPENDENT")
    if review.reviewed_at > date.today():
        return AdmissionStatus(ready=False, code="REVIEW_FUTURE_DATED")
    if review.reviewed_at < max(record.finished_at.date() for record in replays):
        return AdmissionStatus(ready=False, code="REVIEW_PREDATES_REPLAY")
    return AdmissionStatus(ready=True, code="ADMISSION_READY")


def _receipt_matches_case(case: DatasetCase, record: ReplayRecord) -> bool:
    dispositions = {item.revision: item for item in record.dispositions}
    if set(dispositions) != {"vulnerable", "fixed"} or record.fix != case.expected.fix:
        return False
    if not all(_disposition_matches(case, disposition) for disposition in dispositions.values()):
        return False
    if (record.source_label != dispositions["vulnerable"].label
            or record.fixed_label != dispositions["fixed"].label):
        return False
    roles = {(role.revision, role.role): role for role in record.roles}
    if set(roles) != {("vulnerable", "control"), ("vulnerable", "exploit"),
                     ("fixed", "control"), ("fixed", "exploit")}:
        return False
    return all(role.covered_lines == case.target.lines for role in roles.values())


def receipt_bytes(record: Frozen) -> bytes:
    return _canonical_bytes(record) + b"\n"


def _safe_existing_directory(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except OSError as error:
            raise ValueError(f"receipt directory is unavailable: {current}") from error
        if current.is_symlink():
            raise ValueError(f"receipt directory contains a symlink: {current}")
        if not current.is_dir():
            raise ValueError(f"receipt path component is not a directory: {current}")
    return absolute.resolve(strict=True)


def publish_receipt(receipts_root: Path, case_revision: str, filename: str, record: Frozen) -> Path:
    """Publish canonical receipt bytes with exclusive creation; an existing target is never replaced."""
    if not re.fullmatch(_SHA256[1:-1], case_revision):
        raise ValueError("case revision must be a SHA-256 digest")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}\.json", filename):
        raise ValueError("unsafe receipt filename")
    root = _safe_existing_directory(receipts_root)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, directory_flags)
    revision_fd: int | None = None
    temporary = f".{filename}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    linked_identity: tuple[int, int] | None = None
    publication_complete = False
    try:
        root_info = os.fstat(root_fd)
        path_root_info = root.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or root.is_symlink()
                or (root_info.st_dev, root_info.st_ino) != (path_root_info.st_dev, path_root_info.st_ino)):
            raise ValueError("receipt root identity changed during publication")
        try:
            os.mkdir(case_revision, 0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        except FileExistsError:
            pass
        revision_fd = os.open(case_revision, directory_flags, dir_fd=root_fd)
        revision_info = os.fstat(revision_fd)
        path_revision_info = os.stat(case_revision, dir_fd=root_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(revision_info.st_mode)
                or (revision_info.st_dev, revision_info.st_ino)
                != (path_revision_info.st_dev, path_revision_info.st_ino)):
            raise ValueError("receipt revision directory is unsafe")

        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                             0o600, dir_fd=revision_fd)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(receipt_bytes(record))
                stream.flush()
                os.fsync(stream.fileno())
            temporary_info = os.stat(temporary, dir_fd=revision_fd, follow_symlinks=False)
            os.link(temporary, filename, src_dir_fd=revision_fd, dst_dir_fd=revision_fd,
                    follow_symlinks=False)
            linked_identity = (temporary_info.st_dev, temporary_info.st_ino)
        finally:
            try:
                os.unlink(temporary, dir_fd=revision_fd)
            except FileNotFoundError:
                pass
        os.fsync(revision_fd)

        final_fd = os.open(filename, os.O_RDONLY | nofollow, dir_fd=revision_fd)
        try:
            final_info = os.fstat(final_fd)
        finally:
            os.close(final_fd)
        current_revision_info = os.stat(case_revision, dir_fd=root_fd, follow_symlinks=False)
        current_root_info = root.lstat()
        final = root / case_revision / filename
        current_final_info = final.lstat()
        if ((revision_info.st_dev, revision_info.st_ino)
                != (current_revision_info.st_dev, current_revision_info.st_ino)
                or (root_info.st_dev, root_info.st_ino)
                != (current_root_info.st_dev, current_root_info.st_ino)
                or (final_info.st_dev, final_info.st_ino)
                != (current_final_info.st_dev, current_final_info.st_ino)):
            raise ValueError("receipt directory identity changed during publication")
        if (not stat.S_ISREG(final_info.st_mode) or final_info.st_nlink != 1
                or final.is_symlink()):
            raise ValueError("published receipt is not an exclusive regular file")
        publication_complete = True
        return final
    except (FileNotFoundError, NotADirectoryError) as error:
        raise ValueError("receipt directory identity changed during publication") from error
    finally:
        if revision_fd is not None:
            if linked_identity is not None and not publication_complete:
                try:
                    linked_info = os.stat(filename, dir_fd=revision_fd, follow_symlinks=False)
                    if (linked_info.st_dev, linked_info.st_ino) == linked_identity:
                        os.unlink(filename, dir_fd=revision_fd)
                        os.fsync(revision_fd)
                except FileNotFoundError:
                    pass
            os.close(revision_fd)
        os.close(root_fd)


class QualificationAttempt(Frozen):
    attempt: int = Field(ge=1)
    outcome: Literal["complete", "failed", "infrastructure"]
    failure_code: str | None = None
    path: SafePath
    sha256: Sha256 = Field(pattern=_SHA256)


class QualificationCaseReport(Frozen):
    case_id: str
    family_id: str
    case_revision_sha256: Sha256 = Field(pattern=_SHA256)
    attempts: tuple[QualificationAttempt, ...]
    admission_ready: bool
    admission_code: str


class QualificationReport(Frozen):
    schema_version: Literal["corsair-lite/qualification-report/1"] = Field(
        default="corsair-lite/qualification-report/1", alias="schema")
    dataset_version: str
    eval_set: EvalSet
    qualification_run_id: str
    cases: tuple[QualificationCaseReport, ...]

    @property
    def ok(self) -> bool:
        return bool(self.cases) and all(
            case.attempts and all(attempt.outcome == "complete" for attempt in case.attempts)
            for case in self.cases
        )


def select_qualification_cases(manifest: DatasetManifest, eval_set: EvalSet) -> tuple[DatasetCase, ...]:
    """Select candidate and already-qualified cases for deterministic reference replay."""
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
    return tuple(case for case in manifest.cases
                 if case.status in {"candidate", "qualified"} and case.split in splits)


def runtime_row_sha256(row: matrix.Row) -> str:
    return hashlib.sha256(b"corsair-runtime-row-v1\0" + _canonical_bytes(row)).hexdigest()


def executor_sha256() -> str:
    """Version the trusted files that execute and interpret a reference replay."""
    package = Path(__file__).resolve().parent
    paths = [package / name for name in ("benchmark.py", "kernel.py", "case.py", "matrix.py", "matrix.yaml",
                                         "artifacts.py")]
    paths.extend(sorted((package / "frameworks").rglob("*.py")))
    paths.extend(sorted((package / "sandbox").rglob("*.py")))
    records = [(path.relative_to(package).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
               for path in paths]
    return hashlib.sha256(b"corsair-reference-executor-v1\0" + _canonical_bytes(sorted(records))).hexdigest()


async def _trusted_reference_audit(submission: Submission) -> AuditResult:
    # The independent human review is a separate receipt. This callback only lets the deterministic reference
    # submission traverse the kernel's existing audit prerequisite and deliberately has no evaluator truth input.
    return AuditResult(valid=True, reason="trusted reference replay; independent review is recorded separately")


def _artifact(ref: ArtifactRef | None) -> ReceiptArtifact | None:
    return None if ref is None else ReceiptArtifact(sha256=ref.sha256, size=ref.size)


def _role(run) -> ReceiptRoleEvidence:
    return ReceiptRoleEvidence(
        revision=run.revision,
        role=run.role,
        result=run.result,
        invariant_held=run.invariant_held,
        exception_type=run.exception_type,
        exit_code=run.exit_code,
        junit_tests=run.junit_tests,
        covered_target=run.covered_target,
        covered_lines=run.covered_lines,
        cleanup_confirmed=run.cleanup_confirmed,
        output=_artifact(run.output),
        junit=_artifact(run.junit),
        coverage=_artifact(run.coverage),
    )


def _disposition_matches(case: DatasetCase, disposition) -> bool:
    expected = getattr(case.expected, disposition.revision)
    if disposition.label == expected.label and disposition.reason_code == expected.reason_code:
        return True
    return any(variation.revision == disposition.revision and variation.label == disposition.label
               and variation.reason_code == disposition.reason_code for variation in case.allowed_variations)


def _replay_outcome(case: DatasetCase, evaluation: Evaluation, backend: Sandboxes,
                    run_id: str) -> tuple[Literal["complete", "failed", "infrastructure"], str | None, bool]:
    leftovers = backend.labelled(run_id)
    cleanup = not leftovers and all(run.cleanup_confirmed is True for run in evaluation.runs)
    if evaluation.gate.stage is Gate.INFRA:
        return "infrastructure", "KERNEL_INFRASTRUCTURE", cleanup
    if leftovers or any(run.cleanup_confirmed is not True for run in evaluation.runs):
        return "infrastructure", "CLEANUP_UNCONFIRMED", False
    verdict = evaluation.verdict
    if evaluation.gate.stage is not Gate.VERIFIED or verdict is None:
        return "failed", f"KERNEL_{evaluation.gate.stage.name}", cleanup
    if (verdict.audit is None or not verdict.audit.valid or verdict.fix != case.expected.fix
            or len(verdict.revisions) != 2 or not all(_disposition_matches(case, item)
                                                       for item in verdict.revisions)):
        return "failed", "EXPECTED_DISPOSITION_MISMATCH", cleanup
    roles = {(run.revision, run.role): run for run in evaluation.runs}
    expected_roles = {("vulnerable", "control"), ("vulnerable", "exploit"),
                      ("fixed", "control"), ("fixed", "exploit")}
    if set(roles) != expected_roles or len(evaluation.runs) != 4:
        return "failed", "ROLE_EVIDENCE_INCOMPLETE", cleanup
    for (revision, role), run in roles.items():
        if (run.junit_tests != 1 or run.exception_type is not None or run.covered_target is not True
                or run.covered_lines != case.target.lines or run.cleanup_confirmed is not True):
            return "failed", "ROLE_EVIDENCE_INVALID", cleanup
        expected_held = role == "control" or revision == "fixed"
        expected_result = RoleResult.PASS if role == "control" or revision == "vulnerable" else RoleResult.FAIL
        if run.invariant_held is not expected_held or run.result is not expected_result:
            return "failed", "ROLE_POLARITY_INVALID", cleanup
    return "complete", None, True


def _record_from_evaluation(*, dataset_case: DatasetCase, dataset_version: str, manifest_sha256: str,
                            case_revision: str, qualification_run_id: str, attempt: int,
                            runtime_row: matrix.Row, runtime_image_id: str, executor_digest: str,
                            started_at: datetime, finished_at: datetime, evaluation: Evaluation,
                            backend: Sandboxes, run_id: str) -> ReplayRecord:
    outcome, failure_code, cleanup = _replay_outcome(dataset_case, evaluation, backend, run_id)
    verdict = evaluation.verdict
    dispositions = tuple(ReceiptDisposition(revision=item.revision, label=item.label, rule=item.rule,
                                             reason_code=item.reason_code)
                         for item in (verdict.revisions if verdict else ()))
    by_revision = {item.revision: item.label for item in dispositions}
    return ReplayRecord(
        schema="corsair-lite/qualification-replay/1",
        qualification_run_id=qualification_run_id,
        attempt=attempt,
        case_id=dataset_case.case_id,
        family_id=dataset_case.family_id,
        dataset_version=dataset_version,
        manifest_sha256=manifest_sha256,
        case_revision_sha256=case_revision,
        input_sha256=dataset_case.artifacts.input_sha256,
        oracle_sha256=dataset_case.artifacts.oracle_sha256,
        reference_submission_sha256=dataset_case.artifacts.reference_submission_sha256,
        vulnerable_tree_sha256=dataset_case.source_pair.vulnerable.tree_sha256,
        fixed_tree_sha256=dataset_case.source_pair.fixed.tree_sha256,
        runtime_row=runtime_row.id,
        runtime_row_sha256=runtime_row_sha256(runtime_row),
        runtime_image_id=runtime_image_id,
        executor_sha256=executor_digest,
        started_at=started_at,
        finished_at=finished_at,
        gate=evaluation.gate.stage,
        source_label=by_revision.get("vulnerable"),
        fixed_label=by_revision.get("fixed"),
        fix=verdict.fix if verdict else None,
        dispositions=dispositions,
        roles=tuple(_role(run) for run in evaluation.runs),
        cleanup_confirmed=cleanup,
        outcome=outcome,
        failure_code=failure_code,
        audit_mode="trusted_reference",
    )


def _infrastructure_record(*, dataset_case: DatasetCase, dataset_version: str, manifest_sha256: str,
                           case_revision: str, qualification_run_id: str, attempt: int,
                           runtime_row: matrix.Row, runtime_image_id: str | None, executor_digest: str,
                           started_at: datetime, finished_at: datetime, failure_code: str) -> ReplayRecord:
    return ReplayRecord(
        schema="corsair-lite/qualification-replay/1",
        qualification_run_id=qualification_run_id,
        attempt=attempt,
        case_id=dataset_case.case_id,
        family_id=dataset_case.family_id,
        dataset_version=dataset_version,
        manifest_sha256=manifest_sha256,
        case_revision_sha256=case_revision,
        input_sha256=dataset_case.artifacts.input_sha256,
        oracle_sha256=dataset_case.artifacts.oracle_sha256,
        reference_submission_sha256=dataset_case.artifacts.reference_submission_sha256,
        vulnerable_tree_sha256=dataset_case.source_pair.vulnerable.tree_sha256,
        fixed_tree_sha256=dataset_case.source_pair.fixed.tree_sha256,
        runtime_row=runtime_row.id,
        runtime_row_sha256=runtime_row_sha256(runtime_row),
        runtime_image_id=runtime_image_id,
        executor_sha256=executor_digest,
        started_at=started_at,
        finished_at=finished_at,
        gate=Gate.INFRA,
        source_label=None,
        fixed_label=None,
        fix=None,
        dispositions=(),
        roles=(),
        cleanup_confirmed=False,
        outcome="infrastructure",
        failure_code=failure_code,
        audit_mode="trusted_reference",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_review(dataset: Path, case: DatasetCase) -> TechnicalReviewRecord | None:
    pointer = case.review_receipt
    if pointer is None:
        return None
    path = dataset / pointer.path
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to((dataset / "receipts").resolve(strict=True)) or not path.is_file() or path.is_symlink():
        raise ValueError(f"unsafe review receipt for {case.case_id}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer.sha256:
        raise ValueError(f"review receipt hash differs for {case.case_id}")
    review = TechnicalReviewRecord.model_validate_json(raw)
    if review.reviewer != pointer.reviewer or review.reviewed_at != pointer.reviewed_at:
        raise ValueError(f"review receipt pointer differs for {case.case_id}")
    return review


def _declared_receipt_path(dataset: Path, relative: str) -> Path:
    receipts = (dataset / "receipts").resolve(strict=True)
    path = dataset / relative
    resolved = path.resolve(strict=True)
    info = path.lstat()
    if (path.is_symlink() or not path.is_file() or info.st_nlink != 1 or not resolved.is_relative_to(receipts)
            or any((dataset.joinpath(*Path(relative).parts[:index])).is_symlink()
                   for index in range(1, len(Path(relative).parts) + 1))):
        raise ValueError("receipt path is not a regular file below the receipts root")
    return path


def admission_from_manifest(dataset: Path, manifest: DatasetManifest,
                            case: DatasetCase) -> AdmissionStatus:
    """Load and verify the immutable pointers attached to one qualified manifest entry."""
    if len(case.replay_receipts) != 3:
        return AdmissionStatus(ready=False, code="REPLAY_TRIO_REQUIRED")
    try:
        replays: list[ReplayRecord] = []
        revision = case_revision_sha256(case)
        for pointer in case.replay_receipts:
            path = _declared_receipt_path(dataset, pointer.path)
            if path.parent.name != revision:
                return AdmissionStatus(ready=False, code="REPLAY_REVISION_DIRECTORY_MISMATCH")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != pointer.sha256:
                return AdmissionStatus(ready=False, code="REPLAY_POINTER_HASH_MISMATCH")
            record = ReplayRecord.model_validate_json(raw)
            if record.attempt != pointer.attempt:
                return AdmissionStatus(ready=False, code="REPLAY_POINTER_ATTEMPT_MISMATCH")
            replays.append(record)
        selected_run = replays[0].qualification_run_id
        ledger: list[ReplayRecord] = []
        revision_directory = (dataset / "receipts" / revision).resolve(strict=True)
        for candidate in sorted(path for path in revision_directory.iterdir() if path.name.endswith(".json")):
            if candidate.is_symlink() or not candidate.is_file() or candidate.lstat().st_nlink != 1:
                return AdmissionStatus(ready=False, code="REPLAY_RUN_LEDGER_INVALID")
            try:
                ledger_record = ReplayRecord.model_validate_json(candidate.read_bytes())
            except ValueError:
                return AdmissionStatus(ready=False, code="REPLAY_RUN_LEDGER_INVALID")
            if (ledger_record.case_id != case.case_id
                    or ledger_record.case_revision_sha256 != revision):
                return AdmissionStatus(ready=False, code="REPLAY_RUN_LEDGER_INVALID")
            if ledger_record.case_id == case.case_id and ledger_record.qualification_run_id == selected_run:
                ledger.append(ledger_record)
        if (len(ledger) != 3 or sorted(record.attempt for record in ledger) != [1, 2, 3]
                or any(record.outcome != "complete" for record in ledger)):
            return AdmissionStatus(ready=False, code="REPLAY_RUN_LEDGER_INVALID")

        review = None
        if case.review_receipt is not None:
            pointer = case.review_receipt
            review_path = _declared_receipt_path(dataset, pointer.path)
            raw = review_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != pointer.sha256:
                return AdmissionStatus(ready=False, code="REVIEW_POINTER_HASH_MISMATCH")
            review = TechnicalReviewRecord.model_validate_json(raw)
            if review.reviewer != pointer.reviewer or review.reviewed_at != pointer.reviewed_at:
                return AdmissionStatus(ready=False, code="REVIEW_POINTER_METADATA_MISMATCH")

        row = next((candidate for candidate in matrix.load() if candidate.id == case.runtime), None)
        if row is None or row.language != case.language:
            return AdmissionStatus(ready=False, code="RUNTIME_ROW_UNAVAILABLE")
        family = tuple(member for member in manifest.cases if member.family_id == case.family_id)
        return admission_status(case, tuple(replays), review, family_cases=family,
                                runtime_row_sha256=runtime_row_sha256(row),
                                executor_sha256=executor_sha256())
    except (OSError, RuntimeError, ValueError):
        return AdmissionStatus(ready=False, code="RECEIPT_INVALID")


def _preflight_case(root: Path, dataset: Path, dataset_case: DatasetCase) -> tuple[Case, Submission, matrix.Row]:
    case_dir = root / "cases" / dataset_case.case_id
    artifact_paths = {
        "input_sha256": case_dir / "input.json",
        "oracle_sha256": case_dir / "oracle.json",
        "reference_submission_sha256": case_dir / "reference-submission.json",
    }
    for field, path in artifact_paths.items():
        if not path.is_file() or path.is_symlink() or not path.resolve(strict=True).is_relative_to(case_dir.resolve()):
            raise ValueError(f"missing or unsafe {path.name} for {dataset_case.case_id}")
        if _sha256_file(path) != getattr(dataset_case.artifacts, field):
            raise ValueError(f"{path.name} hash differs for {dataset_case.case_id}")
    case = load_case(case_dir)
    if case.case_id != dataset_case.case_id or case.fixed_revision is None:
        raise ValueError(f"case identity or fixed revision differs for {dataset_case.case_id}")
    if (tree_sha256(Path(case.revision.source)) != dataset_case.source_pair.vulnerable.tree_sha256
            or tree_sha256(Path(case.fixed_revision.source)) != dataset_case.source_pair.fixed.tree_sha256):
        raise ValueError(f"source tree hash differs for {dataset_case.case_id}")
    submission = Submission.model_validate_json(artifact_paths["reference_submission_sha256"].read_bytes())
    hypothesis = submission.hypothesis
    if (hypothesis.target_file != dataset_case.target.file or hypothesis.target_symbol != dataset_case.target.symbol
            or hypothesis.target_lines != dataset_case.target.lines):
        raise ValueError(f"reference target differs for {dataset_case.case_id}")
    row = matrix.select(case)
    if row is None or row.id != dataset_case.runtime or row.language != dataset_case.language:
        raise ValueError(f"runtime row differs or is unsupported for {dataset_case.case_id}")
    return case, submission, row


async def verify_references(*, root: Path, manifest_path: Path, eval_set: EvalSet, attempts: int,
                            runs_root: Path, receipts_root: Path,
                            backend_factory: Callable[[], Sandboxes] = sandboxes,
                            now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                            id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
                            corpus_validator: Callable[[Path], CorpusReport] = validate_corpus) -> QualificationReport:
    """Replay checked-in references without a model and publish one immutable receipt per fresh attempt."""
    if attempts < 1:
        raise ValueError("attempts must be at least one")
    root = Path(root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    expected_dataset = (root / "benchmarks/dataset").resolve(strict=True)
    if manifest_path.parent != expected_dataset or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("manifest must be a regular file directly below benchmarks/dataset")
    receipts_root = _safe_existing_directory(receipts_root)
    expected_receipts = (manifest_path.parent / "receipts").resolve(strict=True)
    if receipts_root != expected_receipts:
        raise ValueError("receipts root must be exactly benchmarks/dataset/receipts")
    corpus_report = (validate_corpus(root, manifest_path=manifest_path)
                     if corpus_validator is validate_corpus else corpus_validator(root))
    if not corpus_report.ok:
        codes = ", ".join(sorted({issue.code for issue in corpus_report.errors}))
        raise ValueError(f"corpus validation failed: {codes}")
    manifest_raw = manifest_path.read_bytes()
    manifest = load_manifest(manifest_path)
    selected = select_qualification_cases(manifest, eval_set)
    if not selected:
        raise ValueError(f"evaluation set {eval_set} selects no candidate or qualified cases")
    qualification_run_id = id_factory()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", qualification_run_id):
        raise ValueError("qualification run id is unsafe")
    manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
    executor_digest = executor_sha256()
    prepared = [(dataset_case, *_preflight_case(root, manifest_path.parent, dataset_case))
                for dataset_case in selected]
    family_members = {case.family_id: tuple(member for member in manifest.cases
                                             if member.family_id == case.family_id)
                      for case in selected}
    reports: list[QualificationCaseReport] = []
    for dataset_case, case, submission, row in prepared:
        revision = case_revision_sha256(dataset_case)
        attempts_report: list[QualificationAttempt] = []
        records: list[ReplayRecord] = []
        for attempt in range(1, attempts + 1):
            run_id = f"{qualification_run_id}-{dataset_case.case_id}-{attempt}"
            started_at = now()
            backend = backend_factory()
            kernel = Kernel(backend, row, case, artifacts=ArtifactStore(Path(runs_root) / run_id / "artifacts"),
                            auditor=_trusted_reference_audit, run_id=run_id)
            if kernel.runtime_image_id is None or not re.fullmatch(_IMAGE_ID, kernel.runtime_image_id):
                record = _infrastructure_record(
                    dataset_case=dataset_case, dataset_version=manifest.dataset_version,
                    manifest_sha256=manifest_digest, case_revision=revision,
                    qualification_run_id=qualification_run_id, attempt=attempt, runtime_row=row,
                    runtime_image_id=None, executor_digest=executor_digest,
                    started_at=started_at, finished_at=now(), failure_code="RUNTIME_IMAGE_UNRESOLVED",
                )
            elif kernel.runtime_image_id != dataset_case.runtime_image_id:
                record = _infrastructure_record(
                    dataset_case=dataset_case, dataset_version=manifest.dataset_version,
                    manifest_sha256=manifest_digest, case_revision=revision,
                    qualification_run_id=qualification_run_id, attempt=attempt, runtime_row=row,
                    runtime_image_id=kernel.runtime_image_id, executor_digest=executor_digest,
                    started_at=started_at, finished_at=now(), failure_code="RUNTIME_IMAGE_MISMATCH",
                )
            else:
                evaluation = await kernel.evaluate(submission)
                record = _record_from_evaluation(
                    dataset_case=dataset_case, dataset_version=manifest.dataset_version,
                    manifest_sha256=manifest_digest, case_revision=revision,
                    qualification_run_id=qualification_run_id, attempt=attempt, runtime_row=row,
                    runtime_image_id=kernel.runtime_image_id, executor_digest=executor_digest,
                    started_at=started_at, finished_at=now(), evaluation=evaluation, backend=backend, run_id=run_id,
                )
            filename = f"replay-{qualification_run_id}-{attempt}.json"
            published = publish_receipt(receipts_root, revision, filename, record)
            relative = published.relative_to(root).as_posix()
            attempts_report.append(QualificationAttempt(
                attempt=attempt, outcome=record.outcome, failure_code=record.failure_code,
                path=relative, sha256=_sha256_file(published)))
            records.append(record)
            if record.failure_code in {"CLEANUP_UNCONFIRMED", "RUNTIME_IMAGE_UNRESOLVED",
                                       "RUNTIME_IMAGE_MISMATCH"}:
                break
        review = _load_review(manifest_path.parent, dataset_case)
        status = admission_status(dataset_case, tuple(records), review,
                                  family_cases=family_members[dataset_case.family_id],
                                  runtime_row_sha256=runtime_row_sha256(row),
                                  executor_sha256=executor_digest)
        reports.append(QualificationCaseReport(
            case_id=dataset_case.case_id, family_id=dataset_case.family_id,
            case_revision_sha256=revision, attempts=tuple(attempts_report),
            admission_ready=status.ready, admission_code=status.code))
    return QualificationReport(dataset_version=manifest.dataset_version, eval_set=eval_set,
                               qualification_run_id=qualification_run_id, cases=tuple(reports))
