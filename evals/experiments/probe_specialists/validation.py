"""Bind each proposed output to current-run reads, admitted writes and immutable role input."""
from pydantic_ai import ModelRetry, RunContext
from corsair.agents.source.contracts import SourceRead
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
    if draft.status == 'blocked':
        return Blocked(**draft.model_dump(), role=role, input_digest=inputs.input_digest, files=files)
    if len(files) != 1:
        raise ModelRetry('drafted requires one admitted own-file write; otherwise return blocked')
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
    if not all(any(r.path == c.path and r.start_line <= c.start_line and c.end_line <= r.end_line for r in reads)
               for c in inputs.property_plan.citations):
        raise ModelRetry('Read the source covering every supplied property anchor before returning drafted')
    return Drafted(role=role, input_digest=inputs.input_digest, files=files, limitations=draft.limitations)
