"""Trusted finalization: admit only the input scope and current-run citations, then attach exact saved-source quotations."""

import re
import unicodedata

from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext

from ..source.contracts import SourceReference
from .contracts import ReadyTestPlan, TestPlan, TestPlanDraft, UnsupportedTestPlan
from .dependencies import PlanningDependencies
from .tools._history import run_reads


def _symbol_occurs(symbol: str, text: str) -> bool:
    """Literal occurrence with conservative Python/Java/JS identifier boundaries."""
    def continuation(char: str) -> bool:
        return ("_" + char).isidentifier() or unicodedata.category(char) in {"Sc", "Cf"}

    return any((match.start() == 0 or not continuation(text[match.start() - 1]))
               and (match.end() == len(text) or not continuation(text[match.end()]))
               for match in re.finditer(re.escape(symbol), text))


async def finalize_plan(ctx: RunContext[PlanningDependencies], plan: TestPlanDraft) -> TestPlan:
    """Admit only the input scope and current-run citations, then attach exact saved-source quotations.

    The discriminated union arrives under one ``plan`` argument, as native output functions wrap non-model parameters.
    """
    draft = plan
    inputs = ctx.deps.inputs
    if draft.scope != inputs.scope:
        raise ModelRetry("plan scope must equal the authorized input scope")
    reads = run_reads(ctx)

    def quoted(reference: SourceReference) -> dict:
        if not any(read.path == reference.path and read.start_line <= reference.start_line
                   and reference.end_line <= read.end_line for read in reads):
            available = ", ".join(f"{read.path}:{read.start_line}-{read.end_line}" for read in reads) or "none"
            raise ModelRetry(
                f"reference {reference.path}:{reference.start_line}-{reference.end_line} must be covered by a "
                f"successful read_source in this run. Available read ranges: {available}."
            )
        try:
            return ctx.deps.read_source(reference.path, reference.start_line, reference.end_line).model_dump()
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    data = draft.model_dump()
    data["citations"] = [quoted(reference) for reference in draft.citations]
    if draft.status == "unsupported":
        # Only a file with at least one line can be read and cited.
        if any(source.content.splitlines() for source in inputs.source_files) and not draft.citations:
            raise ModelRetry("an unsupported plan must cite the saved source read in this run that grounds it")
        return UnsupportedTestPlan.model_validate(data, context=inputs)
    target = inputs.identification.target
    symbol = target.symbol
    for name in ("control", "security"):
        spec = getattr(draft, name)
        if not _symbol_occurs(symbol, spec.implementation_call):
            raise ModelRetry(f"the {name} implementation_call must name the identified target {symbol}")
        # Admit the identified source anchor, not merely any successfully read file.
        # Multiple cited windows may jointly cover a long anchor.
        ranges = sorted((ref.start_line, ref.end_line) for ref in spec.source_references
                        if ref.path == target.source.path)
        cursor = target.source.start_line
        for start, end in ranges:
            if start > cursor:
                break
            cursor = max(cursor, end + 1)
        if cursor <= target.source.end_line:
            raise ModelRetry(f"the {name} source_references must cover the identified target "
                             f"{target.source.path}:{target.source.start_line}-{target.source.end_line}")
        data[name]["source_references"] = [quoted(reference) for reference in spec.source_references]
    try:
        return ReadyTestPlan.model_validate(data, context=inputs)
    except ValidationError as exc:
        raise ModelRetry(str(exc)) from exc
