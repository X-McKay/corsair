"""Bind each proposed output to current-run reads, admitted writes and immutable role input."""
from pydantic_ai import ModelRetry, RunContext
from corsair.agents.source.contracts import SourceRead, SourceExcerpt
from corsair.agents.test_authoring.contracts import PatchedFile
from corsair.agents.test_authoring.tools._history import current_files, _successful
from .contracts import Blocked, ControlInput, Drafted, DraftOutput
from .dependencies import SpecialistDependencies

async def finalize_draft(ctx: RunContext[SpecialistDependencies], draft: DraftOutput) -> Drafted | Blocked:
    inputs = ctx.deps.inputs
    role = 'control' if isinstance(inputs, ControlInput) else 'exploit'
    files = tuple(PatchedFile(path=path, content=content) for path, content in sorted(current_files(ctx).items()))
    if any(file.path != inputs.test_path for file in files):
        raise ModelRetry('Native history contains a file outside specialist ownership')
    reads = []
    for _, returned in _successful(ctx, 'read_source'):
        try:
            read = SourceRead.model_validate(returned.content)
        except ValueError:
            continue
        if read.path in {s.path for s in inputs.source_files}:
            expected = ctx.deps.read_source(read.path, read.start_line, read.end_line)
            if tuple(line.text for line in read.lines) != tuple(expected.quote.splitlines()):
                raise ModelRetry('Source read differs from immutable specialist input')
            reads.append(read)
    anchors = tuple(c for c in inputs.property_plan.citations
        if any(r.path == c.path and r.start_line <= c.start_line and c.end_line <= r.end_line for r in reads))
    if draft.status == 'blocked':
        return Blocked(**draft.model_dump(), role=role, input_digest=inputs.input_digest, files=files, read_anchors=anchors)
    if len(files) != 1:
        raise ModelRetry('drafted requires one admitted own-file write; otherwise return blocked')
    if anchors != inputs.property_plan.citations:
        raise ModelRetry('Read the source covering every supplied property anchor before returning drafted')
    lines = files[0].content.splitlines()
    if len(set(draft.assertion_lines)) != len(draft.assertion_lines):
        raise ModelRetry('Assertion line anchors must be unique')
    if any(line > len(lines) or not lines[line-1].strip() for line in draft.assertion_lines):
        raise ModelRetry('Assertion anchors must name nonempty lines in the admitted own file')
    assertion_lines = tuple(sorted(draft.assertion_lines))
    assertion_anchors = tuple(SourceExcerpt(path=inputs.test_path, start_line=line, end_line=line,
        quote=lines[line-1]) for line in assertion_lines)
    return Drafted(assertion_lines=assertion_lines, assertion_anchors=assertion_anchors, role=role, input_digest=inputs.input_digest, files=files, limitations=draft.limitations, read_anchors=inputs.property_plan.citations)
