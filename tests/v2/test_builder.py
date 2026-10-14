"""Builder: a recipe flows from commands it ran in a native workspace; untried recipes are refused (scripted model).

The workspace is pydantic_ai's LocalWorkspaceBackend over a temporary directory, standing in for the Docker
backend; the commands are host Python so the test is language-neutral and needs no toolchain image.
"""
import asyncio
import sys

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from pydantic_ai.workspaces import LocalWorkspaceBackend, Workspace

from corsair.agents.builder.agent import create_agent, build_agent, render_prompt
from corsair.contracts import (Case, Citation, ExitClass, Finding, ProbeBrief, ProbePlan, Recipe, Revision,
                                  Runtime)
from tests.v2.agent_scripts import INPUT_TOKENS, Script, tool_returns

PY = sys.executable
SETUP = [PY, "-c", "open('.installed', 'w').write('ok')"]
BASELINE = [PY, "-c", "import pathlib, sys; sys.exit(0 if pathlib.Path('.installed').exists() else 1)"]

RUNTIME = Runtime(row_id="row", image="image", framework="demo", skill="no-such-skill",
                  run_template=("runner", "{file}"), exit_codes={0: ExitClass.PASS}, test_dir="tests",
                  evidence="image-only")
CITE = Citation(path="src/lib/core.txt", start_line=1, end_line=1, quote="core")
BRIEF = dict(test_name="test_x", target="lib.core", seam="call", input_description="input",
             property_to_assert="property", citations=(CITE,))
PLAN = ProbePlan(status="planned", target="lib.core", hypothesis="if X then Y", citations=(CITE,),
                 control=ProbeBrief(role="control", test_file="tests/test_c.py", **BRIEF),
                 exploit=ProbeBrief(role="exploit", test_file="tests/test_e.py", **BRIEF))
CASE = Case(case_id="opaque", revision=Revision(source="/unused", tree_sha256="0" * 64),
            finding=Finding(title="Secret finding title", description="secret finding body"))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "core.txt").write_text("core\n")
    (tmp_path / "manifest.txt").write_text("declared: nothing\n")
    return Workspace(LocalWorkspaceBackend(tmp_path))


def recipe(**changes) -> dict:
    return {"setup": [SETUP], "network_during_setup": False, "baseline_test": BASELINE,
            "notes": "setup writes the marker", **changes}


def build(script, workspace):
    return asyncio.run(build_agent(CASE, RUNTIME, PLAN, script.model, workspace=workspace))


def test_recipe_flows_from_commands_run_in_the_workspace(workspace, tmp_path):
    script = Script([("list_directory", {"path": "."}),
                     ("run", {"argv": BASELINE}),
                     ("run", {"argv": SETUP}),
                     ("run", {"argv": BASELINE}),
                     recipe()])
    result, usage = build(script, workspace)
    assert result == Recipe(setup=(tuple(SETUP),), baseline_test=tuple(BASELINE), notes="setup writes the marker")
    returns = tool_returns(script.seen[-1])
    assert "manifest.txt" in returns[0][2]
    assert [r[2]["exit_code"] for r in returns[1:]] == [1, 0, 0]
    assert (tmp_path / ".installed").read_text() == "ok"
    assert (usage.agent, usage.status, usage.requests, usage.tool_calls) == ("builder", "ok", 5, 4)
    assert usage.input_tokens == 5 * INPUT_TOKENS


def test_a_recipe_that_was_not_run_or_did_not_pass_is_refused(workspace):
    other = [PY, "-c", "pass"]
    script = Script([("run", {"argv": BASELINE}),
                     recipe(setup=[other]),
                     ("run", {"argv": SETUP}), ("run", {"argv": other}), ("run", {"argv": BASELINE}),
                     recipe(setup=[SETUP, other])])
    result, usage = build(script, workspace)
    assert result is not None and usage.status == "ok"
    refusal = [r for r in tool_returns(script.seen[-1]) if r[0] == "RetryPromptPart"][0][2]
    assert f"{other} was never run here" in refusal and f"{BASELINE} last exited 1" in refusal


def test_an_unsupported_recipe_twice_yields_none(workspace):
    result, usage = build(Script([recipe(), recipe()]), workspace)
    assert result is None and usage.status == "output_invalid" and usage.requests == 2


def test_run_reports_a_timeout_as_a_result(workspace):
    script = Script([("run", {"argv": [PY, "-c", "import time; time.sleep(10)"], "timeout_s": 1}),
                     ("run", {"argv": []}), recipe(), recipe()])
    build(script, workspace)
    returns = tool_returns(script.seen[-1])
    assert returns[0][2]["timed_out"] is True and returns[0][2]["exit_code"] is None
    assert returns[1][0] == "RetryPromptPart"


def test_prompt_names_the_component_and_not_the_finding():
    prompt = render_prompt(RUNTIME, PLAN)
    assert "lib.core" in prompt and "src/lib/core.txt" in prompt and "tests" in prompt
    assert "secret finding" not in prompt.lower() and "if X then Y" not in prompt
    assert "Component under test: not yet known" in render_prompt(RUNTIME, ProbePlan(status="target_not_found"))


def test_factory_direct_and_durable_construction():
    assert create_agent(TestModel()).name == "builder"
    assert create_agent(TestModel(), durability=TemporalDurability()).name == "builder"
    with pytest.raises(TypeError):
        create_agent("openai:gpt-x")


def test_a_reasoned_refusal_is_a_recipe_with_its_reason_and_no_commands(workspace):
    script = Script([{"blocked": "the declared dependency needs a compiler the image lacks",
                      "setup": [["make"]], "baseline_test": []}])
    result, usage = build(script, workspace)
    assert usage.status == "ok" and result.blocked.startswith("the declared dependency")
    assert (result.setup, result.baseline_test, result.files) == ((), (), ())
