"""Capture the complete first native offer without model endpoints or generated-code execution."""
import asyncio
from dataclasses import asdict
from pydantic import TypeAdapter
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel, AgentInfo

class CaptureComplete(Exception):
    pass


def inputs_for(role):
    if role in ('control_authoring','exploit_authoring'):
        from evals.probe_authoring.evaluate import inputs_for as frozen_inputs
        from evals.experiments.probe_specialists.cases import load_cases
        from corsair.agents.probe_authoring.contracts import ControlInput,ExploitInput
        side='control' if role=='control_authoring' else 'exploit'
        cls=ControlInput if side=='control' else ExploitInput
        return cls.model_validate(frozen_inputs(load_cases()[0],'reported',side).model_dump())
    if role=='planning':
        from evals.experiments.staged_baseline.planning_v2 import dataset
        return dataset().cases[0].inputs
    if role=='assessment':
        from evals.evidence_assessment.unit_test import dataset
        return dataset().cases[0].inputs
    raise ValueError(role)


def factory_parts(role):
    if role in ('control_authoring','exploit_authoring'):
        import importlib
        package=importlib.import_module('corsair.agents.'+role)
        side='control' if role=='control_authoring' else 'exploit'
        return getattr(package,'create_'+side+'_agent'),package.prompt_for,package.SpecialistDependencies
    if role=='planning':
        from corsair.agents.test_planning.agent import create_test_planning_agent, planning_prompt
        from corsair.agents.test_planning.dependencies import PlanningDependencies
        return create_test_planning_agent,planning_prompt,PlanningDependencies
    from corsair.agents.evidence_assessment.agent import create_evidence_assessment_agent,assessment_prompt
    from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
    return create_evidence_assessment_agent,assessment_prompt,AssessmentDependencies


def normalize(value):
    if isinstance(value, dict):
        return {key:normalize(item) for key,item in value.items()}
    if isinstance(value, (set,frozenset)):
        return sorted(normalize(item) for item in value)
    if isinstance(value, (list,tuple)):
        return [normalize(item) for item in value]
    return value


def capture(role, *, output_retries=2, activate=False):
    factory,prompt,deps_type=factory_parts(role)
    inputs=inputs_for(role); seen={}
    activation_ids = {'control_authoring':['control-probe','native-probe-boundary'],
        'exploit_authoring':['exploit-probe','native-probe-boundary'],
        'planning':['plan-two-tests'],'assessment':['assess-evidence']}[role]
    def respond(messages,info):
        offer=normalize(asdict(info))
        seen.setdefault('initial_offer',offer)
        seen['native_offer']=offer
        seen['loaded_instructions']=[part.content['instructions'] for message in messages for part in message.parts if part.__class__.__name__=='LoadCapabilityReturnPart' and isinstance(part.content,dict)]
        if activate and activation_ids:
            from pydantic_ai.messages import ModelResponse,ToolCallPart
            return ModelResponse(parts=[ToolCallPart('load_capability', {'id':activation_ids.pop(0)})])
        raise CaptureComplete()
    agent=factory(FunctionModel(respond),output_retries=output_retries)
    seen['input_schema']=inputs.model_json_schema()
    seen['rendered_input']=prompt(inputs)
    seen['dependencies_type']=deps_type.__module__+'.'+deps_type.__qualname__
    seen['native_retries']={'tools':agent._max_tool_retries,'output':agent._max_output_retries}
    seen['agent_name']=agent.name
    async def run():
        with models.override_allow_model_requests(False):
            try:
                await agent.run(prompt(inputs),deps=deps_type(inputs))
            except CaptureComplete:
                pass
    asyncio.run(run())
    assert 'native_offer' in seen
    return seen


def capture_root(role, *, activate=False):
    """Root's pre-migration first native offer, persisted without endpoint or tool execution."""
    from pydantic_ai.tools import ToolDefinition
    if role=='environment':
        from corsair.agents.environment.agent import create_environment_agent
        from corsair.agents.environment.dependencies import EnvironmentDependencies,SetupBudget
        from corsair.agents.environment.contracts import EnvironmentInput
        from evals.environment.evaluate import load_cases,RecordedExecution,HANDLE
        _,cases=load_cases('development-v2');case=cases[0]
        deps=EnvironmentDependencies(EnvironmentInput.model_validate(case['inputs']),RecordedExecution(case),HANDLE,
            case.get('toolchain_id','python-3.12'),'/sandbox/scratch',SetupBudget(max_commands=case['max_commands']))
        factory=create_environment_agent
    elif role=='identification':
        from corsair.agents.issue_identification.agent import create_issue_identification_agent
        from corsair.agents.issue_identification.dependencies import FixtureDependencies
        from evals.experiments.staged_baseline.identification_v2 import dataset
        factory=create_issue_identification_agent;deps=FixtureDependencies(dataset().cases[0].inputs)
    elif role=='repository_identification':
        from corsair.agents.issue_identification.agent import create_repository_identification_agent
        from corsair.agents.issue_identification.dependencies import RepositoryDependencies
        from tests.agents.test_repository_source import inputs,tree
        factory=create_repository_identification_agent;deps=RepositoryDependencies(inputs(),tree())
    else:raise ValueError(role)
    seen={}
    activation_ids={'environment':['prepare-environment'],'identification':['identify-issue'],
        'repository_identification':['identify-issue-repository']}[role]
    def respond(messages,info):
        seen.setdefault('initial_offer',normalize(asdict(info)))
        seen['loaded_instructions']=[part.content['instructions'] for message in messages for part in message.parts if part.__class__.__name__=='LoadCapabilityReturnPart' and isinstance(part.content,dict)]
        if activate and activation_ids:
            from pydantic_ai.messages import ModelResponse,ToolCallPart
            return ModelResponse(parts=[ToolCallPart('load_capability', {'id':activation_ids.pop(0)})])
        seen.update(instructions=info.instructions,
            function_tools=TypeAdapter(list[ToolDefinition]).dump_python(info.function_tools,mode='json'),
            output_tools=TypeAdapter(list[ToolDefinition]).dump_python(info.output_tools,mode='json'),
            allow_text_output=info.allow_text_output,model_settings=info.model_settings)
        raise CaptureComplete()
    agent=factory(FunctionModel(respond),output_retries=1)
    async def run():
        with models.override_allow_model_requests(False):
            try:await agent.run('Observe factory construction only; no external execution.',deps=deps)
            except CaptureComplete:pass
    asyncio.run(run())
    assert seen
    seen.update(name=agent.name,deps_type=agent._deps_type.__module__+'.'+agent._deps_type.__qualname__)
    return seen
