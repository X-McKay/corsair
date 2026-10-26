"""Scanner intake: which findings of a scan report become admissible requests, and why not.

``assess_findings`` is pure. It converts each finding with ``request_from_scanner`` (the
operator's recipe template bound to the finding's file) and runs the trusted line
binding (``bind_target_line``) and pre-model ``target_binding`` check that the prepare
activity runs, over the files of the admitted source snapshot. It reads no finding
narrative, calls no model and runs no target code. ``admit_source`` is its I/O edge: the
real snapshot admission, into a scratch store that is discarded. ``score_dataset``
scores a frozen intake dataset against evaluator-only oracles; ``main`` runs it for
``just eval-intake``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from corsair.adapters.scm.local import iter_snapshot_files, snapshot_source
from corsair.adapters.scm.requests import load_recipe_template, request_from_scanner
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Contract,
    Digest,
    Identifier,
    InvestigationRequest,
    LineProvenance,
    ScannerFinding,
    ScanReport,
    Source,
    digest,
    format_diagnostic,
)
from corsair.contracts.intake import MAX_SCANNER_FINDINGS
from corsair.evaluation.scoring import dataset_root, read_frozen_file, summarize
from corsair.observability.logging import configure_logging, event, safe_error_detail
from corsair.policies.target_binding import (
    TargetBindingReason,
    bind_target_line,
    target_binding,
)
from corsair.settings import Settings

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
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise ValueError("dataset source escapes its root or is missing")
    return path


def _entry_rows(root: Path, entry: IntakeDatasetEntry) -> list[dict[str, Any]]:
    """Assess one frozen report and score each finding against its oracle."""
    report_path, report_bytes = read_frozen_file(root, entry.report, entry.report_digest, "report")
    _, oracle_bytes = read_frozen_file(root, entry.oracle, entry.oracle_digest, "oracle")
    template = None
    if entry.recipe_template is not None:
        if entry.recipe_template_digest is None:
            raise ValueError("a dataset recipe template needs its digest")
        template_path, _ = read_frozen_file(
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
    root = dataset_root(path)
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
