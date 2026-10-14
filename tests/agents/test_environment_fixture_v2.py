"""Versioned source-command truth and native post-halt provenance guards."""
import asyncio
import json
from hashlib import sha256
from types import SimpleNamespace
import pytest
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from corsair.agents.environment.agent import create_environment_agent, environment_prompt
from corsair.agents.environment.contracts import EnvironmentInput
from corsair.agents.environment.dependencies import EnvironmentDependencies, SetupBudget
from evals.environment.evaluate import ROOT, HANDLE, load_cases, RecordedExecution, EnvironmentChecks


def test_v2_preserves_v1_and_declares_every_known_command_in_source():
    old, before = load_cases('development')
    raw, after = load_cases('development-v2')
    assert sha256(old).hexdigest() == 'bc2b151d17d34ccc9d40035cf06b6b0338208f8745d8ae7dd97945a1c4cf00e6'
    assert raw != old
    assert [(c['name'],c['status'],c['layer'],c['max_commands']) for c in after] == [
        (c['name'],c['status'],c['layer'],c['max_commands']) for c in before]
    for case in after:
        source = '\n'.join(s['content'] for s in case['inputs']['source_files'])
        assert all(' '.join(command) in source for command in case['commands'])
    with pytest.raises(ValueError,match='unknown frozen'):
        load_cases('implicit-latest')


def test_v2_does_not_approve_an_early_halt_as_unknown_delivery_trajectory():
    _, cases = load_cases('development-v2')
    case = next(c for c in cases if c['name']=='unknown-delivery')
    assert case['observations'][0]['unknown'] and not case['observations'][1]['unknown']
    def checks(commands):
        return EnvironmentChecks().evaluate(SimpleNamespace(metadata=case,
            inputs=SimpleNamespace(inputs=EnvironmentInput.model_validate(case['inputs'])),
            output=SimpleNamespace(status='blocked',layer='sandbox',citations=[],receipts=[]),
            attributes={'commands':commands,'read_paths':case['required_reads'],'records':[]}))
    assert not checks([])['required_commands']
    assert checks(case['commands'][:1])['required_commands']
    assert not checks(case['commands'])['unknown_halt']


@pytest.mark.parametrize('final', [
    {'status':'unsupported','requirement':'Python 3.13 required but prepared runtime is 3.12',
     'citations':[{'path':'README.md','start_line':2,'end_line':2}]},
    {'status':'blocked','layer':'sandbox','evidence':'native stream ended without exit status',
     'run_ids':[1,2],'citations':[]},
])
def test_native_sdk_refuses_post_halt_status_or_invented_run_id(final):
    _, cases = load_cases('development-v2')
    case = next(c for c in cases if c['name']=='unknown-delivery')
    inputs = EnvironmentInput.model_validate(case['inputs'])
    execution = RecordedExecution(case)
    deps = EnvironmentDependencies(inputs=inputs, execution=execution, handle=HANDLE,
        toolchain_id='python-3.12',scratch_location='/sandbox/scratch',budget=SetupBudget())
    sequence = [('read_source',{'path':'README.md'}),('list_toolchains',{}),
        ('run_setup_command',{'command':case['commands'][0]}),
        ('run_setup_command',{'command':case['commands'][1]})]
    position = 0
    async def respond(messages, info):
        nonlocal position
        if position < len(sequence):
            name,args=sequence[position];position+=1
            return ModelResponse(parts=[ToolCallPart(name,args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'draft':final})])
    async def run():
        with models.override_allow_model_requests(False):
            agent = create_environment_agent(FunctionModel(respond),output_retries=1)
            with pytest.raises(UnexpectedModelBehavior,match='output retries'):
                await agent.run(environment_prompt(inputs),deps=deps)
    asyncio.run(run())
    assert execution.calls == [tuple(case['commands'][0])]
    assert len(deps.ledger.records)==1 and deps.ledger.records[0].delivery=='unknown'
    assert deps.ledger.halted is not None


def test_v10_native_sdk_admits_distinct_recipe_and_terminal_execution_once():
    from corsair.agents.environment.agent import SKILL_TEXT, PROMPT_VERSION
    _, cases = load_cases('development-v2')
    case = next(c for c in cases if c['name']=='ready')
    inputs = EnvironmentInput.model_validate(case['inputs'])
    execution = RecordedExecution(case)
    deps = EnvironmentDependencies(inputs=inputs,execution=execution,handle=HANDLE,
        toolchain_id='python-3.12',scratch_location='/sandbox/scratch')
    sequence=[('read_source',{'path':'.github/workflows/ci.yml'}),('list_toolchains',{})]+[
        ('run_setup_command',{'command':command}) for command in case['commands']]
    position=0
    async def respond(messages,info):
        nonlocal position
        assert 'never again in `recipe`' in SKILL_TEXT
        assert 'Count each successful' in info.instructions
        if position<len(sequence):
            name,args=sequence[position];position+=1
            return ModelResponse(parts=[ToolCallPart(name,args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'draft':case['draft']})])
    async def run():
        with models.override_allow_model_requests(False):
            agent=create_environment_agent(FunctionModel(respond),output_retries=0)
            return (await agent.run(environment_prompt(inputs),deps=deps)).output
    result=asyncio.run(run())
    assert PROMPT_VERSION=='environment-v10-distinct-recipe-and-terminal-commands-native-skills-v1'
    assert result.status=='ready' and len(result.recipe)==1
    assert tuple(record.command for record in result.receipts)==tuple(tuple(c) for c in case['commands'])
    assert len(result.receipts)==4 and result.build_command not in [s.command for s in result.recipe]
