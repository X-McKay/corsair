"""Frozen evaluation datasets: digest-verified loading and offline validation.

The evaluators read a manifest's request, input and oracle bytes through these loaders
(``load_dataset``, ``load_frozen_fixture`` and the ``read_frozen`` primitive), which verify each
declared digest and return oracle data to the evaluator caller only. Validation runs no model,
target, container or service. The intake evaluator reads its frozen files through these loaders
while validation runs that evaluator, so the two modules import each other as module objects and
either may be imported first.

A stale digest, a self-contradicting oracle, a moved source tree or a case the pre-model
``target_binding`` gate blocks is otherwise found only when an evaluation runs on the rig. Each
entry gets one finite set of checks over the exact bytes the evaluators read: the manifest entry,
its frozen digests, the request or role input, the source snapshot digest, target binding and the
oracle's own consistency. Oracles are read here, on the evaluator side, only to check them; no
oracle value is reported.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from corsair.adapters.scm.local import iter_snapshot_files, snapshot_source
from corsair.adapters.scm.requests import load_recipe_template, normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    PYTHON_CALLABLE_RECIPES,
    AuditDecision,
    AuditInput,
    Dataset,
    DatasetEntry,
    Digest,
    Disposition,
    ExecutionStatus,
    FixStatus,
    InvestigationRequest,
    InvestigationResult,
    LineProvenance,
    Oracle,
    Scope,
    Source,
    Verdict,
    digest,
)
from corsair.contracts.recipes import CLEAN_NEGATIVE_QUALIFIED_KINDS
from corsair.evaluation import intake
from corsair.evaluation.scoring import score
from corsair.observability.logging import safe_error_detail, safe_text
from corsair.policies.target_binding import bind_target_line, target_binding
from corsair.settings import Settings

CASE_SCHEMA = "corsair.dataset/1"
AGENT_SCHEMA = "corsair.agent-dataset/1"
MAX_ENTRIES = 64
CHECKS = ("entry", "digests", "request", "source", "target_binding", "oracle")
# Families and splits group cohorts; a lowercase identifier catches case and whitespace typos.
_GROUP_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,79}")
_AGENT_FIELDS = ("case_id", "input", "oracle", "input_digest", "oracle_digest")

type Status = Literal["pass", "fail", "skip"]


def dataset_root(path: Path) -> Path:
    # Reference-layout manifests in evals/datasets address the enclosing evals tree.
    parent = path.parent.resolve()
    return parent.parent if parent.name == "datasets" else parent


def resolve_frozen(root: Path, relative: str) -> Path:
    """Resolve a manifest path below its dataset root; every evaluator and the validator use it."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("dataset path escapes its root")
    return path


def read_frozen(root: Path, relative: str, expected: Digest, kind: str) -> tuple[Path, bytes]:
    """Read once and verify the exact bytes that the evaluator will parse."""
    path = resolve_frozen(root, relative)
    if not path.is_file():
        raise ValueError("dataset path escapes its root or is missing")
    content = path.read_bytes()
    if digest(content) != expected:
        raise ValueError(f"frozen {kind} digest changed")
    return path, content


def load_dataset(path: Path) -> tuple[Dataset, list[InvestigationRequest], dict[str, Oracle]]:
    """Verify the frozen files first. Return oracle data only to the evaluator caller."""
    dataset = Dataset.model_validate_json(path.read_bytes())
    root = dataset_root(path)
    requests, oracles = [], {}
    family_splits: dict[str, str] = {}
    for entry in dataset.entries:
        if entry.case_id in oracles:
            raise ValueError("duplicate case identity")
        if entry.family in family_splits and family_splits[entry.family] != entry.split:
            raise ValueError("related family variants may not cross dataset splits")
        family_splits[entry.family] = entry.split
        request_path, request_bytes = read_frozen(
            root, entry.request, entry.request_digest, "request"
        )
        _, oracle_bytes = read_frozen(root, entry.oracle, entry.oracle_digest, "oracle")
        request = InvestigationRequest.model_validate_json(request_bytes)
        if request.case.case_id != entry.case_id:
            raise ValueError("dataset and request case identities disagree")
        requests.append(normalize_request_sources(request, request_path))
        oracles[entry.case_id] = Oracle.model_validate_json(oracle_bytes)
    return dataset, requests, oracles


def load_frozen_fixture(root: Path, entry: dict[str, Any]) -> tuple[Path, bytes, dict[str, Any]]:
    """Read/verify an isolated-agent fixture once; the oracle remains local to the evaluator."""
    input_path, input_bytes = read_frozen(root, entry["input"], entry["input_digest"], "input")
    _, oracle_bytes = read_frozen(root, entry["oracle"], entry["oracle_digest"], "oracle")
    oracle = json.loads(oracle_bytes)
    if not isinstance(oracle, dict):
        raise ValueError("isolated oracle must be a JSON object")
    return input_path, input_bytes, oracle


@dataclass
class EntryReport:
    """One manifest entry's checks; ``actual`` keeps the current file digests for a fix."""

    index: int
    case_id: str
    kind: str
    family: str | None = None
    split: str | None = None
    checks: dict[str, Status] = field(default_factory=lambda: dict.fromkeys(CHECKS, "skip"))
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    declared: dict[str, str] = field(default_factory=dict)
    actual: dict[str, str] = field(default_factory=dict)

    def passed(self, check: str) -> None:
        if self.checks[check] != "fail":
            self.checks[check] = "pass"

    def fail(self, check: str, problem: str) -> None:
        self.checks[check] = "fail"
        self.problems.append(f"{check}: {problem}")

    @property
    def valid(self) -> bool:
        return "fail" not in self.checks.values()

    @property
    def only_digests_stale(self) -> bool:
        """Every failure is a digest mismatch of a file that exists and is otherwise valid."""
        failed = {name for name, status in self.checks.items() if status == "fail"}
        return failed == {"digests"} and set(self.declared) == set(self.actual)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "family": self.family,
            "split": self.split,
            "status": "pass" if self.valid else "fail",
            "checks": dict(self.checks),
            "problems": list(self.problems),
            "notes": list(self.notes),
        }


@dataclass
class DatasetReport:
    path: Path
    schema_version: str | None = None
    kind: str | None = None
    dataset_digest: str | None = None
    loader: Status = "skip"
    problems: list[str] = field(default_factory=list)
    entries: list[EntryReport] = field(default_factory=list)
    digest_changes: list[dict[str, Any]] = field(default_factory=list)
    # Set by a refreeze that rewrote the manifest: the dataset digest before and after.
    dataset_digest_change: dict[str, str | None] | None = None

    @property
    def valid(self) -> bool:
        return (
            not self.problems
            and self.loader != "fail"
            and bool(self.entries)
            and all(entry.valid for entry in self.entries)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": str(self.path),
            "schema_version": self.schema_version,
            "kind": self.kind,
            "dataset_digest": self.dataset_digest,
            "cohort": [entry.case_id for entry in self.entries],
            "status": "pass" if self.valid else "fail",
            "loader": self.loader,
            "problems": list(self.problems),
            "entries": [entry.as_dict() for entry in self.entries],
            "digest_changes": list(self.digest_changes),
            "dataset_digest_change": self.dataset_digest_change,
        }


def case_oracle_problems(oracle: Oracle) -> list[str]:
    """Contradictions that make a composed-case oracle reject its own expectation."""
    problems: list[str] = []
    overlap = sorted(set(oracle.acceptable) & set(oracle.forbidden))
    if overlap:
        problems.append(f"dispositions both acceptable and forbidden: {', '.join(overlap)}")
    forbidden = set(oracle.forbidden_verdicts)
    if oracle.acceptable_verdicts is not None:
        if not oracle.acceptable_verdicts:
            problems.append("acceptable_verdicts is empty, so no verdict can pass")
        overlap = sorted(set(oracle.acceptable_verdicts) & forbidden)
        if overlap:
            problems.append(f"verdicts both acceptable and forbidden: {', '.join(overlap)}")
        expected = oracle.expected_verdict
        if expected is not None and expected not in oracle.acceptable_verdicts:
            problems.append(f"expected_verdict {expected.value} is not in acceptable_verdicts")
    if oracle.expected_verdict is not None and oracle.expected_verdict in forbidden:
        problems.append(f"expected_verdict {oracle.expected_verdict.value} is forbidden")
    if not problems and not any(oracle.verdict_allowed(verdict) for verdict in Verdict):
        problems.append("no verdict satisfies the oracle")
    return problems


def claim_scope_problems(scope: Scope, oracle: Oracle) -> list[str]:
    """A demonstration label the scope policy can never produce for the request's claim.

    ``policies.verdicts`` reports a demonstrated component claim as EXPLOIT_DEMONSTRATED and a
    demonstrated application claim, which every current recipe probes only at the component
    seam, as COMPONENT_EXPLOIT_DEMONSTRATED. An oracle that scores only the other label can
    never pass; the first live chain found exactly that mislabel.
    """
    reachable, unreachable = (
        (Verdict.EXPLOIT_DEMONSTRATED, Verdict.COMPONENT_EXPLOIT_DEMONSTRATED)
        if scope is Scope.COMPONENT
        else (Verdict.COMPONENT_EXPLOIT_DEMONSTRATED, Verdict.EXPLOIT_DEMONSTRATED)
    )
    problems: list[str] = []
    acceptable = oracle.acceptable_verdicts
    if acceptable is not None and unreachable in acceptable and reachable not in acceptable:
        problems.append(
            f"acceptable_verdicts admits only {unreachable.value} but the request claims "
            f"{scope.value} scope, which a demonstration labels {reachable.value}"
        )
    if oracle.expected_verdict is unreachable:
        problems.append(
            f"expected_verdict {unreachable.value} is unreachable for a {scope.value}-scope "
            f"claim, which a demonstration labels {reachable.value}"
        )
    return problems


def negative_label_problems(kind: str, oracle: Oracle) -> list[str]:
    """A negative label the kernel withholds for a recipe kind without a qualified rubric."""
    if kind in CLEAN_NEGATIVE_QUALIFIED_KINDS:
        return []
    negative = Verdict.EXPLOIT_NOT_DEMONSTRATED
    acceptable = oracle.acceptable_verdicts
    problems: list[str] = []
    if acceptable is not None and acceptable == [negative]:
        problems.append(
            f"acceptable_verdicts admits only {negative.value} but clean negatives are withheld "
            f"for {kind} (auditor rubric not qualified)"
        )
    elif oracle.expected_verdict is negative:
        problems.append(
            f"expected_verdict {negative.value} is unreachable for {kind}: clean negatives are "
            "withheld until its auditor rubric is qualified"
        )
    return problems


def producer_oracle_problems(oracle: dict[str, Any]) -> list[str]:
    """Shape and consistency of a producer diagnostic oracle; payload values are never echoed."""
    control = oracle.get("control_payload")
    candidates = oracle.get("candidate_payloads")
    problems: list[str] = []
    if not isinstance(control, str):
        problems.append("control_payload must be a string")
    if (
        not isinstance(candidates, list)
        or not candidates
        or not all(isinstance(item, str) for item in candidates)
    ):
        problems.append("candidate_payloads must be a non-empty list of strings")
    elif isinstance(control, str):
        if control in candidates:
            problems.append("control_payload is also an accepted candidate payload")
        if len(set(candidates)) != len(candidates):
            problems.append("candidate_payloads lists a payload twice")
    return problems


_REJECTION_RULES = ("R1", "R2", "R3", "R4")


def auditor_oracle_problems(oracle: dict[str, Any]) -> list[str]:
    """A decision, and when the oracle names one, the decisive rule that decision allows."""
    decisions = {decision.value for decision in AuditDecision}
    decision = oracle.get("decision")
    if decision not in decisions:
        return [f"decision must be one of {', '.join(sorted(decisions))}"]
    if "rule" not in oracle:
        return []
    allowed = ("ALL",) if decision == AuditDecision.ACCEPT else _REJECTION_RULES
    if oracle["rule"] not in allowed:
        return [f"rule for {decision} must be one of {', '.join(allowed)}"]
    return []


def blocked_result(request: InvestigationRequest, reason: str) -> InvestigationResult:
    """The terminal result a prepare-time block produces, before any model or container."""
    return InvestigationResult(
        run_id="dataset-validate",
        case_id=request.case.case_id,
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.UNABLE_TO_RUN,
        execution_status=ExecutionStatus.BLOCKED,
        reason=reason,
        scope=request.case.finding.claim_scope,
        fix_status=FixStatus.UNVERIFIED
        if request.case.fixed_source is not None
        else FixStatus.NOT_REQUESTED,
    )


class _Validator:
    """Checks for one dataset over one disposable artifact store; never the operator's store."""

    def __init__(self, root: Path, settings: Settings, store: ArtifactStore) -> None:
        self.root = root
        self.settings = settings
        self.store = store

    def read(self, entry: EntryReport, name: str, relative: str, declared: str) -> bytes | None:
        """Read one frozen file and record its digest against the manifest declaration."""
        try:
            path = resolve_frozen(self.root, relative)
            content = path.read_bytes()
        except (OSError, ValueError) as error:
            entry.fail("digests", f"{name} {relative}: {safe_text(error)}")
            return None
        entry.declared[name], entry.actual[name] = declared, digest(content)
        if entry.actual[name] != declared:
            entry.fail("digests", f"{name}_digest is stale for {relative}")
        else:
            entry.passed("digests")
        return content

    def request(
        self, entry: EntryReport, relative: str, content: bytes
    ) -> InvestigationRequest | None:
        """Parse a request the way the evaluators do and anchor its sources at its file."""
        try:
            request = InvestigationRequest.model_validate_json(content)
        except ValueError as error:
            entry.fail("request", safe_error_detail(error))
            return None
        if request.case.case_id != entry.case_id:
            entry.fail("request", f"request case_id {request.case.case_id} differs from the entry")
        else:
            entry.passed("request")
        return normalize_request_sources(request, resolve_frozen(self.root, relative))

    def snapshot(self, entry: EntryReport, label: str, source: Source) -> dict[str, bytes] | None:
        """Admit one source tree exactly as prepare does and compare its frozen digest."""
        if source.expected_digest is None:
            entry.fail("source", f"{label} declares no expected_digest")
            return None
        try:
            ref = snapshot_source(source, self.settings, self.store)
            return dict(iter_snapshot_files(ref, self.store))
        except (OSError, ValueError) as error:
            prefix = "" if label == "source" else f"{label}: "
            entry.fail("source", f"{prefix}{safe_text(error)}")
            return None

    def module_text(
        self, entry: EntryReport, request: InvestigationRequest
    ) -> tuple[bool, str | None]:
        """Admit source and fixed source; return whether admission held and the module text."""
        case = request.case
        files = self.snapshot(entry, "source", case.source)
        if case.fixed_source is not None:
            fixed = self.snapshot(entry, "fixed_source", case.fixed_source)
            if fixed is not None and case.recipe.module_file not in fixed:
                entry.fail("source", f"fixed_source lacks {case.recipe.module_file}")
        if files is None or entry.checks["source"] == "fail":
            return False, None
        entry.passed("source")
        content = files.get(case.recipe.module_file)
        if content is None:
            return True, None
        try:
            return True, content.decode("utf-8")
        except UnicodeDecodeError:
            entry.fail("source", f"{case.recipe.module_file} is not UTF-8")
            return False, None

    def binding(
        self, entry: EntryReport, request: InvestigationRequest, oracle: Oracle | None
    ) -> None:
        """Run the pure pre-model gate; a block passes only if the oracle expects that stop."""
        admitted, text = self.module_text(entry, request)
        if not admitted:
            return
        recipe = request.case.recipe
        if not isinstance(recipe, PYTHON_CALLABLE_RECIPES):
            # The structural gate is Python-AST specific, as in activities.prepare.
            entry.passed("target_binding")
            return
        finding = request.case.finding
        if text is not None:
            # Bind a missing line from the recipe function exactly as prepare_case does.
            finding, provenance = bind_target_line(finding, recipe, text)
            if provenance is LineProvenance.RECIPE_FUNCTION:
                entry.notes.append(
                    f"target line {finding.line} derived from recipe function {recipe.function} "
                    f"(line_provenance {provenance.value})"
                )
        failure = target_binding(finding, recipe, text)
        if failure is None:
            entry.passed("target_binding")
            return
        accepted = oracle is not None and (
            score(blocked_result(request, str(failure)), oracle)["status"] == "pass"
        )
        if accepted:
            entry.passed("target_binding")
            entry.notes.append(f"{failure}; the oracle accepts the resulting UNABLE_TO_RUN stop")
            return
        entry.fail("target_binding", f"{failure}; the case stops UNABLE_TO_RUN before any model")


def _entry_name(raw: object, index: int) -> str:
    case_id = raw.get("case_id") if isinstance(raw, dict) else None
    return case_id if isinstance(case_id, str) and case_id else f"#{index + 1}"


def _raw_entries(report: DatasetReport, document: dict[str, Any]) -> list[Any]:
    entries = document.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        report.problems.append(f"entries must be a list of 1..{MAX_ENTRIES} entries")
        return []
    return entries


def _unique(entry: EntryReport, seen: set[str]) -> None:
    if entry.case_id in seen:
        entry.fail("entry", f"duplicate case_id {entry.case_id}")
    seen.add(entry.case_id)


def _validate_case_dataset(
    report: DatasetReport, document: dict[str, Any], validator: _Validator
) -> None:
    report.kind = "case"
    family_splits: dict[str, str] = {}
    seen: set[str] = set()
    for index, raw in enumerate(_raw_entries(report, document)):
        entry = EntryReport(index=index, case_id=_entry_name(raw, index), kind="case")
        report.entries.append(entry)
        try:
            declared = DatasetEntry.model_validate(raw)
        except ValueError as error:
            entry.fail("entry", safe_error_detail(error))
            continue
        entry.family, entry.split = declared.family, declared.split
        _unique(entry, seen)
        for name, value in (("family", declared.family), ("split", declared.split)):
            if not _GROUP_NAME.fullmatch(value):
                entry.fail("entry", f"{name} {value!r} is not a lowercase identifier")
        if family_splits.setdefault(declared.family, declared.split) != declared.split:
            entry.fail(
                "entry",
                f"family {declared.family} crosses splits "
                f"{family_splits[declared.family]} and {declared.split}",
            )
        entry.passed("entry")
        request_bytes = validator.read(entry, "request", declared.request, declared.request_digest)
        oracle_bytes = validator.read(entry, "oracle", declared.oracle, declared.oracle_digest)
        oracle = None
        if oracle_bytes is not None:
            try:
                oracle = Oracle.model_validate_json(oracle_bytes)
            except ValueError as error:
                entry.fail("oracle", safe_error_detail(error))
            else:
                for problem in case_oracle_problems(oracle):
                    entry.fail("oracle", problem)
                entry.passed("oracle")
        if request_bytes is not None:
            request = validator.request(entry, declared.request, request_bytes)
            if request is not None:
                if oracle is not None:
                    scope = request.case.finding.claim_scope
                    for problem in claim_scope_problems(scope, oracle):
                        entry.fail("oracle", problem)
                    for problem in negative_label_problems(request.case.recipe.kind, oracle):
                        entry.fail("oracle", problem)
                validator.binding(entry, request, oracle)
    try:
        report.dataset_digest = digest(Dataset.model_validate(document))
    except ValueError as error:
        report.problems.append(f"manifest: {safe_error_detail(error)}")


def _validate_agent_entry(
    entry: EntryReport, raw: dict[str, Any], validator: _Validator
) -> str | None:
    """Check one isolated-agent entry; return its role, inferred from the input shape."""
    input_bytes = validator.read(entry, "input", raw["input"], raw["input_digest"])
    oracle_bytes = validator.read(entry, "oracle", raw["oracle"], raw["oracle_digest"])
    kind = None
    if input_bytes is not None:
        try:
            document = json.loads(input_bytes)
        except ValueError as error:
            entry.fail("request", safe_text(error))
            document = None
        if isinstance(document, dict) and "case" in document:
            kind = "producer"
            request = validator.request(entry, raw["input"], input_bytes)
            if request is not None:
                validator.binding(entry, request, None)
        elif document is not None:
            kind = "auditor"
            try:
                AuditInput.model_validate(document)
            except ValueError as error:
                entry.fail("request", safe_error_detail(error))
            entry.passed("request")
    entry.kind = kind or "unknown"
    if oracle_bytes is not None:
        try:
            oracle = json.loads(oracle_bytes)
        except ValueError as error:
            entry.fail("oracle", safe_text(error))
            return kind
        if not isinstance(oracle, dict):
            entry.fail("oracle", "isolated oracle must be a JSON object")
            return kind
        if kind is None:
            return kind  # Without a readable input the oracle's role is unknown.
        checks = auditor_oracle_problems if kind == "auditor" else producer_oracle_problems
        for problem in checks(oracle):
            entry.fail("oracle", problem)
        entry.passed("oracle")
    return kind


def _validate_agent_dataset(
    report: DatasetReport, document: dict[str, Any], validator: _Validator
) -> None:
    kinds: set[str] = set()
    seen: set[str] = set()
    for index, raw in enumerate(_raw_entries(report, document)):
        entry = EntryReport(index=index, case_id=_entry_name(raw, index), kind="unknown")
        report.entries.append(entry)
        missing = (
            [name for name in _AGENT_FIELDS if not isinstance(raw.get(name), str)]
            if isinstance(raw, dict)
            else list(_AGENT_FIELDS)
        )
        if missing:
            entry.fail("entry", f"missing or non-string fields: {', '.join(missing)}")
            continue
        _unique(entry, seen)
        entry.passed("entry")
        kind = _validate_agent_entry(entry, raw, validator)
        if kind is not None:
            kinds.add(kind)
    if len(kinds) > 1:
        report.problems.append("an isolated dataset mixes producer and auditor entries")
    report.kind = kinds.pop() if len(kinds) == 1 else "agent"
    report.dataset_digest = digest(document)


def _validate_intake_entry(
    entry: EntryReport, declared: intake.IntakeDatasetEntry, validator: _Validator
) -> None:
    """Digests, report envelope, template, source snapshot and oracle length of one row."""
    report_bytes = validator.read(entry, "report", declared.report, declared.report_digest)
    oracle_bytes = validator.read(entry, "oracle", declared.oracle, declared.oracle_digest)
    findings: list[object] | None = None
    if report_bytes is not None:
        try:
            findings = intake.report_findings(report_bytes)
        except ValueError as error:
            entry.fail("request", safe_error_detail(error))
        else:
            entry.passed("request")
    if declared.recipe_template is not None:
        if declared.recipe_template_digest is None:
            entry.fail("entry", "recipe_template needs recipe_template_digest")
        elif validator.read(
            entry, "recipe_template", declared.recipe_template, declared.recipe_template_digest
        ):
            try:
                load_recipe_template(resolve_frozen(validator.root, declared.recipe_template))
            except ValueError as error:
                entry.fail("request", f"recipe template: {safe_error_detail(error)}")
    try:
        source_dir = resolve_frozen(validator.root, declared.source)
    except ValueError as error:
        entry.fail("source", safe_text(error))
    else:
        source = Source(path=str(source_dir), expected_digest=declared.source_digest)
        if validator.snapshot(entry, "source", source) is not None:
            entry.passed("source")
    if oracle_bytes is not None:
        try:
            expected = intake.IntakeOracle.model_validate_json(oracle_bytes).expected
        except ValueError as error:
            entry.fail("oracle", safe_error_detail(error))
        else:
            if findings is not None and len(expected) != len(findings):
                entry.fail("oracle", f"lists {len(expected)} outcomes for {len(findings)} findings")
            entry.passed("oracle")


def _validate_intake_dataset(
    report: DatasetReport, document: dict[str, Any], validator: _Validator
) -> None:
    report.kind = "intake"
    seen: set[str] = set()
    for index, raw in enumerate(_raw_entries(report, document)):
        entry = EntryReport(index=index, case_id=_entry_name(raw, index), kind="intake")
        report.entries.append(entry)
        try:
            declared = intake.IntakeDatasetEntry.model_validate(raw)
        except ValueError as error:
            entry.fail("entry", safe_error_detail(error))
            continue
        _unique(entry, seen)
        entry.passed("entry")
        _validate_intake_entry(entry, declared, validator)
    try:
        report.dataset_digest = digest(intake.IntakeDataset.model_validate(document))
    except ValueError as error:
        report.problems.append(f"manifest: {safe_error_detail(error)}")


def _validate_intake_agent_dataset(
    report: DatasetReport, document: dict[str, Any], validator: _Validator
) -> None:
    from corsair.contracts.intake_agent import ImageInventory, IntakeRequest
    from corsair.evaluation.intake_agent import IntakeAgentDataset, IntakeOracle

    report.kind = "intake_agent"
    try:
        manifest = IntakeAgentDataset.model_validate(document)
    except ValueError as error:
        report.problems.append(f"manifest: {safe_error_detail(error)}")
        return
    report.dataset_digest = digest(document)
    for index, declared in enumerate(manifest.entries):
        entry = EntryReport(
            index=index, case_id=declared.case_id, kind="intake_agent", family=declared.family
        )
        report.entries.append(entry)
        entry.passed("entry")
        source = validator.read(entry, "input", declared.input, declared.input_digest)
        oracle = validator.read(entry, "oracle", declared.oracle, declared.oracle_digest)
        if oracle is not None:
            try:
                IntakeOracle.model_validate_json(oracle)
                entry.passed("oracle")
            except ValueError as error:
                entry.fail("oracle", safe_error_detail(error))
        if source is None:
            continue
        try:
            fixture = json.loads(source)
            request = IntakeRequest.model_validate(fixture["request"])
            ImageInventory.model_validate(fixture["inventory"])
            entry.passed("request")
            path = resolve_frozen(validator.root, declared.input).parent / request.source.path
            admitted = request.source.model_copy(
                update={"path": str(path), "expected_digest": fixture["source_digest"]}
            )
            if validator.snapshot(entry, "source", admitted) is not None:
                entry.passed("source")
        except (ValueError, KeyError, TypeError) as error:
            entry.fail("request", safe_error_detail(error))


def _check_loader(report: DatasetReport, document: dict[str, Any], root: Path) -> None:
    """Run the consuming evaluator's own loader, so its rules cannot drift from these checks."""
    try:
        if report.schema_version == CASE_SCHEMA:
            load_dataset(report.path)
        elif report.schema_version == "corsair.intake-agent-dataset/1":
            from corsair.evaluation.intake_agent import load_frozen_cases

            load_frozen_cases(report.path)
        elif report.schema_version == intake.INTAKE_SCHEMA:
            intake.score_dataset(report.path)
        else:
            for raw in document["entries"]:
                load_frozen_fixture(root, raw)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report.loader = "fail"
        # An entry failure already explains the refusal; report only a loader rule they missed.
        if all(entry.valid for entry in report.entries):
            report.problems.append(f"loader: {safe_error_detail(error)}")
    else:
        report.loader = "pass"


def validate_dataset(path: Path, settings: Settings | None = None) -> DatasetReport:
    """Validate one manifest. ``settings`` defaults to admitting sources below its root."""
    report = DatasetReport(path=path)
    try:
        document = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        report.problems.append(f"cannot read dataset: {safe_text(error)}")
        return report
    if not isinstance(document, dict):
        report.problems.append("a dataset must be a JSON object")
        return report
    schema = document.get("schema_version")
    report.schema_version = schema if isinstance(schema, str) else None
    if schema not in {
        CASE_SCHEMA,
        AGENT_SCHEMA,
        intake.INTAKE_SCHEMA,
        "corsair.intake-agent-dataset/1",
    }:
        found = "no schema_version" if schema is None else f"schema_version {safe_text(schema)!r}"
        report.problems.append(
            f"not an evaluation dataset manifest ({found}); expected {CASE_SCHEMA}, "
            f"{AGENT_SCHEMA} or {intake.INTAKE_SCHEMA}"
        )
        return report
    root = dataset_root(path)
    admission = settings or Settings(source_root=str(root))
    with tempfile.TemporaryDirectory(prefix="corsair-dataset-") as scratch:
        validator = _Validator(root, admission, ArtifactStore(scratch))
        if schema == CASE_SCHEMA:
            _validate_case_dataset(report, document, validator)
        elif schema == "corsair.intake-agent-dataset/1":
            _validate_intake_agent_dataset(report, document, validator)
        elif schema == intake.INTAKE_SCHEMA:
            _validate_intake_dataset(report, document, validator)
        else:
            _validate_agent_dataset(report, document, validator)
    if report.entries:
        _check_loader(report, document, root)
    return report


def fix_digests(report: DatasetReport) -> list[dict[str, Any]]:
    """Rewrite only stale manifest digests; never a request, input, oracle or other field.

    A digest is a statement that the referenced bytes are the reviewed ones, so an entry
    whose files fail any other check is reported and left unchanged.
    """
    document = json.loads(report.path.read_bytes())
    changes: list[dict[str, Any]] = []
    for entry in report.entries:
        if entry.checks["digests"] != "fail":
            continue
        applied = entry.only_digests_stale
        for name, declared in entry.declared.items():
            actual = entry.actual[name]
            if actual == declared:
                continue
            if applied:
                document["entries"][entry.index][f"{name}_digest"] = actual
            changes.append(
                {
                    "case_id": entry.case_id,
                    "field": f"{name}_digest",
                    "old": declared,
                    "new": actual,
                    "applied": applied,
                }
            )
    if any(change["applied"] for change in changes):
        temporary = report.path.with_name(f".{report.path.name}.tmp")
        temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, report.path)
    return changes


def _cross_dataset_problems(reports: list[DatasetReport]) -> list[str]:
    """A family assigned to different splits in two manifests leaks across cohorts."""
    placements: dict[str, set[tuple[str, str]]] = {}
    for report in reports:
        for entry in report.entries:
            if entry.family is not None and entry.split is not None:
                placements.setdefault(entry.family, set()).add((entry.split, str(report.path)))
    problems = []
    for family, placed in sorted(placements.items()):
        splits = sorted({split for split, _ in placed})
        if len(splits) > 1:
            problems.append(f"family {family} crosses splits {', '.join(splits)} across datasets")
    return problems


def validate_datasets(
    paths: list[Path], settings: Settings | None = None, *, fix: bool = False
) -> dict[str, Any]:
    """Validate manifests; with ``fix`` (``dataset refreeze``), rewrite stale digests, then
    report the new state. ``rewritten`` is true whenever a manifest was written: the dataset
    digest changed, so the result is a new frozen cohort to review, never a plain pass."""
    reports = [validate_dataset(path, settings) for path in paths]
    if fix:
        for index, report in enumerate(reports):
            changes = fix_digests(report) if report.entries else []
            if any(change["applied"] for change in changes):
                stale_digest = report.dataset_digest
                report = reports[index] = validate_dataset(report.path, settings)
                report.dataset_digest_change = {"old": stale_digest, "new": report.dataset_digest}
            report.digest_changes = changes
    problems = _cross_dataset_problems(reports)
    return {
        "datasets": [report.as_dict() for report in reports],
        "problems": problems,
        "valid": not problems and all(report.valid for report in reports),
        "rewritten": any(report.dataset_digest_change is not None for report in reports),
    }
