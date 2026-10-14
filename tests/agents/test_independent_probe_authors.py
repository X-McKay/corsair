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
from corsair.agents.control_authoring import SpecialistDependencies, create_control_agent, project_control_input, prompt_for
from corsair.agents.exploit_authoring import create_exploit_agent, project_exploit_input
from corsair.agents.control_authoring.prompts import CONTROL_SKILL_TEXT
from corsair.agents.exploit_authoring.prompts import EXPLOIT_SKILL_TEXT
from corsair.agents.control_authoring.tools import TOOLSET_SHA256, specialist_tools

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
    from evals.experiments.probe_specialists.contracts import project_control_input as frozen_control, project_exploit_input as frozen_exploit
    from corsair.agents.probe_authoring.contracts import ControlInput, ExploitInput
    return (ControlInput.model_validate(frozen_control(plan, sources, env, identity('test_control.py', 'test_control'), 'test_control.py', ordinary_behavior='Ordinary behavior').model_dump()),
            ExploitInput.model_validate(frozen_exploit(plan, sources, env, identity('test_exploit.py', 'test_exploit'), 'test_exploit.py', safety_property='Safety behavior').model_dump()))


def invoke(inputs, factory, *, read=True, assertion_lines=(1,)):
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
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'draft': {'status': 'drafted', 'limitations': ['Proposed only'], 'assertion_lines': assertion_lines}})])
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
    assert TOOLSET_SHA256 == '2634c27a0b1ade4023dec7637cca9ccc362870299b858232cbfffcfeef03ab54'


def test_exploit_toolset_identity():
    from corsair.agents.exploit_authoring.tools import TOOLSET_SHA256, specialist_tools
    assert list(specialist_tools().tools) == ['read_source', 'write_test_file']
    assert TOOLSET_SHA256 == 'c149cfbd6ba0e6187565051a646d777bf27bfda28ee048409dc0130a1c5f22f2'


def production_plan():
    from corsair.agents.test_planning.contracts import ReadyTestPlan, EnvironmentEvidence
    from copy import deepcopy
    case = dataset('unit-first').cases[0]
    data = deepcopy(case.metadata.reference_plan)
    paths = ('test_control.py', 'test_exploit.py')
    for key, path in zip(('control', 'security'), paths):
        spec = data[key]
        spec['test_path'] = path
        spec['test_id'] = path + '::' + spec['test_id'].split('::')[-1]
    def anchored(ref):
        source = next(s for s in case.inputs.source_files if s.path == ref['path'])
        return ref | {'quote': '\n'.join(source.content.splitlines()[ref['start_line']-1:ref['end_line']])}
    data['citations'] = [anchored(r) for r in data['citations']]
    for key in ('control', 'security'):
        data[key]['source_references'] = [anchored(r) for r in data[key]['source_references']]
    env = EnvironmentEvidence.model_validate(case.inputs.environment.model_dump() | {'approved_test_paths': paths})
    return ReadyTestPlan.model_validate(data), case.inputs.source_files, env


def test_production_projection_preserves_own_spec_and_excludes_peer():
    plan, sources, env = production_plan()
    control = project_control_input(plan, sources, env)
    exploit = project_exploit_input(plan, sources, env)
    assert control.fixture_setup == plan.control.fixture_setup
    assert control.observation == plan.control.observation
    assert exploit.observation == plan.security.observation
    assert exploit.property_plan.safety_property == plan.security.required_behavior
    assert plan.security.test_id not in prompt_for(control)
    assert plan.control.test_id not in prompt_for(exploit)
    assert plan.security.input not in prompt_for(control)
    assert plan.control.input not in prompt_for(exploit)


def test_production_projection_refuses_shared_or_unapproved_paths():
    plan, sources, env = production_plan()
    shared = plan.model_copy(update={'security': plan.security.model_copy(update={'test_path':plan.control.test_path})})
    with pytest.raises(ValueError, match='distinct own test paths'):
        project_control_input(shared, sources, env)
    refused = env.model_copy(update={'approved_test_paths':('test_other.py',)})
    with pytest.raises(ValueError, match='not operator approved'):
        project_exploit_input(plan, sources, refused)


def test_production_inputs_refuse_tampered_source_anchor(pair):
    control, _ = pair
    bad = control.model_dump()
    bad['property_plan']['citations'][0]['quote'] = 'tampered'
    with pytest.raises(ValueError, match='immutable source'):
        type(control).model_validate(bad)


@pytest.mark.parametrize('anchors', [(3,), (1, 1)])
def test_assertion_anchors_refuse_outside_or_duplicate_lines(pair, anchors):
    with pytest.raises(Exception, match='output retries'):
        invoke(pair[0], create_control_agent, assertion_lines=anchors)


def test_assertion_anchors_bind_exact_own_file_quotes(pair):
    result, _ = invoke(pair[1], create_exploit_agent, assertion_lines=(2,))
    assert result.output.assertion_lines == (2,)
    assert result.output.assertion_anchors == (SourceExcerpt(path=pair[1].test_path,
        start_line=2, end_line=2, quote='second line'),)
