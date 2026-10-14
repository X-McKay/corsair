"""Independent native contexts, narrow projections and ownership; no authored-code execution."""
import asyncio
import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from corsair.agents.source.contracts import SourceExcerpt
from corsair.ports.test_runner import format_test_id
from evals.test_planning.evaluate import dataset
from evals.test_planning.property_plan import ReadyPropertyPlan, reference_property
from evals.experiments.probe_specialists import (SpecialistDependencies, create_control_agent,
    create_exploit_agent, project_control_input, project_exploit_input, prompt_for)
from evals.experiments.probe_specialists.prompts import CONTROL_SKILL_TEXT, EXPLOIT_SKILL_TEXT
from evals.experiments.probe_specialists.tools import TOOLSET_SHA256, specialist_tools

@pytest.fixture
def pair():
    case = dataset('unit-first').cases[0]
    draft = reference_property(case.inputs, case.metadata)
    sources = case.inputs.source_files
    refs = [SourceExcerpt(**ref, quote='\n'.join(next(s for s in sources if s.path == ref['path']).content.splitlines()[ref['start_line']-1:ref['end_line']])) for ref in draft['citations']]
    plan = ReadyPropertyPlan[SourceExcerpt].model_validate(draft | {'citations': refs})
    env = case.inputs.environment
    baseline = env.baseline_test
    def identity(path, name):
        return format_test_id(baseline.test_id, path, name, baseline_path=baseline.path)
    return (project_control_input(plan, sources, env, identity('test_control.py', 'test_control'), 'test_control.py', ordinary_behavior='Ordinary behavior'),
            project_exploit_input(plan, sources, env, identity('test_exploit.py', 'test_exploit'), 'test_exploit.py', safety_property='Safety behavior'))


def invoke(inputs, factory, *, read=True):
    actions = [('read_source', {'path': 'test_exploit.py' if inputs.test_path == 'test_control.py' else 'test_control.py'}),
               ('write_test_file', {'path': inputs.source_files[0].path, 'content': 'changed'}),
               ('write_test_file', {'path': 'test_exploit.py' if inputs.test_path == 'test_control.py' else 'test_control.py', 'content': 'changed'})]
    if read:
        actions += [('read_source', {'path': c.path, 'start_line': c.start_line}) for c in inputs.property_plan.citations]
    actions += [('write_test_file', {'path': inputs.test_path, 'content': 'first line\nsecond line\n'})]
    seen = []
    def respond(messages, info):
        seen[:] = [part.content for m in messages for part in m.parts if isinstance(part, ToolReturnPart)]
        if actions:
            name, args = actions.pop(0)
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'draft': {'status': 'drafted', 'limitations': ['Proposed only']}})])
    async def run():
        with models.override_allow_model_requests(False):
            return await factory(FunctionModel(respond), output_retries=0).run(prompt_for(inputs), deps=SpecialistDependencies(inputs))
    return asyncio.run(run()), seen


def test_projections_are_narrow_and_skills_distinct(pair):
    control, exploit = pair
    assert 'adversarial_input' not in prompt_for(control)
    assert 'control_input' not in prompt_for(exploit)
    assert 'test_exploit.py' not in prompt_for(control)
    assert 'test_control.py' not in prompt_for(exploit)
    assert control.environment.approved_test_paths == (control.test_path,)
    assert exploit.environment.approved_test_paths == (exploit.test_path,)
    assert CONTROL_SKILL_TEXT != EXPLOIT_SKILL_TEXT
    assert 'stable across' in CONTROL_SKILL_TEXT
    assert 'Assert\nsafe behavior' in EXPLOIT_SKILL_TEXT

@pytest.mark.parametrize('index,factory', [(0, create_control_agent), (1, create_exploit_agent)])
def test_each_context_reads_only_saved_source_and_writes_one_own_file(pair, index, factory):
    inputs = pair[index]
    result, seen = invoke(inputs, factory)
    assert result.output.role == ('control' if index == 0 else 'exploit')
    assert result.output.input_digest == inputs.input_digest
    assert [(f.path, f.content) for f in result.output.files] == [(inputs.test_path, 'first line\nsecond line\n')]
    assert sum(getattr(item, 'status', None) == 'refused' for item in seen) == 2
    assert any(getattr(item, 'status', None) == 'not_in_source' for item in seen)


def test_drafted_requires_current_run_anchor_reads(pair):
    with pytest.raises(Exception, match='output retries'):
        invoke(pair[0], create_control_agent, read=False)


def test_factories_reject_other_role_input(pair):
    with pytest.raises(ValueError, match='requires the narrow ControlInput'):
        invoke(pair[1], create_control_agent)


def test_native_toolset_identity_and_only_two_tools():
    tools = specialist_tools()
    assert list(tools.tools) == ['read_source', 'write_test_file']
    assert all(tool.max_retries == 0 for tool in tools.tools.values())
    assert TOOLSET_SHA256 == 'e7757a49e233091122183a6af66b2a0de785348f8aa0de0a22227d84d86fef82'
