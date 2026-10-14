"""New durable child contracts and payloads; historical histories are not rewritten."""
import asyncio
from datetime import timedelta
from pydantic_ai.durable_exec.temporal import PydanticAIPayloadConverter
from pydantic_ai.messages import ModelRequest, UserPromptPart, ModelMessagesTypeAdapter
from temporalio.common import RetryPolicy
from temporalio.converter import DataConverter
from corsair.agents.probe_authoring.contracts import Drafted, Blocked, ControlInput, ExploitInput
from corsair.agents.probe_authoring.dependencies import SpecialistDependencies
from corsair.composition.direct import CompositionBudget
from corsair.workflows.chain import CHILDREN
from corsair.workflows.chain_runtime import (SpecialistRunContext, StageRequest, StageRecord, StageKeys,
    STAGES, configure_chain, within)
from tests.agents.test_split_chain_integration import inputs, draft
from corsair.agents.probe_authoring.contracts import project_control_input, project_exploit_input
from evals.fixture_e2e.case import scripted_identification

CONVERTER = DataConverter(payload_converter_class=PydanticAIPayloadConverter)


def test_independent_native_child_payloads_roundtrip():
    case, plan, _ = inputs()
    async def check():
        for projection, role, hint in ((project_control_input, 'control', ControlInput),
                                       (project_exploit_input, 'exploit', ExploitInput)):
            own = projection(plan, case.issue.source_files, case.environment)
            request = StageRequest(own, role, CompositionBudget())
            restored, = await CONVERTER.decode(await CONVERTER.encode([request]), [StageRequest[hint]])
            assert restored == request
            from pydantic_ai.usage import RunUsage
            record = StageRecord(draft(own, role), RunUsage(), (), None)
            restored, = await CONVERTER.decode(await CONVERTER.encode([record]), [StageRecord[Drafted | Blocked]])
            assert restored == record
    asyncio.run(check())
    assert set(CHILDREN) == set(STAGES)
    assert 'authoring' not in CHILDREN
    assert StageKeys('i','p','c','e','a').exploit_authoring == 'e'


def test_worker_registers_independent_factories_without_development_runner():
    def forbidden(purpose): raise AssertionError('no development runner is resolved during authoring')
    runtime = configure_chain({'fixture': scripted_identification()}, forbidden,
        activity_config={'start_to_close_timeout': timedelta(seconds=10),
                         'retry_policy': RetryPolicy(maximum_attempts=1)})
    assert set(runtime.agents) == set(STAGES)
    assert runtime.agents['control_authoring'].name == 'control_probe_author'
    assert runtime.agents['exploit_authoring'].name == 'exploit_probe_author'
    lower = CompositionBudget().model_copy(update={'control_authoring': CompositionBudget().control_authoring.model_copy(update={'request_limit': 1})})
    assert within(lower, CompositionBudget())
    assert not within(CompositionBudget(), lower)


def test_specialist_activity_context_keeps_only_own_history():
    case, plan, _ = inputs()
    own = project_control_input(plan, case.issue.source_files, case.environment)
    deps = SpecialistDependencies(own)
    messages = [ModelRequest(parts=[UserPromptPart('own input only')])]
    from pydantic_ai.usage import RunUsage
    ctx = SpecialistRunContext.deserialize_run_context({'run_id': 'r',
        'messages': ModelMessagesTypeAdapter.dump_python(messages, mode='json')}, deps)

    assert ctx.deps == deps
    assert ModelMessagesTypeAdapter.dump_json(ctx.messages) == ModelMessagesTypeAdapter.dump_json(messages)


def test_durable_author_retry_allowance_cannot_differ_from_built_factory(tmp_path):
    import pytest
    from temporalio.exceptions import ApplicationError
    from corsair.workflows.chain import _admit
    ceiling=CompositionBudget()
    runtime=configure_chain({'fixture':scripted_identification()},lambda purpose:None,
        ceiling=ceiling,activity_config={'start_to_close_timeout':timedelta(seconds=10)})
    assert runtime.agents['control_authoring']._max_output_retries==2
    assert runtime.agents['exploit_authoring']._max_output_retries==2
    assert runtime.agents['planning']._max_output_retries==1
    for requested in (0,1,3):
        changed=ceiling.model_copy(update={'author_output_retries':requested})
        assert not within(changed,ceiling)
        with pytest.raises(ApplicationError) as refusal: _admit(('fixture',),changed)
        assert refusal.value.type=='BudgetNotAdmitted' and refusal.value.non_retryable
    assert _admit(('fixture',),ceiling) is runtime
