"""Scanner-finding intake: parsing, conservative mapping, and the hard guarantee
that a scanner's self-assessment can never move a verdict."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.contracts import (
    FixStatus,
    Repository,
    ScannerFinding,
    ScannerScope,
    Scope,
    Verdict,
)
from corsair.entrypoints.requests import finding_from_scanner, load_scan_report
from corsair.policies.verdicts import session_verdict
from tests.unit.test_evidence import _audit, _prepared
from tests.unit.test_verdicts import _demonstrated

FIXTURES = Path(__file__).resolve().parents[2] / "evals/fixtures/scan_reports"


def _scanner_finding(**overrides) -> ScannerFinding:
    base = ScannerFinding(
        title="Caller path joins the configured root without containment",
        description="The reported callable joins a caller-controlled path onto the root.",
        file="reader.py",
        line=4,
        category="Path traversal",
        severity="LOW",
        confidence=0.1,
        preconditions=["The caller controls the path argument."],
        scope=ScannerScope(
            application="Reporting service file export",
            repositories=[Repository(name="svc", url="https://example.invalid/svc")],
        ),
    )
    return base.model_copy(update=overrides) if overrides else base


@pytest.mark.parametrize(
    "name",
    [
        "library-template-injection.json",
        "preview-server-path-traversal.json",
        "python-reader-no-line.json",
    ],
)
def test_example_scan_reports_parse(name):
    report = load_scan_report(FIXTURES / name)
    assert report.scan_completed and report.vulnerabilities_found
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.scope.repositories  # the supplied-repos bound is present
    assert 0.0 <= finding.confidence <= 1.0


def test_mapping_carries_the_untrusted_claim_and_caps_the_scope():
    scanner_finding = _scanner_finding(severity="HIGH", confidence=0.95)
    finding = finding_from_scanner(scanner_finding)
    assert finding.title == scanner_finding.title
    assert finding.file == scanner_finding.file
    assert finding.line == scanner_finding.line
    # Conservative ceiling: a scanner claim maps to APPLICATION scope so a genuine
    # differential is capped at COMPONENT_EXPLOIT_DEMONSTRATED, never a silent full
    # application EXPLOIT_DEMONSTRATED we cannot run end to end.
    assert finding.claim_scope is Scope.APPLICATION
    # The self-assessment is carried verbatim for reporting only.
    assert finding.scanner is not None
    assert finding.scanner.severity == "HIGH"
    assert finding.scanner.confidence == 0.95
    assert finding.scanner.application == scanner_finding.scope.application
    assert finding.scanner.repositories == scanner_finding.scope.repositories


def _verdict_for(scanner_finding: ScannerFinding) -> Verdict:
    finding = finding_from_scanner(scanner_finding)
    prepared = _prepared().model_copy(update={"finding": finding})
    return session_verdict(prepared, _demonstrated(), _audit(), FixStatus.NOT_REQUESTED).verdict


def test_scanner_self_assessment_never_moves_the_verdict():
    """Severity and confidence are carried but the kernel never reads them: a
    maximal-severity, maximal-confidence finding and a minimal one with the same
    demonstrated evidence resolve to the exact same code-decided label, and that
    label is the component ceiling, never the full EXPLOIT_DEMONSTRATED."""
    loud = _verdict_for(_scanner_finding(severity="CRITICAL", confidence=1.0))
    quiet = _verdict_for(_scanner_finding(severity="INFO", confidence=0.0))
    assert loud is quiet is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED
    assert loud is not Verdict.EXPLOIT_DEMONSTRATED


def test_scope_requires_at_least_one_supplied_repository():
    """The supplied repositories bound the demonstrable code; a finding that names
    none cannot be admitted, so the scope contract rejects an empty repository set."""
    with pytest.raises(ValidationError):
        ScannerScope(application="svc", repositories=[])


def test_a_finding_without_a_scope_defaults_to_application():
    """The conservative default: an unspecified scope is application, so a
    demonstration caps at COMPONENT_EXPLOIT_DEMONSTRATED unless the finding
    explicitly claims component scope. Scanner findings, which omit a provable
    scope, inherit this (Al 2026-10-26)."""
    from corsair.contracts import Finding

    scopeless = Finding(title="t", description="d", file="x.py", line=4)
    assert scopeless.claim_scope is Scope.APPLICATION
    explicit = Finding(title="t", description="d", file="x.py", claim_scope=Scope.COMPONENT)
    assert explicit.claim_scope is Scope.COMPONENT


def test_unusual_severity_strings_are_carried_not_rejected():
    """Severity is untrusted producer text, read only for reporting, so an
    unexpected value is preserved rather than rejected (it cannot affect a verdict)."""
    finding = finding_from_scanner(_scanner_finding(severity="SEV-0 (vendor custom)"))
    assert finding.scanner is not None
    assert finding.scanner.severity == "SEV-0 (vendor custom)"


def test_a_line_less_scanner_finding_round_trips_to_a_derived_target_line(tmp_path):
    """A scanner that names the function but no line: intake keeps the line absent,
    and trusted prepare code binds it to the recipe function, recording that."""
    from corsair.adapters.scm.local import prepare_case
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import Case, LineProvenance, PythonRecipe, Source
    from corsair.policies.target_binding import target_binding
    from corsair.settings import Settings

    [scanner_finding] = load_scan_report(FIXTURES / "python-reader-no-line.json").findings
    assert scanner_finding.line is None
    finding = finding_from_scanner(scanner_finding)
    assert finding.line is None  # intake never invents a line
    module = (
        "from pathlib import Path\n\n\n"
        "def read_file(root, path):\n"
        '    """Read one file under root."""\n'
        "    return (Path(root) / path).read_text()\n"
    )
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "reader.py").write_text(module, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    recipe = PythonRecipe(
        module_file="reader.py",
        function="read_file",
        payload_parameter="path",
        fixed_kwargs={"root": "/fixtures/allowed"},
    )
    case = Case(case_id="scan", finding=finding, source=Source(path="project"), recipe=recipe)

    prepared = prepare_case(case, settings, ArtifactStore(settings.artifact_root), _manifest())

    assert prepared.finding.line == 6
    assert prepared.line_provenance is LineProvenance.RECIPE_FUNCTION
    assert prepared.finding.scanner == finding.scanner
    assert target_binding(prepared.finding, recipe, module) is None
    # The derived line is the same exact-line target the verdict gates bind to.
    assert _verdict_for_prepared(prepared) is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED


def _manifest():
    return _prepared().manifest


def _verdict_for_prepared(prepared) -> Verdict:
    evidence = _demonstrated()
    covered = [prepared.finding.line]
    assert evidence.control is not None and evidence.adversarial is not None
    evidence = evidence.model_copy(
        update={
            "source_digest": prepared.source.sha256,
            "control": evidence.control.model_copy(update={"covered_lines": covered}),
            "adversarial": evidence.adversarial.model_copy(update={"covered_lines": covered}),
        }
    )
    return session_verdict(prepared, evidence, _audit(), FixStatus.NOT_REQUESTED).verdict
