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

    Test code that installs audit hooks, monitoring, tracing or profiling, raises audit events, or patches file, process, network or import facilities is refused: the operator witness observes the target, and a refused write leaves the file unchanged."""
    if path not in ctx.deps.inputs.environment.approved_test_paths:
        raise ModelRetry(f"{path} is not an approved test path")
    data = content.encode()
    if len(data) > MAX_PATCH_FILE_BYTES:
        raise ModelRetry(f"test file exceeds {MAX_PATCH_FILE_BYTES} bytes")
    findings = self_observation(content)
    if findings:
        left = max(ctx.deps.budget.admission_refusals - len(refused_writes(ctx)), 0)
        return RefusedWrite(status="refused", path=path, findings=findings[:32], refusals_left=left, reason=(
            "Refused: test code must not observe, forge or replace what the operator witness observes ("
            + "; ".join(f"line {f.line}: {f.facility}" for f in findings[:8]) + "). The operator witness already "
            "records the target's calls, raised exceptions and file opens; remove these constructs and assert only "
            "the planned required behavior. The file keeps its previous content. "
            + ("Another refusal ends this stage blocked." if left else "This stage now ends blocked at admission.")))
    return WrittenFile(path=path, sha256=sha256(data).hexdigest(), size=len(data))
