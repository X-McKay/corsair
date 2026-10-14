"""Ownership-safe whole-file writes recorded in the native run history."""
from hashlib import sha256
from typing import Annotated
from pydantic import Field
from pydantic_ai import RunContext
from corsair.agents.test_authoring.contracts import AdmissionFinding, WrittenFile
from corsair.ports.test_runner import MAX_PATCH_FILE_BYTES
from ..contracts import RefusedDraftWrite
from ..dependencies import SpecialistDependencies

async def write_test_file(ctx: RunContext[SpecialistDependencies],
                          path: Annotated[str, Field(description='Your single assigned new test file')],
                          content: Annotated[str, Field(description='Complete proposed native test file content')]) -> WrittenFile | RefusedDraftWrite:
    """Propose a complete own file; admit only ownership and size, never semantic or runtime validity."""
    reason = None
    if path != ctx.deps.inputs.test_path:
        reason = 'Path is not the single operator-owned specialist file'
    elif len(content.encode()) > MAX_PATCH_FILE_BYTES:
        reason = 'File exceeds the admitted byte limit'
    if reason:
        return RefusedDraftWrite(path=path[:256], reason=reason,
                                 findings=(AdmissionFinding(line=1, facility='role_boundary'),))
    data = content.encode()
    return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))
