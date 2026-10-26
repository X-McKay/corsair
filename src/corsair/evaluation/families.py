"""Evaluator-side family membership: split disjointness and per-family report views.

A family is one vulnerability class in one target (both variants of a chain pair, and any
adversarial row built on them). The baseline policy promotes only on family-grouped
held-out data, so a family must sit in exactly one split across every dataset manifest,
and a chain pair (request directories ``<class>-a`` and ``<class>-b`` under one parent)
must keep one split and one family. The check reads manifests only: frozen request and
oracle bytes are verified by :func:`corsair.evaluation.datasets.load_dataset`, and no oracle
content is read here. The report views group already-scored rows; they never re-score.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from corsair.contracts import Dataset, digest
from corsair.evaluation.intake import INTAKE_SCHEMA, IntakeDataset
from corsair.evaluation.scoring import summarize

_PAIR_DIRECTORY = re.compile(r"^(?P<stem>.+)-(?P<variant>[ab])$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECISIVE = frozenset(
    {"EXPLOIT_DEMONSTRATED", "COMPONENT_EXPLOIT_DEMONSTRATED", "EXPLOIT_NOT_DEMONSTRATED"}
)
_GROUP_FIELDS = (
    "attempts",
    "passed",
    "failed",
    "pass_rate",
    "correctly_resolved",
    "forbidden_labels",
    "inconclusive",
    "operational_failures",
    "unavailable_results",
)


@dataclass(frozen=True)
class Member:
    """One manifest entry's membership; ``family``/``split`` are None when undeclared."""

    source: str
    case_id: str
    family: str | None
    split: str | None
    pair: str | None


def chain_pair(path: str) -> str | None:
    """``chain/python/cmdi-a/request.json`` belongs to pair ``chain/python/cmdi``."""
    parent = PurePosixPath(path).parent
    match = _PAIR_DIRECTORY.match(parent.name)
    return str(parent.parent / match["stem"]) if match else None


def dataset_members(path: Path) -> list[Member]:
    """Read one manifest's membership without reading its frozen requests or oracles.

    ``corsair.dataset/1`` entries declare family and split. ``corsair.agent-dataset/1``
    entries declare neither and are returned unlabelled. A flat object mapping family ids
    to SHA-256 digests is the legacy held-out listing: each key is a family whose split is
    the file stem."""
    raw = json.loads(path.read_bytes())
    source = path.name
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: dataset manifest must be a JSON object")
    schema = raw.get("schema_version")
    if schema == "corsair.dataset/1":
        return [
            Member(source, entry.case_id, entry.family, entry.split, chain_pair(entry.request))
            for entry in Dataset.model_validate(raw).entries
        ]
    if schema == "corsair.agent-dataset/1":
        entries = raw.get("entries")
        if not isinstance(entries, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("case_id"), str)
            and isinstance(item.get("input"), str)
            for item in entries
        ):
            raise ValueError(f"{source}: agent dataset entries need a case_id and an input")
        return [
            Member(source, item["case_id"], None, None, chain_pair(item["input"]))
            for item in entries
        ]
    if schema == INTAKE_SCHEMA:
        # Intake rows score scan-report findings; they carry no family or split.
        return [
            Member(source, entry.case_id, None, None, None)
            for entry in IntakeDataset.model_validate(raw).entries
        ]
    if raw and all(isinstance(value, str) and _SHA256.match(value) for value in raw.values()):
        return [Member(source, family, family, path.stem, None) for family in sorted(raw)]
    raise ValueError(f"{source}: unsupported dataset manifest (schema_version={schema!r})")


def _crossing(
    rule: str, field: str, groups: dict[str, list[Member]], by: str
) -> list[dict[str, Any]]:
    """One violation per group whose labelled members disagree on ``by``."""
    found = []
    for key, members in sorted(groups.items()):
        values: dict[str, list[str]] = defaultdict(list)
        for member in members:
            values[str(getattr(member, by))].append(f"{member.source}:{member.case_id}")
        if len(values) > 1:
            found.append({"rule": rule, field: key, f"{by}s": dict(sorted(values.items()))})
    return found


def split_violations(members: Iterable[Member]) -> list[dict[str, Any]]:
    """Families, cases and chain pairs that cross splits, and pairs that cross families.

    Only members that declare a split are checked; unlabelled entries carry no split
    claim to contradict."""
    families: dict[str, list[Member]] = defaultdict(list)
    cases: dict[str, list[Member]] = defaultdict(list)
    pairs: dict[str, list[Member]] = defaultdict(list)
    for member in members:
        if member.split is None:
            continue
        if member.family is not None:
            families[member.family].append(member)
        cases[member.case_id].append(member)
        if member.pair is not None:
            pairs[member.pair].append(member)
    return [
        *_crossing("family_crosses_splits", "family", families, "split"),
        *_crossing("case_crosses_splits", "case_id", cases, "split"),
        *_crossing("pair_crosses_splits", "pair", pairs, "split"),
        *_crossing("pair_crosses_families", "pair", pairs, "family"),
    ]


def check_family_splits(paths: Iterable[Path]) -> dict[str, Any]:
    """Check every family, case and chain pair keeps one split across these manifests."""
    datasets, members = [], []
    for path in paths:
        found = dataset_members(path)
        members.extend(found)
        datasets.append(
            {
                "path": str(path),
                "entries": len(found),
                "unlabelled": sum(member.split is None for member in found),
                "splits": sorted({member.split for member in found if member.split}),
                "families": sorted({member.family for member in found if member.family}),
            }
        )
    violations = split_violations(members)
    return {
        "ok": not violations,
        "families": len({member.family for member in members if member.split and member.family}),
        "unlabelled_entries": sum(member.split is None for member in members),
        "datasets": datasets,
        "violations": violations,
    }


def label_rows(rows: list[dict[str, Any]], dataset: Dataset) -> list[dict[str, Any]]:
    """Add each row's declared ``family`` and ``split``; rows without a known case are kept."""
    membership = {entry.case_id: entry for entry in dataset.entries}
    labelled = []
    for row in rows:
        case_id = row.get("case_id")
        entry = membership.get(case_id) if isinstance(case_id, str) else None
        labelled.append(
            row if entry is None else {**row, "family": entry.family, "split": entry.split}
        )
    return labelled


def label_report(report: dict[str, Any], path: Path) -> dict[str, Any]:
    """Label an older report's rows from the exact manifest it was scored against."""
    dataset = Dataset.model_validate_json(path.read_bytes())
    declared = report.get("dataset_digest")
    if declared != digest(dataset):
        raise ValueError(
            f"{path.name} digest {digest(dataset)} differs from the report's dataset digest "
            f"{declared}; pass the manifest the report was scored against"
        )
    return {**report, "rows": label_rows(report.get("rows", []), dataset)}


def _group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize(rows)
    scored = [row for row in rows if "verdict" in row]
    decisive = sum(row.get("verdict") in _DECISIVE for row in scored) if scored else None
    return {
        "cases": len({row["case_id"] for row in rows if isinstance(row.get("case_id"), str)}),
        **{field: summary[field] for field in _GROUP_FIELDS},
        "decisive": decisive,
        "decisive_rate": decisive / len(rows) if decisive is not None and rows else None,
    }


def _declared(row: dict[str, Any], field: str) -> str | None:
    value = row.get(field)
    return value if isinstance(value, str) else None


def _ordered(groups: dict[str | None, list[dict[str, Any]]]) -> list[str | None]:
    """Named groups alphabetically, then the undeclared group."""
    return sorted(groups, key=lambda key: (key is None, key or ""))


def _grouped(rows: list[dict[str, Any]], field: str) -> dict[str | None, list[dict[str, Any]]]:
    groups: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_declared(row, field)].append(row)
    return groups


def family_view(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Per-family and per-split summaries; rows without a family group under ``None``."""
    by_family, by_split = _grouped(rows, "family"), _grouped(rows, "split")
    families = []
    for family in _ordered(by_family):
        members = by_family[family]
        splits = sorted({split for row in members if (split := _declared(row, "split"))})
        families.append({"family": family, "splits": splits, **_group(members)})
    splits = []
    for split in _ordered(by_split):
        members = by_split[split]
        named = {family for row in members if (family := _declared(row, "family"))}
        splits.append({"split": split, "families": len(named), **_group(members)})
    return {"families": families, "splits": splits}


def _change(before: dict[str, Any] | None, after: dict[str, Any] | None, field: str) -> Any:
    old = None if before is None else before.get(field)
    new = None if after is None else after.get(field)
    if isinstance(old, bool) or isinstance(new, bool):
        return None
    if isinstance(old, int | float) and isinstance(new, int | float):
        return new - old
    return None


def family_deltas(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Each family's baseline/candidate summary, key deltas and attributed regressions."""
    before = {item["family"]: item for item in family_view(baseline)["families"]}
    after = {item["family"]: item for item in family_view(candidate)["families"]}
    attributed: dict[str | None, int] = defaultdict(int)
    for item in regressions:
        attributed[item.get("family")] += 1
    keys = sorted(before.keys() | after.keys(), key=lambda key: (key is None, key or ""))
    return [
        {
            "family": family,
            "baseline": before.get(family),
            "candidate": after.get(family),
            "pass_rate_delta": _change(before.get(family), after.get(family), "pass_rate"),
            "decisive_delta": _change(before.get(family), after.get(family), "decisive"),
            "forbidden_labels_delta": _change(
                before.get(family), after.get(family), "forbidden_labels"
            ),
            "regressions": attributed[family],
        }
        for family in keys
    ]


def main() -> None:
    """Print the split check as JSON; exit 1 on a violation and 2 on an unreadable manifest."""
    parser = argparse.ArgumentParser(description=check_family_splits.__doc__)
    parser.add_argument(
        "datasets", nargs="*", type=Path, help="Manifests; default evals/datasets/*.json"
    )
    args = parser.parse_args()
    paths = args.datasets or sorted(Path("evals/datasets").glob("*.json"))
    try:
        result = check_family_splits(paths)
    except (OSError, ValueError) as error:
        print(f"dataset family check failed: {error}", file=sys.stderr)
        print(
            "Remedy: pass corsair.dataset/1 or agent manifests from evals/datasets/",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
