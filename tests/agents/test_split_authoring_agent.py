"""Eval-only role authority and immutable seed; scripted drafts are never executed."""

import asyncio
from hashlib import sha256

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from corsair.agents.source.contracts import SourceExcerpt
from corsair.agents.test_authoring.contracts import PatchedFile
from corsair.ports.test_runner import format_test_id
from evals.experiments.split_authoring import DraftingDependencies, DraftingInput, create_drafting_agent, drafting_prompt
from evals.experiments.split_authoring.tools import TOOLSET_ID, TOOLSET_SHA256, drafting_tools
from evals.test_planning.evaluate import dataset
from evals.test_planning.property_plan import ReadyPropertyPlan, reference_property


@pytest.fixture
def inputs():
    case = dataset("unit-first").cases[0]
    draft = reference_property(case.inputs, case.metadata)
    refs = [SourceExcerpt(**ref, quote="\n".join(next(s for s in case.inputs.source_files if s.path == ref["path"])
            .content.splitlines()[ref["start_line"] - 1:ref["end_line"]])) for ref in draft["citations"]]
    prop = ReadyPropertyPlan[SourceExcerpt].model_validate(draft | {"citations": refs})
    environment = case.inputs.environment.model_copy(update={"approved_test_paths": ("test_control.py", "test_exploit.py")})
    baseline = environment.baseline_test
    return DraftingInput(role="pair", property_plan=prop, source_files=case.inputs.source_files,
        environment=environment, control_test_path="test_control.py", exploit_test_path="test_exploit.py",
        control_test_id=format_test_id(baseline.test_id, "test_control.py", "test_control", baseline_path=baseline.path),
        exploit_test_id=format_test_id(baseline.test_id, "test_exploit.py", "test_exploit", baseline_path=baseline.path))


def run(inputs, actions):
    pending = list(actions)
    seen = []
    def respond(messages, info):
        seen[:] = [part.content for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if pending:
            name, arguments = pending.pop(0)
            return ModelResponse(parts=[ToolCallPart(name, arguments)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"draft": {
            "status": "drafted", "limitations": ["Independent pair review and native execution remain pending"]}})])
    async def invoke():
        with models.override_allow_model_requests(False):
            return await create_drafting_agent(FunctionModel(respond), role=inputs.role).run(
                drafting_prompt(inputs), deps=DraftingDependencies(inputs))
    result = asyncio.run(invoke())
    return result.output, seen


def test_one_factory_offers_only_exact_draft_tools_and_pinned_identity():
    tools = drafting_tools()
    assert tools.id == TOOLSET_ID == "split_authoring_experiment"
    assert list(tools.tools) == ["read_source", "write_test_file"]
    assert all(tool.max_retries == 0 for tool in tools.tools.values())
    assert TOOLSET_SHA256 == "f7464b23f6cff1ac66d7a25c2c7bf3fc28c4c0ebf0fc51debb5dbd7971bdf4c8"


def test_control_cannot_write_production_or_exploit_file(inputs):
    control = inputs.model_copy(update={"role": "control"})
    output, seen = run(control, [("write_test_file", {"path": "documents.py", "content": "changed"}),
                                ("write_test_file", {"path": "test_exploit.py", "content": "changed"}),
                                ("write_test_file", {"path": "test_control.py", "content": "control draft"})])
    assert output.status == "drafted" and output.role == "control"
    assert [(file.path, file.content) for file in output.files] == [("test_control.py", "control draft")]
    refusals = [item for item in seen if getattr(item, "status", None) == "refused"]
    assert len(refusals) == 2
    assert all("refusals_left" not in item.model_dump() for item in refusals)


def test_exploit_reads_explicit_seed_but_cannot_overwrite_it(inputs):
    seed = PatchedFile(path="test_control.py", content="frozen control draft")
    exploit = inputs.model_copy(update={"role": "exploit", "frozen_control": (seed,)})
    output, seen = run(exploit, [("read_source", {"path": seed.path}),
                                ("write_test_file", {"path": seed.path, "content": "replaced"}),
                                ("write_test_file", {"path": "test_exploit.py", "content": "exploit draft"})])
    assert output.status == "drafted" and output.role == "exploit"
    assert output.frozen_control_sha256 == sha256(seed.content.encode()).hexdigest()
    assert [(file.path, file.content) for file in output.files] == [("test_exploit.py", "exploit draft")]
    returned = next(item for item in seen if getattr(item, "path", None) == seed.path and hasattr(item, "lines"))
    assert returned.lines[0].text == seed.content
    assert exploit.frozen_control == (seed,)


def test_pair_uses_same_factory_and_tools_to_draft_both_owned_files(inputs):
    output, _ = run(inputs, [("write_test_file", {"path": "test_control.py", "content": "control draft"}),
                            ("write_test_file", {"path": "test_exploit.py", "content": "exploit draft"})])
    assert output.role == "pair" and output.status == "drafted"
    assert {file.path for file in output.files} == set(inputs.owned_paths)
    assert output.frozen_control_sha256 is None
    assert not {"ready", "executed", "run_command", "dev_runs"} & output.model_dump().keys()


def test_shared_file_layout_is_explicitly_blocked(inputs):
    shared_id = inputs.control_test_id.replace("test_control", "test_exploit")
    shared_id = shared_id.replace("test_exploit.py", "test_control.py")
    shared = DraftingInput.model_validate(inputs.model_dump() | {
        "exploit_test_path": "test_control.py", "exploit_test_id": shared_id})
    output, _ = run(shared, [("write_test_file", {"path": "test_control.py", "content": "draft"})])
    assert output.status == "blocked" and output.layer == "layout" and not output.files


def test_factory_role_mismatch_is_refused_before_any_tools(inputs):
    calls = []
    def respond(messages, info):
        calls.append(info)
        raise AssertionError("model must not be called for role mismatch")
    async def invoke():
        with models.override_allow_model_requests(False):
            return await create_drafting_agent(FunctionModel(respond), role="control").run(
                drafting_prompt(inputs), deps=DraftingDependencies(inputs))
    with pytest.raises(ValueError, match="factory role"):
        asyncio.run(invoke())
    assert not calls


@pytest.mark.parametrize("baseline_id,baseline_path,control_path,exploit_path,container", [
    ("test_existing.py::test_existing", "test_existing.py", "test_control.py", "test_exploit.py", None),
    ("test_existing.rb::ExistingTest#test_existing", "test_existing.rb", "test_control.rb", "test_exploit.rb", "ProbeTest"),
    ("existing.test.js::existing", "existing.test.js", "control.test.js", "exploit.test.js", None),
    ("t/existing.t#existing", "t/existing.t", "t/control.t", "t/exploit.t", None),
    ("pkg.ExistingTest#existing", "src/test/java/pkg/ExistingTest.java", "src/test/java/pkg/ControlTest.java", "src/test/java/pkg/ExploitTest.java", None),
])
def test_operator_ids_use_existing_runner_formatter_without_narrowing_grammar(
        inputs, baseline_id, baseline_path, control_path, exploit_path, container):
    control = format_test_id(baseline_id, control_path, "test_control", container, baseline_path=baseline_path)
    exploit = format_test_id(baseline_id, exploit_path, "test_exploit", container, baseline_path=baseline_path)
    environment = inputs.environment.model_copy(update={"approved_test_paths": (control_path, exploit_path)})
    adapted = DraftingInput.model_validate(inputs.model_dump() | {"environment": environment,
        "control_test_path": control_path, "exploit_test_path": exploit_path,
        "control_test_id": control, "exploit_test_id": exploit})
    assert adapted.owned_paths == (control_path, exploit_path)
