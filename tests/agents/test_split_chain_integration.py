"""Production isolation and honest partial receipts, without model or execution endpoints."""
import asyncio
from dataclasses import replace
from uuid import uuid4
import pytest
from pydantic_ai.usage import RunUsage
from corsair.agents.issue_identification.contracts import IssueIdentification
from corsair.agents.probe_authoring.contracts import Drafted, Blocked, project_control_input, project_exploit_input
from corsair.agents.test_authoring.contracts import PatchedFile
from corsair.agents.source.contracts import SourceExcerpt
from corsair.agents.test_planning.contracts import ReadyTestPlan
from corsair.composition.assembly import assemble_patch
from corsair.composition.direct import CompositionBudget, StageAttempt, run_chain, stage_limits
from corsair.composition.receipts import STAGES, stage_configs
from corsair.inference.config import InferenceConfig
from evals.fixture_e2e.case import fixture_case, reference_plan


def inputs():
    case = fixture_case()
    data = reference_plan()
    sources = {s.path: s.content.splitlines() for s in case.issue.source_files}
    def cite(c):
        return c | {'quote': '\n'.join(sources[c['path']][c['start_line']-1:c['end_line']])}
    data['citations'] = [cite(c) for c in data['citations']]
    for role, path in (('control', 'test_control.py'), ('security', 'test_exploit.py')):
        spec = data[role]
        spec['test_id'] = spec['test_id'].replace('test_documents.py', path)
        spec['test_path'] = path
        spec['source_references'] = [cite(c) for c in spec['source_references']]
        spec.pop('witness', None)
        spec['observation'] = {'kind': 'return_value', 'property': spec['required_behavior'],
                               'seam': spec['implementation_call']}
    plan = ReadyTestPlan.model_validate(data)
    environment = case.environment.model_copy(update={'approved_test_paths': ('test_control.py', 'test_exploit.py')})
    identification = IssueIdentification(status='ready', scope='component', target={'symbol': 'read_document',
        'source': data['control']['source_references'][0]}, reason=None, reported_issue=case.issue.issue)
    return replace(case, environment=environment), plan, identification


def draft(inputs, role):
    name = inputs.test_id.split('::')[-1]
    return Drafted(role=role, input_digest=inputs.input_digest,
        files=(PatchedFile(path=inputs.test_path, content=f'def {name}():\n    assert 1 == 1\n'),),
        limitations=('Source proposal; semantic validity remains unreviewed',),
        read_anchors=inputs.property_plan.citations, assertion_lines=(2,),
        assertion_anchors=(SourceExcerpt(path=inputs.test_path, start_line=2, end_line=2, quote="    assert 1 == 1"),))


def test_split_assembly_never_claims_development_execution():
    case, plan, _ = inputs()
    control = project_control_input(plan, case.issue.source_files, case.environment)
    exploit = project_exploit_input(plan, case.issue.source_files, case.environment)
    patch = assemble_patch(plan, case.environment, draft(control, 'control'), draft(exploit, 'exploit'))
    assert patch.status == 'source_proposal' and len(patch.files) == 2
    assert not hasattr(patch, 'dev_runs')
    assert patch.security_assertion_lines == (2,)
    assert control.environment.approved_test_paths == ('test_control.py',)
    assert exploit.environment.approved_test_paths == ('test_exploit.py',)
    assert 'adversarial_input' not in control.model_dump()['property_plan']
    assert 'control_input' not in exploit.model_dump()['property_plan']


def test_partial_control_is_retained_before_blocked_exploit():
    case, plan, identification = inputs()
    seen = []
    async def invoke(stage, own):
        seen.append((stage, own))
        if stage == 'identification': output = identification
        elif stage == 'planning': output = plan
        elif stage == 'control_authoring': output = draft(own, 'control')
        else: output = Blocked(role='exploit', input_digest=own.input_digest, status='blocked',
            layer='source', reason='Reported condition needs unavailable source', files=())
        return StageAttempt(stage, output, RunUsage(), (), 0, None)
    async def forbidden(*a, **k): raise AssertionError('execution must not run')
    run = asyncio.run(run_chain(case, invoke, forbidden, forbidden, new_operation=uuid4))
    assert run.stopped_at == 'exploit_authoring' and run.patch is None
    assert [s for s, _ in seen] == ['identification', 'planning', 'control_authoring', 'exploit_authoring']
    assert len(run.attempts[-2].output.files) == 1
    assert seen[-1][1] == project_exploit_input(plan, case.issue.source_files, case.environment)


def test_budgets_and_profiles_are_explicit_per_author():
    case, plan, _ = inputs()
    control = project_control_input(plan, case.issue.source_files, case.environment)
    exploit = project_exploit_input(plan, case.issue.source_files, case.environment)
    budgets = CompositionBudget()
    assert stage_limits('control_authoring', control, budgets).work_tool_calls == 3
    assert stage_limits('exploit_authoring', exploit, budgets).work_tool_calls == 3
    config = InferenceConfig.model_validate({'models': {'m': {'provider': 'bedrock', 'model_name': 'm', 'region': 'us-east-1'}},
        'agents': {'identification':'m', 'planning':'m', 'authoring':'m', 'assessment':'m'}})
    with pytest.raises(ValueError, match='control_authoring'):
        stage_configs(config, {})
    assert STAGES == ('identification', 'planning', 'control_authoring', 'exploit_authoring', 'assessment')

@pytest.mark.parametrize('control_path,control_id,exploit_path,exploit_id,content,anchor', [
    ('src/test/java/C.java','C#control','src/test/java/E.java','E#exploit',
     'class E { void exploit() { assertEquals(1, 1); } }', 'class E { void exploit() { assertEquals(1, 1); } }'),
    ('t/control.t','t/control.t#control','t/exploit.t','t/exploit.t#exploit',
     "is($actual, $expected, 'safety');", "is($actual, $expected, 'safety');"),
])
def test_generic_source_anchor_assembly(control_path, control_id, exploit_path, exploit_id, content, anchor):
    case, plan, _ = inputs()
    plan = plan.model_copy(update={'control': plan.control.model_copy(update={'test_id':control_id, 'test_path':control_path}),
        'security': plan.security.model_copy(update={'test_id':exploit_id, 'test_path':exploit_path})})
    environment = case.environment.model_copy(update={'approved_test_paths': (control_path,exploit_path)})
    def own(role, path):
        return Drafted(role=role, input_digest='a'*64, files=(PatchedFile(path=path, content=content),),
            limitations=('Proposed assertion requires semantic review',), read_anchors=plan.citations,
            assertion_lines=(1,), assertion_anchors=(SourceExcerpt(path=path,start_line=1,end_line=1,quote=anchor),))
    patch = assemble_patch(plan, environment, own('control',control_path), own('exploit',exploit_path))
    assert patch.security_assertion_lines == (1,)


def test_witness_only_legacy_plan_stops_before_any_author_or_execution():
    case, plan, identification = inputs()
    plan = plan.model_copy(update={'security': plan.security.model_copy(update={'observation': None})})
    called = []
    async def invoke(stage, own):
        called.append(stage)
        return StageAttempt(stage, identification if stage == 'identification' else plan, RunUsage(), (), 0, None)
    async def forbidden(*a, **k): raise AssertionError('no author or revision execution allowed')
    run = asyncio.run(run_chain(case, invoke, forbidden, forbidden, new_operation=uuid4))
    assert run.stopped_at == 'planning' and 'witness-only' in run.reason
    assert called == ['identification', 'planning']


def test_author_budget_derivation_uses_own_retries_and_tighter_ceiling():
    from pydantic import ValidationError
    from corsair.composition.direct import stage_output_retries
    case, plan, _ = inputs()
    budget = CompositionBudget()
    for stage, project in (('control_authoring',project_control_input),('exploit_authoring',project_exploit_input)):
        own = project(plan,case.issue.source_files,case.environment)
        ceiling = getattr(budget,stage)
        assert (ceiling.request_limit,ceiling.tool_calls_limit,ceiling.total_tokens_limit,ceiling.timeout_seconds)==(20,20,128000,900)
        current = stage_limits(stage,own,budget)
        fewer = stage_limits(stage,own,budget.model_copy(update={'author_output_retries':1}))
        assert current.read_windows==fewer.read_windows and current.work_tool_calls==fewer.work_tool_calls
        assert current.request_limit==fewer.request_limit+1
        assert stage_output_retries(stage,budget)==2
    assert stage_output_retries('planning',budget)==1
    assert stage_output_retries('assessment',budget)==1
    for invalid in (3,True,-1):
        with pytest.raises(ValidationError): CompositionBudget(author_output_retries=invalid)
    with pytest.raises(ValidationError): CompositionBudget(output_retries=2)


def test_direct_author_native_output_retry_allowance_is_two(tmp_path):
    from pydantic_ai import models
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from corsair.adapters.local_artifacts import LocalArtifacts
    from corsair.composition.direct import run_direct, StageModels
    from evals.fixture_e2e.case import (scripted_identification,scripted_planning,scripted_control_authoring,
        scripted_exploit_authoring,scripted_assessment,reviewed_runners)
    base = scripted_control_authoring()
    corrections = 0
    async def twice_invalid(messages,info):
        nonlocal corrections
        response = await base.function(messages,info)
        if any(isinstance(p,ToolCallPart) and p.tool_name==info.output_tools[0].name for p in response.parts):
            if corrections<2:
                corrections+=1
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'draft':{
                    'status':'drafted','assertion_lines':[],'limitations':['Invalid proposed source anchor']}})])
        return response
    stage_models=StageModels(identification=scripted_identification(),planning=scripted_planning(),
        control_authoring=FunctionModel(twice_invalid),exploit_authoring=scripted_exploit_authoring(),
        assessment=scripted_assessment())
    (tmp_path/'artifacts').mkdir(mode=0o700);(tmp_path/'work').mkdir()
    async def run():
        with models.override_allow_model_requests(False),LocalArtifacts(tmp_path/'artifacts',max_bytes=1024*1024) as store:
            return await run_direct(fixture_case(),stage_models,reviewed_runners(store,tmp_path/'work'))
    result=asyncio.run(run())
    assert corrections==2 and result.attempts[2].stage=='control_authoring'
    assert result.attempts[2].output.status=='drafted' and result.attempts[2].failure is None
    assert len([m for m in result.attempts[2].messages for p in m.parts if p.part_kind=='retry-prompt'])==2
