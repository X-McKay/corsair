"""Tracked review records of reviewed intake, and the audit that reads them back.

``dataset freeze`` writes one ``corsair.dataset-review/1`` record per freeze under
``<reviews>/<manifest stem>/`` (default ``reviews/`` beside the manifest, so
``evals/datasets/reviews/`` for the tiers): the review sheet itself stays in the private draft
directory, but who decided which row, and which oracle was frozen, is kept in the repository.
``audit_manifests`` (``dataset audit``) lists every manifest row with its latest record and
flags rows with none and rows a stand-in reviewer marked ``pending owner audit``. Records are
data: reading one never changes a manifest, and the audit never fails a run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from corsair.contracts import Dataset, DatasetReview, DatasetReviewEntry, digest
from corsair.observability.logging import safe_error_detail

REVIEWS_DIRECTORY = "reviews"
# A stand-in reviewer marks decisions the owner has still to audit with this text.
PENDING_OWNER_AUDIT = "pending owner audit"
UNREVIEWED = "unreviewed"
PENDING = "pending_owner_audit"
REVIEWED = "reviewed"
# The manifest's oracle is not the one the latest record froze (a later refreeze or edit).
ORACLE_CHANGED = "oracle_changed"
# The latest record rejected a row the manifest holds.
REJECTED_BUT_FROZEN = "rejected_but_frozen"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}")


def default_reviews_directory(manifest: Path) -> Path:
    """``reviews/`` beside the manifest: ``evals/datasets/reviews`` for the evals tree."""
    return manifest.parent / REVIEWS_DIRECTORY


def repository_path(path: Path, manifest: Path) -> str:
    """``path`` relative to the repository holding an ``evals/datasets`` manifest (or to the
    manifest's own directory otherwise), absolute when it lies outside."""
    parent = manifest.resolve().parent
    root = parent.parent.parent if parent.name == "datasets" else parent
    resolved = path.resolve()
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else str(path)


def record_name(draft_id: str, split: str, directory: Path, now: datetime) -> Path:
    """``<draft id>-<split>.json`` below ``directory``; a timestamp keeps an earlier record."""
    split = split if _NAME.fullmatch(split) else "split"
    target = directory / f"{draft_id}-{split}.json"
    if target.exists():
        target = directory / f"{draft_id}-{now.strftime('%Y%m%dt%H%M%S%f')}-{split}.json"
    return target


def draft_identity(draft_dir: Path, now: datetime) -> str:
    """The draft directory's name when it is a plain name, else the freeze timestamp."""
    name = draft_dir.resolve().name
    return name if _NAME.fullmatch(name) else now.strftime("draft-%Y%m%dt%H%M%S")


def write_review(record: DatasetReview, *, manifest: Path, reviews: Path, now: datetime) -> Path:
    """Write ``record`` under ``<reviews>/<manifest stem>/`` and return its path."""
    directory = reviews / manifest.stem
    directory.mkdir(parents=True, exist_ok=True)
    target = record_name(record.draft_id, record.split, directory, now)
    payload = record.model_dump(mode="json", exclude_none=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(target)
    return target


def _sort_key(item: tuple[Path, DatasetReview]) -> tuple[datetime, str]:
    path, record = item
    when = record.recorded_at or datetime.min.replace(tzinfo=UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when, path.name


def _records(directory: Path, problems: list[str]) -> list[tuple[Path, DatasetReview]]:
    """Every readable record below ``directory``, oldest first; unreadable ones are problems."""
    records = []
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in paths:
        try:
            records.append((path, DatasetReview.model_validate_json(path.read_bytes())))
        except (OSError, ValueError) as error:
            problems.append(f"{path.name}: unreadable review record: {safe_error_detail(error)}")
    return sorted(records, key=_sort_key)


def _row_flags(entry: DatasetReviewEntry | None, oracle_digest: str) -> list[str]:
    if entry is None:
        return [UNREVIEWED]
    flags = []
    if PENDING_OWNER_AUDIT in (entry.reviewer or "").lower():
        flags.append(PENDING)
    if entry.frozen_oracle_digest is None:
        flags.append(REJECTED_BUT_FROZEN)
    elif entry.frozen_oracle_digest != oracle_digest:
        flags.append(ORACLE_CHANGED)
    return flags


def audit_manifest(manifest: Path, reviews: Path | None = None) -> dict[str, Any]:
    """One manifest's rows, each with its latest review record and its flags."""
    directory = (reviews or default_reviews_directory(manifest)) / manifest.stem
    problems: list[str] = []
    records = _records(directory, problems)
    latest: dict[str, tuple[Path, DatasetReview, DatasetReviewEntry]] = {}
    for path, record in records:
        for entry in record.entries:
            latest[entry.case_id] = path, record, entry
    try:
        dataset = Dataset.model_validate_json(manifest.read_bytes())
    except (OSError, ValueError) as error:
        problems.append(f"manifest unreadable: {safe_error_detail(error)}")
        dataset = None
    rows = []
    for item in [] if dataset is None else dataset.entries:
        found = latest.get(item.case_id)
        entry = None if found is None else found[2]
        flags = _row_flags(entry, item.oracle_digest)
        row: dict[str, Any] = {
            "case_id": item.case_id,
            "family": item.family,
            "split": item.split,
            "status": PENDING if PENDING in flags else flags[0] if flags else REVIEWED,
            "flags": flags,
            "decision": None,
            "reviewer": None,
            "record": None,
            "recorded_at": None,
            "reconstructed": None,
        }
        if found is not None and entry is not None:
            path, record, _ = found
            row |= {
                "decision": entry.decision.value,
                "reviewer": entry.reviewer,
                "record": repository_path(path, manifest),
                "recorded_at": None
                if record.recorded_at is None
                else record.recorded_at.isoformat(),
                "reconstructed": record.reconstructed,
            }
        rows.append(row)
    return {
        "manifest": str(manifest),
        "dataset_digest": None if dataset is None else digest(dataset),
        "reviews": repository_path(directory, manifest),
        "records": len(records),
        "problems": problems,
        "rows": rows,
    }


def audit_manifests(manifests: Sequence[Path], reviews: Path | None = None) -> dict[str, Any]:
    """The review audit of every manifest: rows, their latest records and the flag counts."""
    audited = [audit_manifest(manifest, reviews) for manifest in manifests]
    rows = [row for item in audited for row in item["rows"]]
    flags = (UNREVIEWED, PENDING, ORACLE_CHANGED, REJECTED_BUT_FROZEN)
    return {
        "dataset_audit": {
            "manifests": [str(path) for path in manifests],
            "reviews": None if reviews is None else str(reviews),
        },
        "manifests": audited,
        "counts": {
            "rows": len(rows),
            REVIEWED: sum(row["status"] == REVIEWED for row in rows),
            **{flag: sum(flag in row["flags"] for row in rows) for flag in flags},
            "problems": sum(len(item["problems"]) for item in audited),
        },
    }
