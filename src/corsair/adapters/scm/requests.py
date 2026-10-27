"""Request shaping before local source admission: source anchoring, scanner and chain intake."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel, TypeAdapter, ValidationError

from corsair.contracts import (
    Budget,
    Case,
    Finding,
    InvestigationRequest,
    Recipe,
    ScannerClaim,
    ScannerFinding,
    Scope,
    Source,
)

# A recipe template is one ``Recipe`` union member without the fields intake binds per
# finding (always ``module_file``). Up-front validation uses this placeholder module; a
# member whose module suffix differs is validated completely when it is bound.
_TEMPLATE_MODULE = "template.py"
_DEFAULT_KIND = "python.secret_disclosure/1"
# The field naming a recipe's callable: ``method`` for Java, ``function`` elsewhere.
CALLABLE_FIELDS = ("function", "method")
_RECIPE = TypeAdapter[Any](Recipe)


def _recipe_members() -> dict[str, type[BaseModel]]:
    """Each admitted recipe kind and its contract, read from the ``Recipe`` union itself."""
    union = get_args(Recipe)[0]
    members: dict[str, type[BaseModel]] = {}
    for option in get_args(union):
        model = get_args(option)[0]
        members[model.model_fields["kind"].default] = model
    return members


RECIPE_MEMBERS = _recipe_members()


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


def recipe_member(template: Mapping[str, object]) -> type[BaseModel]:
    """The union member a template's ``kind`` names; a kind outside the union is refused.

    A template without ``kind`` is the original Python secret-disclosure recipe, as for a
    request. No kind is invented here: a new kind needs its own contract, observer and
    human-authored auditor rubric first.
    """
    kind = template.get("kind", _DEFAULT_KIND)
    member = RECIPE_MEMBERS.get(kind) if isinstance(kind, str) else None
    if member is None:
        raise ValueError(
            f"recipe kind {kind!r} is not an admitted Recipe kind; "
            f"admitted: {', '.join(sorted(RECIPE_MEMBERS))}"
        )
    return member


def callable_field(member: type[BaseModel]) -> str:
    """The field of ``member`` that names the bound callable."""
    return next(name for name in CALLABLE_FIELDS if name in member.model_fields)


def load_recipe_template(
    path: Path, *, bound: Sequence[str] = ("module_file",)
) -> dict[str, object]:
    """Read one operator-owned recipe template: a ``Recipe`` member without its bound fields.

    ``bound`` names the fields intake binds per finding (``module_file`` always; chain
    drafting also binds the callable). The template may not set them. Every other field is
    validated up front against the kind's contract, so a malformed template fails the
    command rather than blocking every finding with the same reason.
    """
    template = json.loads(path.read_bytes())
    if not isinstance(template, dict):
        raise ValueError("a recipe template must be a JSON object")
    for name in bound:
        if name in template:
            raise ValueError(
                f"a recipe template may not set {name}; intake binds it to each finding"
            )
    member = recipe_member(template)
    try:
        member.model_validate({**template, "module_file": _TEMPLATE_MODULE})
    except ValidationError as error:
        fields = sorted(
            {
                ".".join(str(part) for part in item["loc"])
                for item in error.errors()
                if item["loc"][:1] != ("module_file",)
                and not (item["type"] == "missing" and item["loc"][0] in bound)
            }
        )
        if fields:
            raise ValueError(f"invalid recipe template field(s): {fields}") from None
    return template


def recipe_from_template(
    recipe_template: Mapping[str, object], *, module_file: str, function: str | None = None
) -> Recipe:
    """Bind a template to one module (and, when given, one callable) as a ``Recipe``."""
    values = {**recipe_template, "module_file": module_file}
    if function is not None:
        values[callable_field(recipe_member(recipe_template))] = function
    return _RECIPE.validate_python(values)


def request_from_template(
    finding: Finding,
    *,
    case_id: str,
    source: Source,
    recipe_template: Mapping[str, object],
    function: str | None = None,
    fixed_source: Source | None = None,
    budget: Budget | None = None,
) -> InvestigationRequest:
    """Assemble one candidate request: the operator's recipe bound to the finding's file.

    The recipe comes only from the template, with ``module_file`` set to the finding's
    file (the binding ``Case`` requires) and, when ``function`` is given, the kind's
    callable field set to it. Nothing is read from finding narrative.
    """
    recipe = recipe_from_template(recipe_template, module_file=finding.file, function=function)
    case = Case(
        case_id=case_id, finding=finding, source=source, recipe=recipe, fixed_source=fixed_source
    )
    return InvestigationRequest(case=case, budget=budget or Budget())


def request_from_scanner(
    scanner_finding: ScannerFinding,
    *,
    case_id: str,
    source: Source,
    recipe_template: Mapping[str, object],
) -> InvestigationRequest:
    """Bind an operator recipe template to one scanner finding: a candidate request.

    Nothing is read from the finding's description or any other scanner narrative, and
    no line is invented: a line-less finding stays line-less here and prepare binds it
    from the recipe.
    """
    return request_from_template(
        finding_from_scanner(scanner_finding),
        case_id=case_id,
        source=source,
        recipe_template=recipe_template,
    )
