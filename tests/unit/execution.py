"""Synthetic v3 inputs shared by unit tests; no target execution."""

from corsair.contracts import ArtifactRef, Source, digest
from corsair.contracts.execution import (
    ExecutionRequest,
    ExecutionRoundInput,
    PreparedExecution,
)
from corsair.contracts.execution import (
    TestPlan as Plan,
)
from corsair.contracts.intake import AvailableImage, Issue
from corsair.settings import Settings


class Reader:
    def read(self, operation, relative=""):
        assert relative in ("", "reader.py", "unread.py")
        return (
            {"files": ["reader.py"]}
            if operation == "list"
            else {"content": "def answer(): return 42"}
        )


def round_input():
    settings = Settings()
    request = ExecutionRequest(
        case_id="example",
        issue=Issue(title="Inspect answer"),
        source=Source(path="repository"),
        image=AvailableImage(
            reference=settings.image,
            image_id="sha256:" + "1" * 64,
            language="python",
            execution_mode="callable",
        ),
    )
    prepared = PreparedExecution(
        run_id="test",
        request=request,
        source=ArtifactRef(sha256="2" * 64, size=0),
        config_digest=settings.identity,
        request_digest=digest(request),
        resources_digest="3" * 64,
    )
    return ExecutionRoundInput(
        prepared=prepared, revision=1, llm_limit=2, tool_limit=12, seconds=30
    )


def plan(**updates):
    return Plan.model_validate(
        {
            "hypothesis": "Inspect the reported path handling",
            "revision": 1,
            "files": [{"path": "test.py", "content": "print(1)"}],
            "commands": [{"argv": ["python", "/work/test.py"]}],
            "locations": [{"path": "reader.py"}],
            **updates,
        }
    )
