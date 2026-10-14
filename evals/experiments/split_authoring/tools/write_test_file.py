"""Whole-file draft writes confined to the operator-owned role paths."""

from hashlib import sha256
from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from corsair.agents.test_authoring.contracts import AdmissionFinding, WrittenFile
from ..contracts import RefusedDraftWrite
from corsair.ports.test_runner import MAX_PATCH_FILE_BYTES
from ..dependencies import DraftingDependencies


async def write_test_file(ctx: RunContext[DraftingDependencies],
                          path: Annotated[str, Field(description="One of your role-owned approved test paths")],
                          content: Annotated[str, Field(description="Complete file content; replaces your previous admitted write")]) -> WrittenFile | RefusedDraftWrite:
    """Propose a complete role-owned test file; application source and frozen control are never writable.

    Refusal preserves the previous owned-file write. Acceptance establishes path and size only;
    semantic/runtime admission, independent pair review and native execution remain separate."""
    reason = None
    if not ctx.deps.inputs.layout_supported:
        reason = "This pilot requires separate role files; the shared-file layout is unsupported"
    elif path not in ctx.deps.inputs.owned_paths:
        reason = "Path is not owned by this role; production source and the frozen other role are read-only"
    elif len(content.encode()) > MAX_PATCH_FILE_BYTES:
        reason = "File exceeds the admitted byte limit"
    if reason is not None:
        return RefusedDraftWrite(status="refused", path=path[:256], reason=reason,
                            findings=(AdmissionFinding(line=1, facility="role_boundary"),))
    data = content.encode()
    return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))
