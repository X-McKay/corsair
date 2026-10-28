"""V3 execution proposals remain bounded data, never security observations."""

import pytest
from pydantic import ValidationError

from corsair.contracts.execution import Command, ExecutionResult
from corsair.contracts.execution import TestFile as PlanFile
from tests.unit.execution import plan


@pytest.mark.parametrize("path", ["/tmp/a", "../a", "a/../b", "a//b", "a\\b"])
def test_test_file_path_is_confined(path):
    with pytest.raises(ValidationError):
        PlanFile(path=path, content="x")


def test_plan_has_byte_and_argv_limits():
    with pytest.raises(ValidationError):
        PlanFile(path="x", content="é" * 17000)
    with pytest.raises(ValidationError):
        Command(argv=["x"] * 65)
    with pytest.raises(ValidationError):
        Command(argv=["x\x00"])
    with pytest.raises(ValidationError):
        plan(files=[{"path": str(n), "content": "x" * 32768} for n in range(5)])
    with pytest.raises(ValidationError):
        plan(files=[{"path": "x", "content": ""}, {"path": "x/y", "content": ""}])
    with pytest.raises(ValidationError):
        plan(commands=[{"argv": ["x" * 20000]}, {"argv": ["y" * 20000]}])


def test_work_directory_is_relative_and_dot_is_allowed():
    assert Command(argv=["true"]).cwd == "."
    with pytest.raises(ValidationError):
        Command(argv=["true"], cwd="/source")


def test_success_cannot_promote_security_assessment():
    result = ExecutionResult(run_id="r1", case_id="case1")
    assert result.security_assessment == "UNRESOLVED"
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(
            dict(run_id="r1", case_id="case1", security_assessment="DEMONSTRATED")
        )
    assert plan().commands[0].expected == "zero"
