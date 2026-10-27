"""Scanner intake: which findings of a scan report become admissible requests, and why not.

``assess_findings`` is pure. It converts each finding with ``request_from_scanner`` (the
operator's recipe template bound to the finding's file) and runs the trusted line
binding (``bind_target_line``) and pre-model ``target_binding`` check that the prepare
activity runs, over the files of the admitted source snapshot. It reads no finding
narrative, calls no model and runs no target code. ``admit_source`` is its I/O edge: the
real snapshot admission, into a scratch store that is discarded. ``score_dataset``
scores a frozen intake dataset against evaluator-only oracles through the frozen-file loaders
of ``corsair.evaluation.datasets`` (imported as a module object: dataset validation imports this
module back); ``main`` runs it for ``just eval-intake``.

Reviewed case intake turns un-manifested chain directories into frozen composed cases in two
steps with a human between them. ``draft_dataset`` (``corsair dataset draft``) assembles each
directory's request from its ``case.json``/``input.json`` and the operator's recipe template,
proposes an oracle from mechanical facts only, and writes a ``corsair.dataset-draft/1`` file
that no dataset loader accepts plus a code-owned review sheet. ``freeze_dataset`` (``corsair
dataset freeze``) writes only the rows the reviewer accepted or amended into a
``corsair.dataset/1`` manifest, refusing incomplete reviews, invalid rows, rows whose family or
source tree sits in another split, and manifests over 64 entries.

Material staged under a private tree (fetched datasets, agent-built chain inputs) is drafted
with an explicit staging root (``draft --source-root``) and admitted in place below it; the
draft marks itself ``staged`` and its sheet names each tree and its licence files. Only
``freeze --import-into``, after the reviewer's decisions, copies the accepted and amended
rows' trees into the corpus, so no frozen request ever points into the staging root.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from corsair.adapters.scm.local import iter_snapshot_files, snapshot_source
from corsair.adapters.scm.requests import (
    CALLABLE_FIELDS,
    load_recipe_template,
    normalize_request_sources,
    request_from_scanner,
    request_from_template,
)
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    PYTHON_CALLABLE_RECIPES,
    Budget,
    Contract,
    Dataset,
    DatasetEntry,
    Digest,
    Disposition,
    ExecutionStatus,
    Finding,
    FixStatus,
    Identifier,
    InvestigationRequest,
    LineProvenance,
    Oracle,
    ScannerFinding,
    ScanReport,
    Scope,
    Source,
    Verdict,
    digest,
    format_diagnostic,
)
from corsair.contracts.intake import MAX_SCANNER_FINDINGS
from corsair.contracts.recipes import CLEAN_NEGATIVE_QUALIFIED_KINDS
from corsair.evaluation import datasets
from corsair.evaluation.scoring import summarize
from corsair.observability.logging import configure_logging, event, safe_error_detail, safe_text
from corsair.policies.target_binding import (
    TargetBindingReason,
    bind_target_line,
    target_binding,
)
from corsair.settings import Settings

if TYPE_CHECKING:
    # families imports this module's intake schema, so it is imported where it is used.
    from corsair.evaluation.families import Member

INTAKE_SCHEMA = "corsair.intake-dataset/1"
ADMISSIBLE = "admissible"
BLOCKED = "blocked"
# One finding's intake outcome, as an oracle states it and a report records it.
IntakeOutcome = Annotated[
    str, Field(pattern=r"^(admissible(:recipe_function)?|blocked:[a-z][a-z_]{0,63})$")
]


class IntakeBlock(StrEnum):
    """Intake reasons before the target-binding check (whose reasons are its own)."""

    FINDING_INVALID = "finding_invalid"
    PATH_UNSAFE = "path_unsafe"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    SOURCE_NOT_UTF8 = "source_not_utf8"
    RECIPE_MISSING = "recipe_missing"
    RECIPE_INVALID = "recipe_invalid"


@dataclass(frozen=True)
class FindingIntake:
    """One scanner finding's intake: admissible with its candidate request, or blocked."""

    index: int
    file: str | None
    line: int | None
    line_provenance: LineProvenance | None
    outcome: str
    detail: str
    request: InvestigationRequest | None = None

    @property
    def admissible(self) -> bool:
        return self.request is not None

    def receipt(self) -> dict[str, Any]:
        """The JSON receipt row: the candidate request only when it is admissible."""
        return {
            "index": self.index,
            "file": self.file,
            "line": self.line,
            "line_provenance": self.line_provenance,
            "outcome": self.outcome,
            "detail": self.detail,
            "request": None if self.request is None else self.request.model_dump(mode="json"),
        }


def report_findings(content: bytes) -> list[object]:
    """The raw findings of a scan report whose envelope satisfies ``ScanReport``.

    Each finding is validated on its own by ``assess_findings``, so one malformed
    finding is a per-finding block here, while ``load_scan_report`` rejects the whole
    envelope; ``report_admitted`` in the intake receipt records which applies.
    """
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("a scan report must be a JSON object")
    findings = raw.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("scan report findings must be a list")
    if len(findings) > MAX_SCANNER_FINDINGS:
        raise ValueError(f"a scan report holds at most {MAX_SCANNER_FINDINGS} findings")
    ScanReport.model_validate({**raw, "findings": []})
    return findings


def _case_id(stem: str, index: int) -> str:
    """A request identity from the report file name, never from report content."""
    prefix = re.sub(r"[^a-zA-Z0-9_.-]", "-", stem).strip("-._")[:64] or "intake"
    return f"{prefix}-{index:03d}"


def _blocked(
    index: int, file: str | None, reason: str, detail: str, line: int | None = None
) -> FindingIntake:
    """A blocked finding keeps the scanner's declared line, if any, for reading only."""
    return FindingIntake(
        index=index,
        file=file,
        line=line,
        line_provenance=None,
        outcome=f"{BLOCKED}:{reason}",
        detail=format_diagnostic(detail),
    )


def _invalid_fields(error: ValidationError) -> list[str]:
    return sorted({".".join(str(part) for part in item["loc"])[:64] for item in error.errors()})


def assess_finding(
    index: int,
    raw: object,
    *,
    case_id: str,
    source: Source,
    files: Mapping[str, bytes],
    recipe_template: Mapping[str, object] | None,
) -> FindingIntake:
    """Pure: convert one raw finding and decide whether prepare would admit it."""
    try:
        scanner_finding = ScannerFinding.model_validate(raw)
    except ValidationError as error:
        fields = _invalid_fields(error)
        reason = IntakeBlock.PATH_UNSAFE if fields == ["file"] else IntakeBlock.FINDING_INVALID
        return _blocked(index, None, reason, f"invalid scanner finding field(s): {fields}")
    file, line = scanner_finding.file, scanner_finding.line
    # PythonRecipe admits only .py modules; Python is the one running runtime.
    if not file.endswith(".py"):
        detail = f"no recipe runs {file}: Python only"
        return _blocked(index, file, IntakeBlock.UNSUPPORTED_LANGUAGE, detail, line)
    content = files.get(file)
    if content is None:
        detail = f"{file} is absent from the admitted snapshot"
        return _blocked(index, file, TargetBindingReason.FILE_ABSENT, detail, line)
    try:
        module_text = content.decode("utf-8")
    except UnicodeDecodeError:
        return _blocked(index, file, IntakeBlock.SOURCE_NOT_UTF8, f"{file} is not UTF-8", line)
    if recipe_template is None:
        detail = "no recipe template: the operator names the function and payload parameter"
        return _blocked(index, file, IntakeBlock.RECIPE_MISSING, detail, line)
    try:
        request = request_from_scanner(
            scanner_finding, case_id=case_id, source=source, recipe_template=recipe_template
        )
    except ValidationError as error:
        detail = f"invalid recipe: {_invalid_fields(error)}"
        return _blocked(index, file, IntakeBlock.RECIPE_INVALID, detail, line)
    recipe = request.case.recipe
    if not isinstance(recipe, PYTHON_CALLABLE_RECIPES):
        detail = f"{recipe.kind} has no pre-model structural gate; intake supports Python recipes"
        return _blocked(index, file, IntakeBlock.UNSUPPORTED_LANGUAGE, detail, line)
    finding, provenance = bind_target_line(request.case.finding, recipe, module_text)
    failure = target_binding(finding, recipe, module_text)
    if failure is not None:
        return _blocked(index, file, failure.reason, failure.detail, line)
    derived = provenance is LineProvenance.RECIPE_FUNCTION
    return FindingIntake(
        index=index,
        file=file,
        line=finding.line,
        line_provenance=provenance,
        outcome=f"{ADMISSIBLE}:{provenance.value}" if derived else ADMISSIBLE,
        detail=(
            f"line {finding.line} derived from recipe function {recipe.function}"
            if derived
            else f"line {finding.line} binds to {recipe.function}()"
        ),
        request=request,
    )


def assess_findings(
    findings: Sequence[object],
    *,
    report_stem: str,
    source: Source,
    files: Mapping[str, bytes],
    recipe_template: Mapping[str, object] | None,
) -> list[FindingIntake]:
    """Pure: assess every finding of one report, in report order."""
    return [
        assess_finding(
            index,
            raw,
            case_id=_case_id(report_stem, index),
            source=source,
            files=files,
            recipe_template=recipe_template,
        )
        for index, raw in enumerate(findings)
    ]


def intake_counts(intakes: Sequence[FindingIntake]) -> dict[str, Any]:
    """How many findings became admissible requests, and why the rest were blocked."""
    admissible = [item for item in intakes if item.admissible]
    blocked: dict[str, int] = {}
    for item in intakes:
        if not item.admissible:
            reason = item.outcome.removeprefix(f"{BLOCKED}:")
            blocked[reason] = blocked.get(reason, 0) + 1
    return {
        "findings": len(intakes),
        "admissible": len(admissible),
        "admissible_derived_line": sum(
            item.line_provenance is LineProvenance.RECIPE_FUNCTION for item in admissible
        ),
        "blocked": len(intakes) - len(admissible),
        "blocked_reasons": dict(sorted(blocked.items(), key=lambda item: (-item[1], item[0]))),
    }


def admit_source(
    source_dir: Path, settings: Settings, expected_digest: Digest | None = None
) -> tuple[Source, dict[str, bytes]]:
    """Admit ``source_dir`` exactly as prepare would and return its snapshot's files.

    The snapshot goes to a scratch store that is discarded; the returned ``Source``
    pins the snapshot digest, so a candidate request admits only these bytes.
    """
    source = Source(path=str(source_dir.absolute()), expected_digest=expected_digest)
    with TemporaryDirectory(prefix="corsair-intake-") as scratch:
        store = ArtifactStore(scratch)
        ref = snapshot_source(source, settings, store)
        files = dict(iter_snapshot_files(ref, store))
    return source.model_copy(update={"expected_digest": ref.sha256}), files


def intake_receipt(
    report: Path,
    source_dir: Path,
    settings: Settings,
    recipe_template: Path | None = None,
) -> tuple[dict[str, Any], list[FindingIntake]]:
    """The ``corsair intake`` dry run: one report, one source tree, no model, no container."""
    findings = report_findings(report.read_bytes())
    template = None if recipe_template is None else load_recipe_template(recipe_template)
    source, files = admit_source(source_dir, settings)
    intakes = assess_findings(
        findings, report_stem=report.stem, source=source, files=files, recipe_template=template
    )
    invalid = sum(
        item.outcome
        in {f"{BLOCKED}:{IntakeBlock.FINDING_INVALID}", f"{BLOCKED}:{IntakeBlock.PATH_UNSAFE}"}
        for item in intakes
    )
    receipt = {
        "intake": {
            "report": str(report),
            "source": source.path,
            "source_digest": source.expected_digest,
            "recipe_template": None if recipe_template is None else str(recipe_template),
            # load_scan_report admits the envelope only when every finding is valid.
            "report_admitted": invalid == 0,
        },
        "counts": intake_counts(intakes),
        "findings": [item.receipt() for item in intakes],
    }
    return receipt, intakes


class IntakeDatasetEntry(Contract):
    case_id: Identifier
    report: str
    report_digest: Digest
    source: str
    source_digest: Digest
    recipe_template: str | None = None
    recipe_template_digest: Digest | None = None
    oracle: str
    oracle_digest: Digest


class IntakeDataset(Contract):
    schema_version: Literal["corsair.intake-dataset/1"] = "corsair.intake-dataset/1"
    entries: list[IntakeDatasetEntry] = Field(min_length=1, max_length=64)


class IntakeOracle(Contract):
    """Evaluator-only: the expected outcome of each finding, in report order."""

    expected: list[IntakeOutcome] = Field(min_length=1, max_length=MAX_SCANNER_FINDINGS)


def _frozen_source(root: Path, relative: str) -> Path:
    path = datasets.resolve_frozen(root, relative)
    if not path.is_dir():
        raise ValueError("dataset source is missing")
    return path


def _entry_rows(root: Path, entry: IntakeDatasetEntry) -> list[dict[str, Any]]:
    """Assess one frozen report and score each finding against its oracle."""
    report_path, report_bytes = datasets.read_frozen(
        root, entry.report, entry.report_digest, "report"
    )
    _, oracle_bytes = datasets.read_frozen(root, entry.oracle, entry.oracle_digest, "oracle")
    template = None
    if entry.recipe_template is not None:
        if entry.recipe_template_digest is None:
            raise ValueError("a dataset recipe template needs its digest")
        template_path, _ = datasets.read_frozen(
            root, entry.recipe_template, entry.recipe_template_digest, "recipe template"
        )
        template = load_recipe_template(template_path)
    settings = Settings(source_root=str(root))
    source, files = admit_source(
        _frozen_source(root, entry.source), settings, expected_digest=entry.source_digest
    )
    intakes = assess_findings(
        report_findings(report_bytes),
        report_stem=report_path.stem,
        source=source,
        files=files,
        recipe_template=template,
    )
    expected = IntakeOracle.model_validate_json(oracle_bytes).expected
    if len(expected) != len(intakes):
        raise ValueError(
            f"{entry.case_id}: oracle lists {len(expected)} outcomes for {len(intakes)} findings"
        )
    return [
        {
            "case_id": f"{entry.case_id}.{item.index}",
            "status": "pass" if item.outcome == want else "fail",
            "intake": item.outcome,
            "expected": want,
            "file": item.file,
            "line": item.line,
            "line_provenance": item.line_provenance,
            "reason": item.detail,
            # Intake runs no model: these are measured zeros, not unknowns.
            "llm_calls": 0,
            "tool_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "gate_ledger": [
                {
                    "session": None,
                    "round": None,
                    "stage": "intake",
                    "gate": item.outcome,
                    "reason": item.detail,
                }
            ],
        }
        for item, want in zip(intakes, expected, strict=True)
    ]


def score_dataset(path: Path) -> dict[str, Any]:
    """Verify every frozen file, assess each report and score it; oracles stay here."""
    dataset = IntakeDataset.model_validate_json(path.read_bytes())
    root = datasets.dataset_root(path)
    if len({entry.case_id for entry in dataset.entries}) != len(dataset.entries):
        raise ValueError("duplicate intake case identity")
    rows = [row for entry in dataset.entries for row in _entry_rows(root, entry)]
    admissible = [row for row in rows if str(row["intake"]).startswith(ADMISSIBLE)]
    summary = summarize(rows) | {
        "findings": len(rows),
        "admissible": len(admissible),
        "admissible_derived_line": sum(
            row["line_provenance"] is LineProvenance.RECIPE_FUNCTION for row in admissible
        ),
        "blocked": len(rows) - len(admissible),
    }
    return {
        "dataset_digest": digest(dataset),
        "rows": rows,
        "summary": summary,
    }


# Reviewed case intake: dataset draft and dataset freeze.

DRAFT_SCHEMA = "corsair.dataset-draft/1"
# Chain directories written before the corpus moved address it with this prefix.
LEGACY_CORPUS_PREFIX = "../../../../../benchmarks/corpus/"
# Drafting binds the module and the callable from input.json; the template supplies the rest.
DRAFT_BOUND_FIELDS = ("module_file", *CALLABLE_FIELDS)
REVIEW_COLUMNS = (
    "case id",
    "kind",
    "family",
    "split",
    "source digest",
    "proposed acceptable verdicts",
    "proposed expected_fix",
    "proposal basis",
    "validator blockers",
    "decision",
    "reviewer",
    "reviewed oracle digest",
)
# A staged draft's sheet also names each tree below the staging root and its licence files.
STAGED_REVIEW_COLUMNS = (*REVIEW_COLUMNS[:5], "staged tree", "licence file", *REVIEW_COLUMNS[5:])
_REVIEWER_COLUMNS = 3
_DECISIONS = ("accept", "amend", "reject")
# Dataset.entries bound; datasets.MAX_ENTRIES is not importable here (datasets imports intake).
_MAX_DATASET_ENTRIES = 64
_CORPUS_PROVENANCE = {"infosec-harness": "ih", "permissive-reduced": "pr"}
_SLUG = re.compile(r"[a-z0-9][a-z0-9_.-]{0,39}")
_TOKEN = re.compile(r"[A-Za-z0-9_.:/-]{1,64}")
_VARIANT = re.compile(r"^(?P<stem>.+)-[ab]$")
_BASIS_LABELS = {
    "legacy_expected_label": "legacy label",
    "legacy_expected_rule": "legacy rule",
    "truth_type": "truth type",
}
_STAGING = ".freeze-check.json"
# LICENSE, LICENCE, UNLICENSE, COPYING or NOTICE, with optional suffixes (LICENSE-MIT,
# COPYING.LESSER, NOTICE.md), but not a program file such as notice.py.
_LICENCE_NAME = re.compile(r"(?:un)?licen[cs]e|copying|notice", re.IGNORECASE)
_LICENCE_SUFFIX = re.compile(r"(?:[-_.][A-Za-z0-9]+)*")
_PROGRAM_SUFFIXES = {
    *(".c", ".cjs", ".go", ".h", ".java", ".js", ".json", ".mjs", ".pl", ".pm", ".py"),
    *(".rb", ".rs", ".ts"),
}
NOASSERTION = "NOASSERTION"


class DraftRefused(ValueError):
    """A draft input intake will not assemble; the message is code-owned."""


class StagedTree(Contract):
    """One source tree of a staged row: its path below the staging root and the licence or
    notice files its admitted snapshot holds (paths within the tree, sorted)."""

    path: str
    licence_files: list[str] = Field(default_factory=list)


class DraftEntry(DatasetEntry):
    """One drafted row: a would-be manifest entry plus what the reviewer needs to judge it.

    ``request`` and ``oracle`` (the proposed oracle) are relative to the draft directory.
    ``provenance`` copies legacy labels as data; nothing maps them onto the oracle. A staged
    row also names its trees below the staging root.
    """

    kind: str
    origin: str
    source_digest: Digest
    fixed_source_digest: Digest | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    staged_source: StagedTree | None = None
    staged_fixed_source: StagedTree | None = None


class DatasetDraft(Contract):
    """A proposal awaiting review. No dataset loader accepts this schema.

    ``staged`` drafts were read below an explicit staging root (``source_root``); freeze
    imports their reviewed trees into the corpus before any request points at them.
    """

    schema_version: Literal["corsair.dataset-draft/1"] = "corsair.dataset-draft/1"
    source_root: str
    staged: bool = False
    recipe_template_digest: Digest
    budget_digest: Digest | None = None
    entries: list[DraftEntry] = Field(min_length=1, max_length=_MAX_DATASET_ENTRIES)

    @property
    def columns(self) -> tuple[str, ...]:
        """The review sheet's header for this draft."""
        return STAGED_REVIEW_COLUMNS if self.staged else REVIEW_COLUMNS

    def document(self) -> dict[str, Any]:
        """draft.json's content; an unstaged draft keeps its earlier fields only."""
        if self.staged:
            return self.model_dump(mode="json")
        unstaged = {"staged_source", "staged_fixed_source"}
        return self.model_dump(
            mode="json", exclude={"staged": True, "entries": {"__all__": unstaged}}
        )


def licence_files(files: Mapping[str, bytes]) -> list[str]:
    """The licence and notice files of an admitted snapshot, at any depth, sorted."""
    found = []
    for path in files:
        name = path.rsplit("/", 1)[-1]
        match = _LICENCE_NAME.match(name)
        if (
            match is not None
            and _LICENCE_SUFFIX.fullmatch(name, match.end())
            and Path(name).suffix.lower() not in _PROGRAM_SUFFIXES
        ):
            found.append(path)
    return sorted(found)


def propose_oracle(kind: str, *, fixed_source: bool) -> Oracle:
    """The mechanical oracle proposal for a component-scope claim of one recipe kind.

    It admits every decisive verdict the kind can reach and sets no expected verdict: a
    demonstration, and a clean negative only for a kind whose auditor rubric is qualified.
    The fix is unscored when a fixed source exists (the reviewer sets it), else
    NOT_REQUESTED. No legacy label, finding text or outcome is an input.
    """
    qualified = kind in CLEAN_NEGATIVE_QUALIFIED_KINDS
    return Oracle(
        acceptable=[Disposition.SUPPORTED, *([Disposition.REFUTED] if qualified else [])],
        expected_execution=ExecutionStatus.COMPLETED,
        expected_fix=None if fixed_source else FixStatus.NOT_REQUESTED,
        acceptable_verdicts=[
            Verdict.EXPLOIT_DEMONSTRATED,
            *([Verdict.EXPLOIT_NOT_DEMONSTRATED] if qualified else []),
        ],
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise DraftRefused(f"{path}: not a readable JSON file ({safe_text(error)})") from None
    if not isinstance(value, dict):
        raise DraftRefused(f"{path}: expected a JSON object")
    return value


def _evals_root(chain_dir: Path) -> Path:
    """The evals tree holding a chain directory: the parent of its ``datasets`` ancestor."""
    for parent in chain_dir.parents:
        if parent.name == "datasets":
            return parent.parent
    raise DraftRefused(f"{chain_dir}: a chain directory must lie under an evals/datasets tree")


def _staging_root(source_root: Path, chain_dirs: Sequence[Path]) -> Path:
    """The explicit staging root; every chain directory lies below it, with no symlink on
    the way (sources are then admitted below it, which refuses symlinks itself)."""
    root = Path(os.path.normpath(source_root.absolute()))
    if root.is_symlink() or not root.is_dir():
        raise DraftRefused(f"{root}: the staging root must be a directory, not a symbolic link")
    for chain_dir in chain_dirs:
        if not chain_dir.is_relative_to(root) or chain_dir == root:
            raise DraftRefused(f"{chain_dir}: a chain directory must lie under the staging root")
        cursor = root
        for part in chain_dir.relative_to(root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise DraftRefused(f"{chain_dir}: the chain path contains a symbolic link")
    return root


def _chain_source(chain_dir: Path, evals_root: Path, value: object) -> Path:
    """Map an input.json source onto the corpus in place; nothing is copied."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise DraftRefused(f"{chain_dir}: input.json source must be a relative path")
    if value.startswith(LEGACY_CORPUS_PREFIX):
        mapped = evals_root / "datasets/corpus" / value.removeprefix(LEGACY_CORPUS_PREFIX)
    else:
        mapped = chain_dir / value
    return Path(os.path.normpath(mapped))


def _provenance_code(source: Path, chain_dir: Path, evals_root: Path, case: dict) -> str:
    """``ih``/``pr`` for a known corpus, ``syn`` for a tree beside the chain, else ``unk``."""
    corpus = evals_root / "datasets/corpus"
    if source.is_relative_to(corpus):
        code = _CORPUS_PROVENANCE.get(source.relative_to(corpus).parts[0])
        if code is not None:
            return code
    elif source.is_relative_to(chain_dir.parent):
        return "syn"
    declared = case.get("provenance")
    path = declared.get("path") if isinstance(declared, dict) else None
    for name, code in _CORPUS_PROVENANCE.items():
        if isinstance(path, str) and f"/{name}/" in path:
            return code
    return "unk"


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def _legacy_provenance(chain_dir: Path, case: dict) -> dict[str, str]:
    """Legacy label, rule and truth type copied as data; any other legacy field is ignored."""
    provenance: dict[str, str] = {}
    legacy = chain_dir / "oracle.json"
    if legacy.is_file():
        record = _json_object(legacy)
        for key in ("expected_label", "expected_rule"):
            if (value := _token(record.get(key))) is not None:
                provenance[f"legacy_{key}"] = value
    if (truth := _token(case.get("kind"))) is not None:
        provenance["truth_type"] = truth
    return provenance


@dataclass(frozen=True)
class _ChainCase:
    """One chain directory read for drafting: identities, finding fields and source trees."""

    directory: Path
    case_id: str
    family: str
    finding: Finding
    function: str
    source: Path
    fixed_source: Path | None
    provenance: dict[str, str]


def _unprefixed(text: str, language: str) -> str:
    """``text`` without a leading ``<language>-`` token, so an id names its language once."""
    rest = text.removeprefix(f"{language}-")
    return rest or text


def _read_chain(chain_dir: Path, evals_root: Path, language: str) -> _ChainCase:
    """Read case.json and input.json only; never README, submission, manifest or narrative.

    ``language`` is the recipe template kind's, not the parent directory's: the C rows are
    filed under ``chain/common/`` as ``c-<class>-<variant>``, and drop that repeated prefix.
    """
    case = _json_object(chain_dir / "case.json")
    record = _json_object(chain_dir / "input.json")
    raw = record.get("finding")
    if not isinstance(raw, dict):
        raise DraftRefused(f"{chain_dir}: input.json has no finding object")
    title, file, line, symbol = (
        raw.get(key) for key in ("title", "file_path", "start_line", "symbol")
    )
    if not (isinstance(title, str) and isinstance(file, str) and isinstance(symbol, str)):
        raise DraftRefused(f"{chain_dir}: input.json finding needs title, file_path and symbol")
    if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
        raise DraftRefused(f"{chain_dir}: input.json start_line must be an integer")
    if not _SLUG.fullmatch(chain_dir.name):
        raise DraftRefused(f"{chain_dir}: the directory name must be a lowercase slug")
    name = _unprefixed(chain_dir.name, language)
    declared = case.get("family")
    if isinstance(declared, str) and _SLUG.fullmatch(declared):
        vulnerability = _unprefixed(declared, language)
    else:
        variant = _VARIANT.match(name)
        vulnerability = variant["stem"] if variant else name
    source = _chain_source(chain_dir, evals_root, record.get("source"))
    fixed = record.get("fixed_source")
    fixed_source = None if fixed is None else _chain_source(chain_dir, evals_root, fixed)
    provenance = _provenance_code(source, chain_dir, evals_root, case)
    try:
        finding = Finding(
            title=title,
            description=f"{symbol} in {file}"
            + ("" if line is None else f" at line {line}")
            + "; drafted by corsair dataset draft for owner review.",
            file=file,
            line=line,
            claim_scope=Scope.COMPONENT,
        )
    except ValidationError as error:
        raise DraftRefused(f"{chain_dir}: invalid finding {_invalid_fields(error)}") from None
    return _ChainCase(
        directory=chain_dir,
        case_id=f"{provenance}-{language}-{name}",
        family=f"{provenance}-{language}-{vulnerability}",
        finding=finding,
        function=symbol,
        source=source,
        fixed_source=fixed_source,
        provenance=_legacy_provenance(chain_dir, case),
    )


def _admitted(chain: _ChainCase, path: Path, settings: Settings) -> tuple[Source, list[str]]:
    """The admitted source and the licence files of its snapshot."""
    try:
        source, files = admit_source(path, settings)
    except (OSError, ValueError) as error:
        detail = f"{chain.directory}: {path} is not admissible ({safe_text(error)})"
        raise DraftRefused(detail) from None
    return source, licence_files(files)


def _validate_rows(
    directory: Path, entries: Sequence[DatasetEntry], settings: Settings
) -> dict[str, list[str]]:
    """Run ``corsair dataset validate`` over rows whose files are in ``directory``.

    A transient ``corsair.dataset/1`` manifest is written beside them and removed again, so
    every row gets exactly the checks a frozen manifest gets.
    """
    staging = directory / _STAGING
    root = datasets.dataset_root(staging)
    relative = [
        entry.model_copy(
            update={
                "request": (directory / entry.request).relative_to(root).as_posix(),
                "oracle": (directory / entry.oracle).relative_to(root).as_posix(),
            }
        )
        for entry in entries
    ]
    manifest = Dataset(
        entries=[
            DatasetEntry.model_validate(entry.model_dump(include=set(DatasetEntry.model_fields)))
            for entry in relative
        ]
    )
    staging.write_bytes(_json_bytes(manifest.model_dump(mode="json")))
    try:
        report = datasets.validate_dataset(staging, settings)
    finally:
        staging.unlink()
    shared = list(report.problems)
    problems = {entry.case_id: [*entry.problems, *shared] for entry in report.entries}
    return {entry.case_id: problems.get(entry.case_id, shared) for entry in entries}


def _cell(text: str) -> str:
    """One Markdown table cell: no pipe, no line break, bounded."""
    return " ".join(text.replace("|", "/").split())[:400]


def _staged_cells(entry: DraftEntry) -> list[str]:
    """The staged tree and licence file cells: the source tree, then ``fixed`` and its own."""
    trees = [
        (label, tree)
        for label, tree in (("", entry.staged_source), ("fixed ", entry.staged_fixed_source))
        if tree is not None
    ]
    return [
        _cell("; ".join(f"{label}{tree.path}" for label, tree in trees)) or "none",
        _cell(
            "; ".join(f"{label}{', '.join(tree.licence_files) or 'none'}" for label, tree in trees)
        )
        or "none",
    ]


def _code_cells(entry: DraftEntry, proposal: Oracle, *, staged: bool) -> list[str]:
    """The code-owned review columns of one row; a reviewer edits only the last three."""
    verdicts = proposal.acceptable_verdicts
    fix = proposal.expected_fix
    basis = "; ".join(
        f"{_BASIS_LABELS[key]} {value}"
        for key, value in entry.provenance.items()
        if key in _BASIS_LABELS
    )
    return [
        entry.case_id,
        entry.kind,
        entry.family,
        entry.split,
        entry.source_digest,
        *(_staged_cells(entry) if staged else []),
        "unscored" if verdicts is None else ", ".join(verdict.value for verdict in verdicts),
        "unset (fixed_source present; reviewer sets)" if fix is None else fix.value,
        basis or "none",
        _cell("; ".join(entry.blockers)) or "none",
    ]


def review_sheet(draft: DatasetDraft, proposals: Mapping[str, Oracle]) -> str:
    """The code-owned Markdown review sheet: one row per drafted case, reviewer columns empty."""
    split = draft.entries[0].split
    lines = [
        "# Dataset intake review",
        "",
        f"Draft `draft.json` ({DRAFT_SCHEMA}), split `{split}`, {len(draft.entries)} row(s). "
        "Edit only the last three columns of a row.",
        "",
        "- decision: `accept` freezes the row's `oracle.proposed.json`; `amend` freezes the "
        "`oracle.json` you write beside it; `reject` leaves the row out.",
        "- reviewer: who reviewed the row.",
        "- reviewed oracle digest: optional SHA-256 of the oracle file you reviewed; freeze "
        "refuses a mismatch.",
        "",
        "Each proposed oracle is mechanical: it admits every decisive verdict the recipe kind "
        "can reach for a component claim and sets no expected verdict. Narrow it by amending. "
        "The proposal basis column is legacy data, not a label. A row with validator blockers "
        "cannot be frozen until its draft is fixed.",
        "",
    ]
    if draft.staged:
        lines += [
            "Staged draft: every tree lies below the staging root named in `draft.json`. The "
            "staged tree column is its path there and the licence file column the licence or "
            "notice files it holds. Freeze copies accepted and amended rows' trees into the "
            "corpus (`--import-into`) and refuses a tree without a licence file unless "
            "`--allow-noassertion` is given.",
            "",
        ]
    lines += [
        "| " + " | ".join(draft.columns) + " |",
        "| " + " | ".join("---" for _ in draft.columns) + " |",
    ]
    for entry in draft.entries:
        code = _code_cells(entry, proposals[entry.case_id], staged=draft.staged)
        lines.append("| " + " | ".join([*code, *[""] * _REVIEWER_COLUMNS]) + " |")
    return "\n".join(lines) + "\n"


def _draft_output(out: Path, evals_root: Path | None) -> None:
    """Refuse an output under the evals tree (a staged draft: under any ``evals/datasets``)
    or over an earlier draft."""
    where = Path(os.path.normpath(out.absolute()))
    if evals_root is None:
        evals_root = next(
            (
                parent.parent
                for parent in (where, *where.parents)
                if parent.name == "datasets" and parent.parent.name == "evals"
            ),
            None,
        )
    if evals_root is not None and where.is_relative_to(evals_root.absolute()):
        raise DraftRefused(f"{out}: draft output must lie outside the evals tree {evals_root}")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise DraftRefused(f"{out}: draft output directory is not empty")


def _staged_tree(root: Path, source: Source | None, licences: list[str]) -> StagedTree | None:
    if source is None:
        return None
    return StagedTree(path=Path(source.path).relative_to(root).as_posix(), licence_files=licences)


def draft_dataset(
    chain_dirs: Sequence[Path],
    *,
    recipe_template: Path,
    split: str,
    out: Path,
    budget: Path | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Draft one review: requests, mechanical oracle proposals, draft.json and review.md.

    Chain directories and their sources lie under one evals tree, or, with ``source_root``,
    under that explicit staging root (a staged draft). Raises ``DraftRefused`` before
    writing anything when an input cannot be assembled. Rows the dataset checks would reject
    are still written, with their blockers on the sheet.
    """
    if not chain_dirs or len(chain_dirs) > _MAX_DATASET_ENTRIES:
        raise DraftRefused(f"draft between 1 and {_MAX_DATASET_ENTRIES} chain directories")
    directories = [Path(os.path.normpath(path.absolute())) for path in chain_dirs]
    staged = source_root is not None
    if source_root is not None:
        evals_root = _staging_root(source_root, directories)
        _draft_output(out, None)
    else:
        roots = {_evals_root(path) for path in directories}
        if len(roots) != 1:
            raise DraftRefused("every chain directory must lie under one evals tree")
        evals_root = roots.pop()
        _draft_output(out, evals_root)
    try:
        template_bytes = recipe_template.read_bytes()
        template = load_recipe_template(recipe_template, bound=DRAFT_BOUND_FIELDS)
        budget_bytes = None if budget is None else budget.read_bytes()
        limits = None if budget_bytes is None else Budget.model_validate_json(budget_bytes)
    except (OSError, ValueError) as error:
        detail = f"recipe template or budget refused: {safe_error_detail(error)}"
        raise DraftRefused(detail) from None
    # families imports this module's intake schema, so it is imported where it is used.
    from corsair.evaluation.families import kind_language

    settings = Settings(source_root=str(evals_root))
    language = kind_language(str(template["kind"]))
    chains = [_read_chain(path, evals_root, language) for path in directories]
    if len({chain.case_id for chain in chains}) != len(chains):
        raise DraftRefused("two chain directories derive the same case id")
    requests: list[tuple[_ChainCase, InvestigationRequest]] = []
    licences: dict[str, tuple[list[str], list[str]]] = {}
    for chain in chains:
        source, source_licences = _admitted(chain, chain.source, settings)
        fixed, fixed_licences = (
            (None, [])
            if chain.fixed_source is None
            else _admitted(chain, chain.fixed_source, settings)
        )
        licences[chain.case_id] = source_licences, fixed_licences
        try:
            request = request_from_template(
                chain.finding,
                case_id=chain.case_id,
                source=source,
                fixed_source=fixed,
                recipe_template=template,
                function=chain.function,
                budget=limits,
            )
        except ValidationError as error:
            raise DraftRefused(
                f"{chain.directory}: the recipe template does not bind to "
                f"{chain.finding.file}: invalid {_invalid_fields(error)}"
            ) from None
        requests.append((chain, request))

    out.mkdir(parents=True, exist_ok=True)
    entries, proposals = [], {}
    for chain, request in requests:
        case = request.case
        proposal = propose_oracle(case.recipe.kind, fixed_source=case.fixed_source is not None)
        request_bytes = _json_bytes(request.model_dump(mode="json", exclude_none=True))
        oracle_bytes = _json_bytes(proposal.model_dump(mode="json", exclude_none=True))
        (out / chain.case_id).mkdir()
        (out / chain.case_id / "request.json").write_bytes(request_bytes)
        (out / chain.case_id / "oracle.proposed.json").write_bytes(oracle_bytes)
        proposals[chain.case_id] = proposal
        entries.append(
            DraftEntry(
                case_id=chain.case_id,
                family=chain.family,
                split=split,
                request=f"{chain.case_id}/request.json",
                oracle=f"{chain.case_id}/oracle.proposed.json",
                request_digest=digest(request_bytes),
                oracle_digest=digest(oracle_bytes),
                kind=case.recipe.kind,
                origin=chain.directory.relative_to(evals_root).as_posix(),
                source_digest=str(case.source.expected_digest),
                fixed_source_digest=None
                if case.fixed_source is None
                else case.fixed_source.expected_digest,
                provenance=chain.provenance,
                staged_source=_staged_tree(evals_root, case.source, licences[chain.case_id][0])
                if staged
                else None,
                staged_fixed_source=_staged_tree(
                    evals_root, case.fixed_source, licences[chain.case_id][1]
                )
                if staged
                else None,
            )
        )
    blockers = _validate_rows(out.resolve(), entries, settings)
    draft = DatasetDraft(
        source_root=str(evals_root),
        staged=staged,
        recipe_template_digest=digest(template_bytes),
        budget_digest=None if budget_bytes is None else digest(budget_bytes),
        entries=[
            entry.model_copy(update={"blockers": blockers[entry.case_id]}) for entry in entries
        ],
    )
    (out / "draft.json").write_bytes(_json_bytes(draft.document()))
    (out / "review.md").write_text(review_sheet(draft, proposals))
    return {
        "draft": str(out / "draft.json"),
        "review": str(out / "review.md"),
        **({"staged": True, "source_root": draft.source_root} if staged else {}),
        "split": split,
        "entries": [
            {
                "case_id": entry.case_id,
                "family": entry.family,
                "kind": entry.kind,
                "blockers": list(entry.blockers),
            }
            for entry in draft.entries
        ],
        "blocked": sum(bool(entry.blockers) for entry in draft.entries),
    }


@dataclass(frozen=True)
class _Reviewed:
    """One accepted or amended row and the oracle file the reviewer's decision names."""

    entry: DraftEntry
    oracle: str
    oracle_bytes: bytes


def _refusal(rule: str, detail: str) -> dict[str, str]:
    return {"rule": rule, "detail": detail}


def _sheet_rows(text: str, columns: tuple[str, ...]) -> dict[str, list[str]] | None:
    """The review table's rows by case id; None when the code-owned header is absent."""
    rows: dict[str, list[str]] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1):
            continue
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if rows is None:
            if tuple(cells) == columns:
                rows = {}
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows[cells[0]] = cells
    return rows


def _reviewed_rows(
    draft_dir: Path, draft: DatasetDraft, sheet: str, refusals: list[dict[str, str]]
) -> tuple[list[_Reviewed], list[str]]:
    """Check the draft's files and the reviewer's sheet; return the rows to freeze and the
    case ids the reviewer rejected."""
    proposals: dict[str, Oracle] = {}
    for entry in draft.entries:
        try:
            datasets.read_frozen(draft_dir, entry.request, entry.request_digest, "request")
            _, content = datasets.read_frozen(
                draft_dir, entry.oracle, entry.oracle_digest, "proposed oracle"
            )
            proposals[entry.case_id] = Oracle.model_validate_json(content)
        except ValueError as error:
            refusals.append(_refusal("draft_changed", f"{entry.case_id}: {safe_text(error)}"))
    columns = draft.columns
    code_columns = len(columns) - _REVIEWER_COLUMNS
    rows = _sheet_rows(sheet, columns)
    if rows is None:
        refusals.append(
            _refusal("sheet_missing_table", "no review table with the code-owned header")
        )
        return [], []
    known = {entry.case_id for entry in draft.entries}
    for case_id in sorted(set(rows) - known):
        refusals.append(_refusal("sheet_row_unknown", f"{_cell(case_id)} is not a drafted case"))
    selected, rejected = [], []
    for entry in draft.entries:
        cells = rows.get(entry.case_id)
        if cells is None:
            refusals.append(_refusal("sheet_row_missing", f"{entry.case_id} has no review row"))
            continue
        if len(cells) != len(columns) or (
            entry.case_id in proposals
            and cells[:code_columns]
            != _code_cells(entry, proposals[entry.case_id], staged=draft.staged)
        ):
            refusals.append(
                _refusal("sheet_mismatch", f"{entry.case_id}: a code-owned column was edited")
            )
            continue
        decision, _, reviewed = (cell.strip() for cell in cells[code_columns:])
        decision = decision.lower()
        if not decision:
            refusals.append(_refusal("decision_missing", f"{entry.case_id} has no decision"))
            continue
        if decision not in _DECISIONS:
            refusals.append(
                _refusal(
                    "decision_invalid", f"{entry.case_id}: decision must be accept, amend or reject"
                )
            )
            continue
        if decision == "reject":
            rejected.append(entry.case_id)
            continue
        oracle = entry.oracle if decision == "accept" else f"{entry.case_id}/oracle.json"
        try:
            content = datasets.resolve_frozen(draft_dir, oracle).read_bytes()
        except (OSError, ValueError):
            refusals.append(
                _refusal("amended_oracle_missing", f"{entry.case_id}: amend needs {oracle}")
            )
            continue
        if reviewed and reviewed != digest(content):
            refusals.append(
                _refusal(
                    "reviewed_digest_mismatch",
                    f"{entry.case_id}: {oracle} is not the reviewed oracle {_cell(reviewed)}",
                )
            )
            continue
        selected.append(_Reviewed(entry, oracle, content))
    return selected, rejected


def _manifest_members(path: Path, split: str, refusals: list[dict[str, str]]) -> list[Member]:
    """One manifest's members, pairs anchored at its root; an other-split entry whose request
    is unreadable is refused, since its family stem and trees are unknown."""
    from corsair.evaluation import families

    try:
        members = families.dataset_members(path)
    except (OSError, ValueError) as error:
        refusals.append(_refusal("against_unreadable", f"{path}: {safe_text(error)}"))
        return []
    for member in members:
        if member.problem is not None and member.split != split:
            detail = f"{path.name}:{member.case_id}: {member.problem}"
            refusals.append(_refusal("against_unreadable", detail))
    root = datasets.dataset_root(path)
    return [
        replace(member, pair=None if member.pair is None else str(root / member.pair))
        for member in members
    ]


def _split_refusals(
    draft_dir: Path,
    draft: DatasetDraft,
    rows: Sequence[_Reviewed],
    requests: Mapping[str, InvestigationRequest],
    manifests: Sequence[Path],
) -> list[dict[str, str]]:
    """Refuse a row whose family, family stem, case, chain pair or source tree sits in another
    split. Each drafted row is a member built as ``dataset_members`` builds a frozen entry, so
    freeze refuses what ``just dataset-families`` would report."""
    from corsair.evaluation import families

    refusals: list[dict[str, str]] = []
    split = rows[0].entry.split
    root = Path(draft.source_root)
    members = [
        families.request_member(
            "draft",
            row.entry,
            families.chain_pair(str(root / row.entry.origin / "request.json")),
            requests[row.entry.case_id],
            draft_dir / row.entry.request,
            root,
        )
        for row in rows
    ]
    for path in manifests:
        members += _manifest_members(path, split, refusals)
    for violation in families.split_violations(members):
        if not violation["rule"].endswith("_splits"):
            continue
        placements: dict[str, list[str]] = violation["splits"]
        if not any(name.startswith("draft:") for names in placements.values() for name in names):
            continue
        key = next(value for name, value in violation.items() if name not in {"rule", "splits"})
        shown = ", ".join(key) if isinstance(key, list) else key
        where = "; ".join(f"{name}: {', '.join(found)}" for name, found in placements.items())
        refusals.append(_refusal(violation["rule"], f"{shown} is placed in {where}"))
    return refusals


def _frozen_directory(
    into: Path, source_root: Path, request: InvestigationRequest
) -> tuple[Path | None, bool]:
    """Where a row's frozen request and oracle go, and whether its sources stay absolute.

    Admission refuses ``..`` in a source path, so a frozen request must sit in an ancestor
    of its source trees. Inside the evals tree that is the first directory below the
    manifest's own directory holding every tree (``evals/datasets/corpus`` for the corpus,
    as for the existing in-place Perl row), and the sources become relative to it. A
    manifest outside the evals tree (a scratch freeze) keeps absolute sources under its own
    ``<stem>/`` directory. ``None`` means the trees share no such directory.
    """
    manifest_dir = into.resolve().parent
    case = request.case
    trees = [Path(item.path).resolve() for item in (case.source, case.fixed_source) if item]
    if not manifest_dir.is_relative_to(source_root.resolve()):
        return manifest_dir / into.stem, True
    firsts = {
        tree.relative_to(manifest_dir).parts[0] if tree.is_relative_to(manifest_dir) else None
        for tree in trees
    }
    if len(firsts) != 1 or None in firsts:
        return None, False
    return manifest_dir / str(firsts.pop()), False


def _reanchored(request: InvestigationRequest, directory: Path) -> InvestigationRequest:
    """Rewrite absolute draft source paths relative to the frozen request's directory."""

    def relative(source: Source | None) -> Source | None:
        if source is None:
            return None
        path = Path(source.path).resolve().relative_to(directory).as_posix()
        return source.model_copy(update={"path": path})

    case = request.case
    return request.model_copy(
        update={
            "case": case.model_copy(
                update={
                    "source": relative(case.source),
                    "fixed_source": relative(case.fixed_source),
                }
            )
        }
    )


@dataclass(frozen=True)
class _ImportTree:
    """One admitted staged tree of an accepted row and where freeze copies it."""

    name: Literal["source", "fixed"]
    staged: Source
    staged_tree: str
    files: dict[str, bytes]
    licence_files: list[str]


@dataclass(frozen=True)
class _Import:
    """An accepted staged row's import: ``<import-into>/<case id>/{source,fixed}/``."""

    case_id: str
    directory: Path
    trees: list[_ImportTree]

    @property
    def licence(self) -> str:
        return NOASSERTION if any(not tree.licence_files for tree in self.trees) else "retained"

    def provenance(self) -> dict[str, Any]:
        """The code-owned provenance.json written beside the imported trees."""
        return {
            "case_id": self.case_id,
            "licence": self.licence,
            "trees": {
                tree.name: {
                    "staged_tree": tree.staged_tree,
                    "snapshot_digest": tree.staged.expected_digest,
                    "licence_files": tree.licence_files,
                }
                for tree in self.trees
            },
        }

    def imported(self, request: InvestigationRequest) -> InvestigationRequest:
        """The request with its sources at the imported trees, digests unchanged."""
        sources = {
            "source" if tree.name == "source" else "fixed_source": tree.staged.model_copy(
                update={"path": str(self.directory / tree.name)}
            )
            for tree in self.trees
        }
        return request.model_copy(update={"case": request.case.model_copy(update=sources)})


def _import_plan(
    rows: Sequence[_Reviewed],
    requests: Mapping[str, InvestigationRequest],
    *,
    draft: DatasetDraft,
    import_into: Path,
    corpus: Path,
    allow_noassertion: bool,
    refusals: list[dict[str, str]],
) -> dict[str, _Import]:
    """Check every accepted row's import without writing: the target lies below the corpus
    and does not exist, each staged tree still has its drafted snapshot digest, and each tree
    holds a licence file unless NOASSERTION is allowed."""
    target = import_into.resolve()
    if not target.is_relative_to(corpus.resolve()) or target == corpus.resolve():
        refusals.append(
            _refusal("import_outside_corpus", f"{import_into} must lie below {corpus}/")
        )
        return {}
    root = Path(draft.source_root)
    settings = Settings(source_root=draft.source_root)
    plan: dict[str, _Import] = {}
    for row in rows:
        case_id = row.entry.case_id
        directory = target / case_id
        if directory.exists() or directory.is_symlink():
            refusals.append(_refusal("import_target_exists", f"{directory} exists"))
        case = requests[case_id].case
        trees = []
        for name, source in (("source", case.source), ("fixed", case.fixed_source)):
            if source is None:
                continue
            staged_tree = Path(source.path).relative_to(root).as_posix()
            try:
                _, files = admit_source(Path(source.path), settings, source.expected_digest)
            except (OSError, ValueError) as error:
                refusals.append(
                    _refusal(
                        "import_source_changed", f"{case_id}: {staged_tree}: {safe_text(error)}"
                    )
                )
                continue
            licences = licence_files(files)
            if not licences and not allow_noassertion:
                refusals.append(
                    _refusal(
                        "licence_missing",
                        f"{case_id}: {name} tree {staged_tree} holds no LICENSE, COPYING or "
                        f"NOTICE file; --allow-noassertion records licence {NOASSERTION}",
                    )
                )
            trees.append(_ImportTree(name, source, staged_tree, files, licences))
        plan[case_id] = _Import(case_id, directory, trees)
    return plan


def _write_tree(target: Path, files: Mapping[str, bytes]) -> None:
    """Write an admitted snapshot's files under a new ``target``, never over a file."""
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)


def _write_imports(plan: Mapping[str, _Import], corpus_settings: Settings) -> str | None:
    """Copy every planned tree, then re-admit each copy against its drafted digest. On any
    failure remove everything written (the targets did not exist) and return the detail."""
    created = [
        path
        for directory in {item.directory.parent for item in plan.values()}
        for path in (directory, *directory.parents)
        if not path.exists()
    ]
    written: list[Path] = []
    try:
        for item in plan.values():
            written.append(item.directory)
            for tree in item.trees:
                _write_tree(item.directory / tree.name, tree.files)
                admit_source(
                    item.directory / tree.name, corpus_settings, tree.staged.expected_digest
                )
            (item.directory / "provenance.json").write_bytes(_json_bytes(item.provenance()))
    except (OSError, ValueError) as error:
        for directory in written:
            shutil.rmtree(directory, ignore_errors=True)
        for path in sorted(set(created), key=lambda value: len(value.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        return safe_text(error)
    return None


def _freeze_result(
    draft_dir: Path,
    review: Path,
    into: Path,
    against: Sequence[Path],
    import_into: Path | None,
) -> dict[str, Any]:
    return {
        "freeze": {
            "draft": str(draft_dir),
            "review": str(review),
            "into": str(into),
            "against": [str(path) for path in against],
            "import_into": None if import_into is None else str(import_into),
        },
        "written": False,
        "refusals": [],
        "identity": None,
        "frozen": [],
        "rejected": [],
        "imported": [],
        "absolute_sources": False,
        "validation": None,
    }


def freeze_dataset(
    draft_dir: Path,
    *,
    review: Path,
    into: Path,
    against: Sequence[Path],
    import_into: Path | None = None,
    allow_noassertion: bool = False,
) -> dict[str, Any]:
    """Freeze a reviewed draft's accepted and amended rows into a ``corsair.dataset/1`` manifest.

    Nothing is written while any refusal stands. A write appends the rows to ``into`` (kept
    entries are unchanged), copies each row's request and reviewed oracle beside the corpus
    and reports the old and new dataset identities. A staged draft needs ``import_into``
    (below the corpus of ``into``'s evals tree): each accepted row's trees are first copied
    there byte for byte, with their licence files, and their digests re-checked.
    """
    result = _freeze_result(draft_dir, review, into, against, import_into)
    refusals: list[dict[str, str]] = result["refusals"]
    base = draft_dir.resolve()
    try:
        draft = DatasetDraft.model_validate_json((base / "draft.json").read_bytes())
        sheet = review.read_text()
    except (OSError, ValueError) as error:
        refusals.append(_refusal("draft_unreadable", safe_error_detail(error)))
        return result
    if draft.staged and import_into is None:
        detail = "a staged draft is frozen only with --import-into evals/datasets/corpus/<dir>"
        refusals.append(_refusal("import_required", detail))
        return result
    if not draft.staged and import_into is not None:
        detail = "--import-into copies a staged draft's trees; this draft is not staged"
        refusals.append(_refusal("import_not_staged", detail))
        return result
    rows, result["rejected"] = _reviewed_rows(base, draft, sheet, refusals)
    if refusals or not rows:
        return result
    existing: Dataset | None = None
    if into.exists():
        try:
            existing = Dataset.model_validate_json(into.read_bytes())
        except (OSError, ValueError) as error:
            refusals.append(_refusal("into_invalid", f"{into}: {safe_error_detail(error)}"))
            return result
    kept = [] if existing is None else list(existing.entries)
    frozen_ids = {entry.case_id for entry in kept}
    for row in rows:
        if row.entry.case_id in frozen_ids:
            refusals.append(_refusal("case_already_frozen", f"{row.entry.case_id} is in {into}"))
    if len(kept) + len(rows) > _MAX_DATASET_ENTRIES:
        refusals.append(
            _refusal(
                "too_many_entries",
                f"{len(kept)} kept + {len(rows)} new exceeds {_MAX_DATASET_ENTRIES} entries",
            )
        )
    settings = Settings(source_root=draft.source_root)
    reviewed = [
        row.entry.model_copy(
            update={"oracle": row.oracle, "oracle_digest": digest(row.oracle_bytes)}
        )
        for row in rows
    ]
    for case_id, problems in _validate_rows(base, reviewed, settings).items():
        if problems:
            refusals.append(_refusal("row_invalid", f"{case_id}: {'; '.join(problems)}"))
    requests = {
        row.entry.case_id: normalize_request_sources(
            InvestigationRequest.model_validate_json((base / row.entry.request).read_bytes()),
            base / row.entry.request,
        )
        for row in rows
    }
    # A staged draft's rows are frozen over their imported trees, in the evals tree of into.
    frozen_root = Path(draft.source_root)
    frozen_requests = dict(requests)
    plan: dict[str, _Import] = {}
    if import_into is not None:
        frozen_root = datasets.dataset_root(into)
        plan = _import_plan(
            rows,
            requests,
            draft=draft,
            import_into=import_into,
            corpus=frozen_root / "datasets/corpus",
            allow_noassertion=allow_noassertion,
            refusals=refusals,
        )
        if not plan:  # the target lies outside the corpus: no frozen layout to check
            return result
        for case_id, item in plan.items():
            frozen_requests[case_id] = item.imported(requests[case_id])
    layout: dict[str, tuple[Path, bool]] = {}
    for row in rows:
        directory, absolute = _frozen_directory(
            into, frozen_root, frozen_requests[row.entry.case_id]
        )
        if directory is None:
            refusals.append(
                _refusal(
                    "sources_span_directories",
                    f"{row.entry.case_id}: its source trees share no directory below "
                    f"{into.resolve().parent}",
                )
            )
            continue
        layout[row.entry.case_id] = directory, absolute
        for suffix in ("request", "oracle"):
            target = directory / f"{row.entry.case_id}.{suffix}.json"
            if target.exists():
                refusals.append(_refusal("case_file_exists", f"{target} exists"))
    manifests = [*against, *([into] if existing is not None else [])]
    refusals += _split_refusals(base, draft, rows, requests, manifests)
    if refusals:
        return result

    corpus_settings = Settings(source_root=str(frozen_root))
    if plan:
        failure = _write_imports(plan, corpus_settings)
        if failure is not None:
            refusals.append(_refusal("import_digest_mismatch", failure))
            return result
        result["imported"] = [
            {
                "case_id": item.case_id,
                "directory": str(item.directory),
                "licence": item.licence,
                "licence_files": {tree.name: tree.licence_files for tree in item.trees},
            }
            for item in plan.values()
        ]
    root = datasets.dataset_root(into)
    added = []
    for row in rows:
        directory, absolute = layout[row.entry.case_id]
        request = frozen_requests[row.entry.case_id]
        frozen = request if absolute else _reanchored(request, directory)
        request_bytes = _json_bytes(frozen.model_dump(mode="json", exclude_none=True))
        paths = {
            suffix: directory / f"{row.entry.case_id}.{suffix}.json"
            for suffix in ("request", "oracle")
        }
        directory.mkdir(parents=True, exist_ok=True)
        paths["request"].write_bytes(request_bytes)
        paths["oracle"].write_bytes(row.oracle_bytes)
        added.append(
            DatasetEntry(
                case_id=row.entry.case_id,
                family=row.entry.family,
                split=row.entry.split,
                request=paths["request"].relative_to(root).as_posix(),
                oracle=paths["oracle"].relative_to(root).as_posix(),
                request_digest=digest(request_bytes),
                oracle_digest=digest(row.oracle_bytes),
            )
        )
    manifest = Dataset(entries=[*kept, *added])
    temporary = into.with_name(f".{into.name}.tmp")
    temporary.write_bytes(_json_bytes(manifest.model_dump(mode="json")))
    os.replace(temporary, into)
    report = datasets.validate_dataset(into, corpus_settings)
    result["written"] = True
    result["identity"] = {
        "old": None if existing is None else digest(existing),
        "new": digest(manifest),
    }
    result["frozen"] = [entry.case_id for entry in added]
    # A scratch manifest outside the evals tree keeps absolute, machine-local sources.
    result["absolute_sources"] = any(absolute for _, absolute in layout.values())
    result["validation"] = {
        "valid": report.valid,
        "dataset_digest": report.dataset_digest,
        "problems": [*report.problems, *(p for e in report.entries for p in e.problems)],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a frozen scanner-intake dataset")
    parser.add_argument("dataset")
    parser.add_argument("--output", help="Report path (default .runs/evaluations/intake-*.json)")
    args = parser.parse_args()
    from rich.console import Console

    configure_logging(Console(stderr=True, no_color=True), format="json")
    try:
        report = score_dataset(Path(args.dataset))
    except Exception as error:
        event(
            "intake_eval.failed",
            level=logging.ERROR,
            error_type=type(error).__name__,
            message=safe_error_detail(error),
        )
        raise SystemExit(2) from None
    destination = Path(args.output or f".runs/evaluations/intake-{uuid4().hex}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(destination), "summary": report["summary"]}, indent=2))
    raise SystemExit(0 if report["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
