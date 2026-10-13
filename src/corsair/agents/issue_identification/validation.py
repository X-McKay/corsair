"""Trusted output functions: admit a draft only against source this run actually read."""

import re
import unicodedata

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from ..source.contracts import SourceRead
from ..source.repository_tools import run_source_reads
from ..source.tools import READ_SOURCE_TOOL
from .contracts import IssueIdentification, IssueIdentificationDraft
from .dependencies import FixtureDependencies, IdentificationDependencies, RepositoryDependencies


def _symbol_occurs(symbol: str, text: str) -> bool:
    """Literal occurrence with conservative Python/Java/JS identifier boundaries."""
    def continuation(char: str) -> bool:
        return ("_" + char).isidentifier() or unicodedata.category(char) in {"Sc", "Cf"}

    return any((match.start() == 0 or not continuation(text[match.start() - 1]))
               and (match.end() == len(text) or not continuation(text[match.end()]))
               for match in re.finditer(re.escape(symbol), text))


def finalize_draft(deps: IdentificationDependencies, draft: IssueIdentificationDraft,
                   reads: list[SourceRead]) -> IssueIdentification:
    """Shared by inline and repository modes: scope, run-local read coverage, symbol and quotation."""
    if draft.scope != deps.inputs.scope:
        raise ModelRetry("identification scope must equal the authorized input scope")
    if draft.status != "ready":
        return IssueIdentification.model_validate(draft.model_dump() | {"reported_issue": deps.inputs.issue})
    reference = draft.target.source
    if not any(read.path == reference.path and read.start_line <= reference.start_line
               and reference.end_line <= read.end_line for read in reads):
        raise ModelRetry("target source must be fully covered by a successful read_source in this run")
    try:
        source = deps.read_source(reference.path, reference.start_line, reference.end_line)
    except ValueError as exc:
        raise ModelRetry(str(exc)) from exc
    # Literal escaped matching is only an occurrence check, not a language parser.
    if not _symbol_occurs(draft.target.symbol, source.quote):
        raise ModelRetry("exact target symbol must occur without identifier prefixes or suffixes in the selected source excerpt")
    return IssueIdentification.model_validate(draft.model_dump() | {
        "reported_issue": deps.inputs.issue,
        "target": {"symbol": draft.target.symbol, "source": source.model_dump()},
    })


async def finalize_identification(ctx: RunContext[FixtureDependencies],
                                  draft: IssueIdentificationDraft) -> IssueIdentification:
    reads = [SourceRead.model_validate(part.content)
             for message in ctx.messages if isinstance(message, ModelRequest) and message.run_id == ctx.run_id
             for part in message.parts if isinstance(part, ToolReturnPart)
             and part.tool_name == READ_SOURCE_TOOL and part.outcome == "success"]
    return finalize_draft(ctx.deps, draft, reads)


async def finalize_repository_identification(ctx: RunContext[RepositoryDependencies],
                                             draft: IssueIdentificationDraft) -> IssueIdentification:
    return finalize_draft(ctx.deps, draft, run_source_reads(ctx))
