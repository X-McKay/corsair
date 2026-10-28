"""Evaluator-side family membership: split disjointness and per-family report views.

A family is one vulnerability class in one target (both variants of a chain pair, and any
adversarial row built on them). The baseline policy promotes only on family-grouped
held-out data, so across every manifest checked together a family id, its family stem
(language and class, :func:`family_stem`), a case, a chain pair (:func:`variant_stem`) and
a source tree must each keep one split, and a chain pair must keep one family id. The
check reads manifests and each labelled entry's digest-verified request (for its recipe
kind and source trees); it never reads an oracle. The report views group already-scored
rows; they never re-score.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from corsair.contracts import Dataset, DatasetEntry, InvestigationRequest, digest
from corsair.evaluation.datasets import dataset_root, read_frozen
from corsair.evaluation.intake import INTAKE_SCHEMA, IntakeDataset
from corsair.evaluation.scoring import summarize
from corsair.observability.logging import safe_error_detail

_VARIANT_DIRECTORY = re.compile(r"^(?:(?P<stem>.+)-)?[ab](?:-v\d+)?$")
_LAYOUT_DIRECTORY = re.compile(r"^v\d+$")
# Family ids written ``ih-<language>-<class>``, ``sbj-<language>-<class>`` or
# ``chain-<language>-<class>`` always name the language; an unprefixed id names one only
# through a known language token.
_LANGUAGE_PREFIXES = frozenset({"ih", "sbj", "chain"})
_LANGUAGES = {
    "c": "c",
    "java": "java",
    "javascript": "javascript",
    "js": "javascript",
    "perl": "perl",
    "py": "python",
    "python": "python",
    "rb": "ruby",
    "ruby": "ruby",
}
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
    """One manifest entry's membership; ``family``/``split`` are None when undeclared.

    ``trees`` maps each source-tree key (an absolute resolved path or a content digest) to
    its display text; ``problem`` records why a labelled entry's request was unreadable."""

    source: str
    case_id: str
    family: str | None
    split: str | None
    pair: str | None
    stem: str | None = None
    trees: tuple[tuple[str, str], ...] = ()
    problem: str | None = None


def variant_stem[P: PurePath](directory: P) -> P | None:
    """The pair stem a variant directory belongs to, or None outside a pair.

    This is the one pair-layout rule. Trailing ``v<N>`` layout directories are skipped;
    the remaining directory is a variant when it is named ``<class>-a`` or ``<class>-b``
    (optionally suffixed ``-v<N>``), or is a bare ``a``/``b`` corpus tree::

        chain/python/cmdi-a                      -> chain/python/cmdi
        chain/java/xxe-b/v3                      -> chain/java/xxe
        chain/javascript/prototypepollution-a-v3 -> chain/javascript/prototypepollution
        corpus/infosec-harness/perl/xss/b        -> corpus/infosec-harness/perl/xss
        chain/python/ineffective-fix             -> None
    """
    while _LAYOUT_DIRECTORY.match(directory.name) and directory.parent != directory:
        directory = directory.parent
    match = _VARIANT_DIRECTORY.match(directory.name)
    if match is None:
        return None
    return directory.parent / match["stem"] if match["stem"] else directory.parent


def chain_pair(path: str) -> str | None:
    """The pair of a request file, read from its directory by :func:`variant_stem`.

    ``chain/python/cmdi-a/request.json`` and ``chain/java/xxe-b/v3/request.json`` belong to
    pairs ``chain/python/cmdi`` and ``chain/java/xxe``."""
    stem = variant_stem(PurePosixPath(path).parent)
    return None if stem is None else str(stem)


def kind_language(kind: str) -> str:
    """The language a recipe kind names: ``c.integer_overflow/1`` is ``c``."""
    prefix = kind.split(".", 1)[0]
    return _LANGUAGES.get(prefix, prefix)


def family_stem(family: str, kind: str | None) -> str:
    """A family's language and class, ``<language>/<class>``, so spellings compare equal.

    The language comes from an ``ih-``/``sbj-``/``chain-`` prefix, a leading language token, or else
    the request's recipe kind (``java.secret_disclosure/1`` is java); the class drops
    ``-``/``_`` separators. ``xxe`` under a java kind and ``ih-java-xxe`` are both ``java/xxe``;
    without any language the stem is the class alone."""
    tokens = family.lower().split("-")
    language = None
    if tokens[0] in _LANGUAGE_PREFIXES and len(tokens) > 2:
        language, tokens = _LANGUAGES.get(tokens[1], tokens[1]), tokens[2:]
    elif tokens[0] in _LANGUAGES and len(tokens) > 1:
        language, tokens = _LANGUAGES[tokens[0]], tokens[1:]
    elif kind is not None:
        language = kind_language(kind)
    name = "".join(tokens).replace("_", "")
    return f"{language}/{name}" if language else name


def _tree_display(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _source_trees(
    request: InvestigationRequest, request_path: Path, root: Path
) -> tuple[tuple[str, str], ...]:
    """Key each source tree by its pair stem directory (else the resolved tree, so a symlink
    names its target) and by its declared content digest, so a copied tree still matches."""
    trees: dict[str, str] = {}
    for source in (request.case.source, request.case.fixed_source):
        if source is None:
            continue
        tree = (request_path.parent / source.path).resolve()
        anchor = variant_stem(tree) or variant_stem(tree.parent) or tree
        trees[str(anchor)] = _tree_display(anchor, root)
        if source.expected_digest is not None:
            trees[f"digest:{source.expected_digest}"] = f"digest:{source.expected_digest}"
    return tuple(trees.items())


def request_member(
    source: str,
    entry: DatasetEntry,
    pair: str | None,
    request: InvestigationRequest,
    request_path: Path,
    root: Path,
) -> Member:
    """A labelled entry's membership given its read request: the family stem from the
    request's recipe kind and its source trees (relative paths anchor at ``request_path``,
    displays at ``root``). Frozen entries and ``dataset freeze``'s drafted rows share it."""
    stem = family_stem(entry.family, request.case.recipe.kind)
    trees = _source_trees(request, request_path, root.resolve())
    return Member(source, entry.case_id, entry.family, entry.split, pair, stem, trees)


def _case_member(source: str, root: Path, entry: DatasetEntry) -> Member:
    """A labelled entry's membership, with its family stem and source trees from its request."""
    pair = chain_pair(entry.request)
    try:
        request_path, content = read_frozen(root, entry.request, entry.request_digest, "request")
        request = InvestigationRequest.model_validate_json(content)
    except (OSError, ValueError) as error:
        problem = safe_error_detail(error)
        return Member(source, entry.case_id, entry.family, entry.split, pair, problem=problem)
    return request_member(source, entry, pair, request, request_path, root)


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
        root = dataset_root(path)
        return [_case_member(source, root, entry) for entry in Dataset.model_validate(raw).entries]
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
        return [
            Member(source, family, family, path.stem, None, family_stem(family, None))
            for family in sorted(raw)
        ]
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


def _placements(members: Iterable[Member]) -> dict[str, list[str]]:
    placed: dict[str, set[str]] = defaultdict(set)
    for member in members:
        placed[str(member.split)].add(f"{member.source}:{member.case_id}")
    return {split: sorted(names) for split, names in sorted(placed.items())}


def _stem_crossings(stems: dict[str, list[Member]]) -> list[dict[str, Any]]:
    """Stems that cross splits under more than one family id (one id is the family rule)."""
    found = []
    for stem, members in sorted(stems.items()):
        splits = _placements(members)
        families = sorted({str(member.family) for member in members})
        if len(splits) > 1 and len(families) > 1:
            message = (
                f"family stem {stem} is shared by families {', '.join(families)} "
                f"in splits {', '.join(splits)}"
            )
            found.append(
                {
                    "rule": "family_stem_crosses_splits",
                    "stem": stem,
                    "families": families,
                    "splits": splits,
                    "message": message,
                }
            )
    return found


def _tree_crossings(trees: dict[str, list[Member]], shown: dict[str, str]) -> list[dict[str, Any]]:
    """Source trees shared across splits; keys with the same placement report once."""
    merged: dict[str, dict[str, Any]] = {}
    for key, members in trees.items():
        splits = _placements(members)
        if len(splits) > 1:
            found = merged.setdefault(
                json.dumps(splits, sort_keys=True),
                {"rule": "source_tree_crosses_splits", "trees": [], "splits": splits},
            )
            found["trees"].append(shown[key])
    for found in merged.values():
        # Path keys before content digests, each in name order.
        found["trees"].sort(key=lambda tree: (tree.startswith("digest:"), tree))
    return sorted(merged.values(), key=lambda found: found["trees"])


def split_violations(members: Iterable[Member]) -> list[dict[str, Any]]:
    """Families, family stems, cases, chain pairs and source trees that cross splits, pairs
    that cross families, and labelled entries whose request could not be read.

    Only members that declare a split are checked; unlabelled entries carry no split
    claim to contradict."""
    families: dict[str, list[Member]] = defaultdict(list)
    stems: dict[str, list[Member]] = defaultdict(list)
    cases: dict[str, list[Member]] = defaultdict(list)
    pairs: dict[str, list[Member]] = defaultdict(list)
    trees: dict[str, list[Member]] = defaultdict(list)
    shown: dict[str, str] = {}
    unreadable = []
    for member in members:
        if member.split is None:
            continue
        if member.family is not None:
            families[member.family].append(member)
        if member.stem is not None:
            stems[member.stem].append(member)
        cases[member.case_id].append(member)
        if member.pair is not None:
            pairs[member.pair].append(member)
        for key, display in member.trees:
            trees[key].append(member)
            shown.setdefault(key, display)
        if member.problem is not None:
            unreadable.append(
                {
                    "rule": "request_unreadable",
                    "case_id": member.case_id,
                    "dataset": member.source,
                    "problem": member.problem,
                }
            )
    return [
        *unreadable,
        *_crossing("family_crosses_splits", "family", families, "split"),
        *_stem_crossings(stems),
        *_crossing("case_crosses_splits", "case_id", cases, "split"),
        *_crossing("pair_crosses_splits", "pair", pairs, "split"),
        *_crossing("pair_crosses_families", "pair", pairs, "family"),
        *_tree_crossings(trees, shown),
    ]


def check_family_splits(paths: Iterable[Path]) -> dict[str, Any]:
    """Check every family, family stem, case, chain pair and source tree keeps one split
    across these manifests, checked together as one population."""
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
        "family_stems": len({member.stem for member in members if member.split and member.stem}),
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
