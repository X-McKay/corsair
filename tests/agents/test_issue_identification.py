"""Exercise the narrowed role and wrong-selection counterexamples through native SDK calls."""

import asyncio
from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.exceptions import ToolFailed, UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.issue_analysis.identification import SKILL_TEXT, create_issue_identification_agent, identification_prompt
from corsair.agents.issue_analysis.identification_contracts import IssueIdentificationDraft
from corsair.agents.issue_analysis.tools import FixtureDependencies
from evals.issue_identification.evaluate import EvaluationBudget, dataset, evaluate, passed, scripted_model, selection_checks


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def case():
    return dataset().cases[0]


def ready_draft(inputs):
    return {"status":"ready", "scope":inputs.scope,
            "target":{"symbol":"read_document", "source":{"path":"documents.py","start_line":3,"end_line":4}}, "reason":None}


def run(agent, inputs, **kwargs):
    return agent.run_sync(identification_prompt(inputs), deps=FixtureDependencies(inputs),
                          usage_limits=UsageLimits(request_limit=4, tool_calls_limit=3), **kwargs)


def responding(draft, *, read=True, read_path="documents.py"):
    calls=[]
    async def respond(messages, info):
        calls.append(len(messages))
        assert "sole task" in info.instructions and SKILL_TEXT.strip() in info.instructions
        assert [t.name for t in info.function_tools]==["read_source"]
        if read and len(calls)==1:
            return ModelResponse(parts=[ToolCallPart("read_source", {"path":read_path,"start_line":1})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,draft)])
    return FunctionModel(respond)


def test_native_identification_reads_and_materializes_source_without_labels():
    c=case()
    result=run(create_issue_identification_agent(responding(ready_draft(c.inputs))),c.inputs)
    assert all(selection_checks(c.inputs,result.output,c.metadata).values())
    assert result.output.target.source.quote=="def read_document(root: Path, filename: str) -> str:\n    return (root / filename).read_text()"
    prompt=identification_prompt(c.inputs)
    assert c.inputs.fixture_id not in prompt and c.inputs.source_files[0].content not in prompt
    assert "property_excerpts" not in prompt and "required_lines" not in prompt


@pytest.mark.parametrize("change", [
    {"scope":"application_path"}, {"reported_issue":"The application is vulnerable."},
    {"target":{"symbol":"invented_symbol","source":{"path":"documents.py","start_line":3,"end_line":4}}},
    {"target":{"symbol":"read_document","source":{"path":"other.py","start_line":3,"end_line":4}}},
    {"target":{"symbol":"read_document","source":{"path":"documents.py","start_line":3,"end_line":5}}},
])
def test_finalizer_refuses_scope_report_and_source_inventions(change):
    c=case()
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_identification_agent(responding(ready_draft(c.inputs)|change),output_retries=0),c.inputs)


def test_previous_run_reads_do_not_authorize_selection():
    c=case()
    prior=run(create_issue_identification_agent(responding(ready_draft(c.inputs))),c.inputs)
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_identification_agent(responding(ready_draft(c.inputs),read=False),output_retries=0),c.inputs,
            message_history=prior.all_messages())


@dataclass(frozen=True)
class FailedRead(FixtureDependencies):
    def read_source(self, path, start_line, end_line):
        raise ToolFailed("source unavailable")


def test_failed_read_cannot_authorize_target():
    c=case()
    with pytest.raises(UnexpectedModelBehavior):
        create_issue_identification_agent(responding(ready_draft(c.inputs)),output_retries=0).run_sync(
            identification_prompt(c.inputs),deps=FailedRead(c.inputs))


def test_unsupported_can_abstain_without_inventing_target():
    c=case()
    draft={"status":"unsupported","scope":"component","target":None,
           "reason":"The requested deployment scope is outside the authorized component."}
    result=run(create_issue_identification_agent(responding(draft,read=False)),c.inputs)
    assert result.output.status=="unsupported" and result.output.target is None
    for change in ({"reason":None},{"target":ready_draft(c.inputs)["target"]},{"verdict":"fixed"}):
        with pytest.raises(ValidationError):
            IssueIdentificationDraft.model_validate(draft|change)
    with pytest.raises(ValidationError):
        IssueIdentificationDraft.model_validate(ready_draft(c.inputs)|{"hypothesis":"read succeeds"})


def test_unknown_tool_refused_even_with_output_correction_budget():
    c=case()
    calls=[]
    async def respond(messages,info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart("run_shell", {"command":"echo should-not-run"})])
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_identification_agent(FunctionModel(respond),output_retries=1),c.inputs)
    assert len(calls)==1


def test_curated_evaluator_rejects_wrong_selections_even_when_structurally_valid():
    c=case()
    output=run(create_issue_identification_agent(responding(ready_draft(c.inputs))),c.inputs).output
    # These are not semantic regexes: concrete wrong excerpts, symbols and locations fail frozen expectations.
    bad_report=output.model_copy(update={"reported_issue":"rewritten report"})
    assert not selection_checks(c.inputs,bad_report,c.metadata)["report_identity"]
    bad_symbol=output.model_copy(update={"target":output.target.model_copy(update={"symbol":"Path"})})
    assert not selection_checks(c.inputs,bad_symbol,c.metadata)["target_selection"]
    bad_range=output.model_copy(update={"target":output.target.model_copy(update={"source":output.target.source.model_copy(update={"start_line":1,"end_line":1})})})
    assert not selection_checks(c.inputs,bad_range,c.metadata)["source_range"]
    assert not selection_checks(c.inputs,output.model_copy(update={"status":"missing_information"}),c.metadata)["status"]


def test_native_evals_repeat_and_preserve_receipts(tmp_path):
    evidence=tmp_path/'attempt'
    report=asyncio.run(evaluate(evidence,EvaluationBudget()))
    assert passed(report) and len(report.cases)==16
    assert len(list(evidence.glob('attempt-*.json')))==16
    assert all(c.attributes['input_digest']==c.inputs.input_digest for c in report.cases)
    assert len(report.case_groups())==8
    assert all(c.metrics['requests']==c.attributes['observed_requests'] for c in report.cases)
    assert all(c.metrics['input_tokens']==c.attributes['observed_input_tokens'] for c in report.cases)
    assert report.experiment_metadata['weights_identity']=='not_applicable'
    with pytest.raises(FileExistsError):
        asyncio.run(evaluate(evidence,EvaluationBudget()))


def test_native_task_failure_remains_in_denominator_and_receipt(tmp_path):
    async def unavailable(messages,info):
        raise RuntimeError('scripted provider failure')
    report=asyncio.run(evaluate(tmp_path/'failure',EvaluationBudget(repeat=1),model=FunctionModel(unavailable)))
    assert not passed(report) and len(report.failures)==8
    assert len(list((tmp_path/'failure').glob('attempt-*.json')))==8


def test_native_provider_wire_carries_narrow_schema_skill_and_only_reader():
    import json
    import httpx2
    from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
    c=case()
    bodies=[]
    async def respond(request):
        body=json.loads(request.content); bodies.append(body)
        system=body['messages'][0]['content']
        assert SKILL_TEXT.strip() in system
        assert '"reported_property"' not in system and '"reported_issue"' not in system and '"target"' in system
        assert '"hypothesis"' not in system and '"preconditions"' not in system and '"quote"' not in system
        assert [t['function']['name'] for t in body['tools']]==['read_source']
        assert 'response_format' not in body
        assert body['max_completion_tokens']==8192 and body['parallel_tool_calls'] is False
        if len(bodies)==1:
            message={'role':'assistant','content':None,'tool_calls':[{'id':'read1','type':'function','function':{
                'name':'read_source','arguments':json.dumps({'path':'documents.py','start_line':1})}}]}
            finish='tool_calls'
        else:
            message={'role':'assistant','content':json.dumps(ready_draft(c.inputs))};finish='stop'
        return httpx2.Response(200,json={'id':f'wire-{len(bodies)}','object':'chat.completion','created':1,'model':'test-model',
            'choices':[{'index':0,'finish_reason':finish,'message':message}],
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
    client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    async def exercise():
        async with local_model(LocalModelConfig(server='vllm',base_url='https://llm.example/v1',model_name='test-model',response_token_limit=8192),http_client=client) as model:
            with models.override_allow_model_requests(True):
                result=await create_issue_identification_agent(model).run(identification_prompt(c.inputs),deps=FixtureDependencies(c.inputs))
            assert all(selection_checks(c.inputs,result.output,c.metadata).values())
            assert result.usage.requests==2
    asyncio.run(exercise())
    assert client.is_closed and len(bodies)==2


@pytest.mark.parametrize('line_count,start,expected_end', [(2,1,2),(100,1,80),(100,81,100)])
def test_window_reader_preserves_hard_bound_and_computes_actual_end(line_count,start,expected_end):
    from pydantic_ai.messages import ToolReturnPart
    from corsair.agents.issue_analysis.contracts import SourceRead
    c=case()
    inputs=IssueAnalysisInput.model_validate(c.inputs.model_dump() | {'source_files':[{
        'path':'saved.txt','content':'\n'.join('symbol '+str(i) for i in range(1,line_count+1))+'\n'}]})
    calls=[]
    async def respond(messages,info):
        calls.append(1)
        assert set(info.function_tools[0].parameters_json_schema['properties'])=={'path','start_line'}
        if len(calls)==1:
            return ModelResponse(parts=[ToolCallPart('read_source',{'path':'saved.txt','start_line':start})])
        part=next(p for p in messages[-1].parts if isinstance(p,ToolReturnPart))
        read=SourceRead.model_validate(part.content)
        assert read.start_line==start and read.end_line==expected_end
        assert len(read.lines)<=80 and [x.number for x in read.lines]==list(range(start,expected_end+1))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'status':'ready','scope':'component',
            'target':{'symbol':'symbol','source':{'path':'saved.txt','start_line':start,'end_line':expected_end}},'reason':None})])
    result=run(create_issue_identification_agent(FunctionModel(respond)),inputs)
    assert result.output.target.source.end_line==expected_end


@pytest.mark.parametrize('args', [{'path':'../private','start_line':1},{'path':'absent.py','start_line':1},
                                 {'path':'documents.py','start_line':5},{'path':'documents.py','start_line':0}])
def test_window_reader_refuses_unavailable_source_and_start(args):
    c=case()
    async def respond(messages,info):
        return ModelResponse(parts=[ToolCallPart('read_source',args)])
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_identification_agent(FunctionModel(respond)),c.inputs)


@pytest.mark.parametrize('symbol', ['read_doc', 'document', ' ', ' read_document', 'read_document\n'])
def test_partial_or_whitespace_symbols_cannot_become_ready(symbol):
    c = case()
    draft = ready_draft(c.inputs)
    draft['target']['symbol'] = symbol
    with pytest.raises(UnexpectedModelBehavior):
        run(create_issue_identification_agent(responding(draft), output_retries=0), c.inputs)


@pytest.mark.parametrize('declared,selected,accepted', [
    ('prefix_read_document', 'read_document', False),
    ('read_document_suffix', 'read_document', False),
    ('read_document\u0301', 'read_document', False),
    ('read_document\u093e', 'read_document', False),
    ('read_document\u0301', 'read_document\u0301', True),
    ('read_document£', 'read_document', False),
    ('read_document\u200c', 'read_document', False),
    ('read_document\u200d', 'read_document', False),
    ('read_document£', 'read_document£', True),
    ('read_document\u200c', 'read_document\u200c', True),
    ('read_document\u200d', 'read_document\u200d', True),
    ('αread_document', 'read_document', False),
    ('$read_document', 'read_document', False),
    ('read_document$', 'read_document', False),
    ('read_document', 'read_document', True),
    ('$read_document', '$read_document', True),
    ('read_document?', 'read_document?', True),
])
def test_symbol_occurrence_is_literal_and_has_identifier_boundaries(declared, selected, accepted):
    c = case()
    inputs = IssueAnalysisInput.model_validate(c.inputs.model_dump() | {'source_files': [{
        'path': 'documents.py', 'content': f'def {declared}(root, filename):\n    return filename\n'}]})
    draft = {'status': 'ready', 'scope': inputs.scope, 'target': {
        'symbol': selected, 'source': {'path': 'documents.py', 'start_line': 1, 'end_line': 2}}, 'reason': None}
    agent = create_issue_identification_agent(responding(draft), output_retries=0)
    if accepted:
        assert run(agent, inputs).output.target.symbol == selected
    else:
        with pytest.raises(UnexpectedModelBehavior):
            run(agent, inputs)


def test_curated_evaluator_rejects_fabricated_quote_with_correct_coordinates():
    c = case()
    output = run(create_issue_identification_agent(responding(ready_draft(c.inputs))), c.inputs).output
    fabricated = output.model_copy(update={'target': output.target.model_copy(update={
        'source': output.target.source.model_copy(update={'quote': 'fabricated source'})})})
    assert not selection_checks(c.inputs, fabricated, c.metadata)['source_quote']
