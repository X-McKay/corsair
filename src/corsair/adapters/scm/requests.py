"""Request shaping before local source admission: source anchoring and scanner intake."""

import json
from collections.abc import Mapping
from pathlib import Path

from corsair.contracts import (
    Case,
    Finding,
    InvestigationRequest,
    PythonRecipe,
    ScannerClaim,
    ScannerFinding,
    Scope,
    Source,
)

# A recipe template is a PythonRecipe without ``module_file``: intake binds that field
# to each finding's file. Validation uses this placeholder module only.
_TEMPLATE_MODULE = "template.py"


def normalize_request_sources(
    request: InvestigationRequest, request_file: Path
) -> InvestigationRequest:
    """Anchor relative sources at a request file without resolving source symlinks."""

    base = request_file.parent.absolute()

    def anchored(path: str) -> str:
        return path if Path(path).is_absolute() else str((base / path).absolute())

    source = request.case.source.model_copy(update={"path": anchored(request.case.source.path)})
    fixed = request.case.fixed_source
    if fixed is not None:
        fixed = fixed.model_copy(update={"path": anchored(fixed.path)})
    return request.model_copy(
        update={"case": request.case.model_copy(update={"source": source, "fixed_source": fixed})}
    )


def finding_from_scanner(scanner_finding: ScannerFinding) -> Finding:
    """Map one scanner finding onto an internal Finding, conservatively.

    The scanner's severity, confidence, category and narrative are carried on the
    Finding as an untrusted ``ScannerClaim`` purely for reporting; the verdict
    kernel never reads them. The claimed scope is set to APPLICATION so that a
    genuine demonstration against the supplied repositories is capped at
    COMPONENT_EXPLOIT_DEMONSTRATED: driving the real application entry point needs
    an application-entry recipe mechanism that is a known follow-up, so until then
    we never award a silent full-application EXPLOIT_DEMONSTRATED for an
    application claim we cannot run end to end. The supplied repositories are the
    only code the demonstration may run against: a finding whose file is absent
    from the admitted source cannot bind its target line and resolves
    UNABLE_TO_RUN rather than any demonstration or clean negative.
    """

    return Finding(
        title=scanner_finding.title,
        description=scanner_finding.description,
        file=scanner_finding.file,
        line=scanner_finding.line,
        claim_scope=Scope.APPLICATION,
        scanner=ScannerClaim.from_finding(scanner_finding),
    )


def load_recipe_template(path: Path) -> dict[str, object]:
    """Read one operator-owned recipe template: a ``PythonRecipe`` without ``module_file``.

    The template is validated as a complete recipe up front, so a malformed template
    fails the command rather than blocking every finding with the same reason.
    """
    template = json.loads(path.read_bytes())
    if not isinstance(template, dict):
        raise ValueError("a recipe template must be a JSON object")
    if "module_file" in template:
        raise ValueError(
            "a recipe template may not set module_file; intake binds it to each finding's file"
        )
    PythonRecipe.model_validate({**template, "module_file": _TEMPLATE_MODULE})
    return template


def request_from_scanner(
    scanner_finding: ScannerFinding,
    *,
    case_id: str,
    source: Source,
    recipe_template: Mapping[str, object],
) -> InvestigationRequest:
    """Bind an operator recipe template to one scanner finding: a candidate request.

    The recipe comes only from the operator's template, with its ``module_file`` set to
    the finding's file (the binding ``Case`` requires). Nothing is read from the
    finding's description or any other scanner narrative, and no line is invented:
    a line-less finding stays line-less here and prepare binds it from the recipe.
    """
    recipe = PythonRecipe.model_validate({**recipe_template, "module_file": scanner_finding.file})
    case = Case(
        case_id=case_id,
        finding=finding_from_scanner(scanner_finding),
        source=source,
        recipe=recipe,
    )
    return InvestigationRequest(case=case)
