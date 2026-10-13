"""write_test_file: one complete approved test file into this run's patch, refused when it observes the witness's facilities."""

from hashlib import sha256
from typing import Annotated

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext

from corsair.ports.test_runner import MAX_PATCH_FILE_BYTES

from ..admission import self_observation
from ..contracts import RefusedWrite, WrittenFile
from ..dependencies import AuthoringDependencies
from ._history import WRITE_TOOL, refused_writes

__all__ = ["WRITE_TOOL", "write_test_file"]


async def write_test_file(ctx: RunContext[AuthoringDependencies],
                          path: Annotated[str, Field(description="One of the approved test paths, exactly as given")],
                          content: Annotated[str, Field(description="Complete new file content; replaces any earlier write of this path")]) -> WrittenFile | RefusedWrite:
    """Write one complete test file into the patch. Only approved test paths are accepted; application source and test configuration are never writable.

    Unit observations may use native doubles at existing dependency seams. Interpreter hooks and global file, process, network or import rewrites are refused; witness plans additionally refuse mock facilities. A refused write leaves the file unchanged."""
    if path not in ctx.deps.inputs.environment.approved_test_paths:
        raise ModelRetry(f"{path} is not an approved test path")
    data = content.encode()
    if len(data) > MAX_PATCH_FILE_BYTES:
        raise ModelRetry(f"test file exceeds {MAX_PATCH_FILE_BYTES} bytes")
    findings = self_observation(content, witness_required=ctx.deps.inputs.plan.security.witness is not None)
    if findings:
        left = max(ctx.deps.budget.admission_refusals - len(refused_writes(ctx)), 0)
        return RefusedWrite(status="refused", path=path, findings=findings[:32], refusals_left=left, reason=(
            "Refused: test code violates the planned observation or interpreter boundary ("
            + "; ".join(f"line {f.line}: {f.facility}" for f in findings[:8]) + "). Use the planned observation boundary. "
            "Remove these constructs and assert "
            "the planned required behavior. The file keeps its previous content. "
            + ("Another refusal ends this stage blocked." if left else "This stage now ends blocked at admission.")))
    return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))
