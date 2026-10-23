"""Evaluator-only benchmark inventory.

This module owns corpus truth, provenance, rights and qualification metadata.  Nothing here is part of
``corsair.case.Case`` or an agent payload: callers select a case here, then separately load its small ``input.json``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .case import Frozen, SafePath
from .kernel import Fix, Label

DATASET_SCHEMA = "corsair-lite/dataset-manifest/1"
Sha256 = str
Commit = str
Split = Literal["conformance", "development", "regression", "holdout", "quarantine"]
QualificationStatus = Literal["candidate", "qualified", "quarantined", "retired"]
EvalSet = Literal["conformance", "development", "regression", "release", "holdout"]


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
    notice_requirements: tuple[str, ...] = Field(default=(), max_length=32)
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

