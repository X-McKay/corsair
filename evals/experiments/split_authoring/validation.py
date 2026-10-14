"""Bind proposed draft outputs to this invocation's admitted writes and immutable seed."""

from hashlib import sha256
from pydantic_ai import ModelRetry, RunContext

from corsair.agents.test_authoring.contracts import PatchedFile
from corsair.agents.test_authoring.tools._history import current_files
from .contracts import Blocked, DraftOutput, Drafted
from .dependencies import DraftingDependencies


async def finalize_draft(ctx: RunContext[DraftingDependencies], draft: DraftOutput) -> Drafted | Blocked:
    inputs = ctx.deps.inputs
    files = tuple(PatchedFile(path=path, content=content) for path, content in sorted(current_files(ctx).items()))
    if not inputs.layout_supported:
        return Blocked(status="blocked", role=inputs.role, layer="layout",
                       reason="This pilot requires separate control and exploit files", files=files)
    if draft.status == "blocked":
        return Blocked(**draft.model_dump(), role=inputs.role, files=files)
    if {file.path for file in files} != set(inputs.owned_paths):
        raise ModelRetry("drafted requires an admitted write for every role-owned file; otherwise return blocked")
    seed = inputs.frozen_control[0] if inputs.frozen_control else None
    return Drafted(role=inputs.role, files=files, limitations=draft.limitations,
                   frozen_control_sha256=sha256(seed.content.encode()).hexdigest() if seed else None)
