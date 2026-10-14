"""Isolated native draft evaluation; frozen pilot data is wiring evidence, not a promoted baseline."""
import argparse
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator
from corsair.agents.probe_authoring.contracts import ControlInput, ExploitInput
from corsair.agents.probe_authoring.dependencies import SpecialistDependencies
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from evals.experiments.probe_specialists.cases import load_cases, reference_patches, ROOT
from evals.experiments.probe_specialists.evaluate import Budget, inputs_for
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names

def scripted_model(case, inputs, role):
    content = reference_patches()[case['name']][inputs.test_path]
    assertion_lines = tuple(i for i, line in enumerate(content.splitlines(), 1)
        if line.lstrip().startswith('assert ') or line.lstrip().startswith('with pytest.raises('))
    step = 0
    def respond(messages, info):
        nonlocal step
        step += 1
        if step == 1:
            return ModelResponse(parts=[ToolCallPart('read_source', {'path':s.path}) for s in inputs.source_files])
        if step == 2:
            return ModelResponse(parts=[ToolCallPart('write_test_file', {'path':inputs.test_path,'content':content})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'draft':{
            'status':'drafted','limitations':['Proposed only; separate source review and native execution required'],
            'assertion_lines': assertion_lines}})])
    return FunctionModel(respond)

class OwnDraft(Evaluator):
    def evaluate(self, ctx):
        output = ctx.output
        return {'draft_completed': output.status == 'drafted',
                'input_bound': output.input_digest == ctx.inputs.input_digest,
                'own_path': len(output.files) == 1 and output.files[0].path == ctx.inputs.test_path,
                'read_anchors_bound': getattr(output, 'read_anchors', ()) == ctx.inputs.property_plan.citations,
                'assertion_anchors_bound': bool(getattr(output, 'assertion_anchors', ())) and all(
                    anchor.path == ctx.inputs.test_path and anchor.start_line == anchor.end_line
                    and anchor.start_line in output.assertion_lines
                    and anchor.quote == output.files[0].content.splitlines()[anchor.start_line-1]
                    for anchor in output.assertion_anchors)}

async def evaluate(role, evidence, *, model=None, provider=None, repeat=1, budget=Budget()):
    import importlib
    package=importlib.import_module('corsair.agents.'+role+'_authoring')
    prompts=importlib.import_module(package.__name__+'.prompts')
    factory_module=importlib.import_module(package.__name__+'.agent')
    tools=importlib.import_module(package.__name__+'.tools')
    factory=getattr(package, 'create_'+role+'_agent')
    cls=ControlInput if role=='control' else ExploitInput
    import logfire
    logfire.configure(send_to_logfire=False, console=False)
    evidence=Path(evidence); evidence.mkdir(parents=True, exist_ok=False)
    fixture_cases={}; cases=[]
    for case in load_cases():
        for revision in case['revisions']:
            inputs=cls.model_validate(inputs_for(case, revision, role).model_dump())
            fixture_cases[inputs.input_digest]=case
            cases.append(Case(name=case['name']+'-'+revision, inputs=inputs))
    metadata={'prompt_version':prompts.PROMPT_VERSION,'config_version':factory_module.CONFIG_VERSION,
        'skill_sha256':prompts.SKILL_SHA256,'toolset_sha256':tools.TOOLSET_SHA256,
        'evaluator_version':'independent-probe-author-wiring-v1','dataset':'frozen-parent-python-v1','dataset_sha256':sha256((ROOT/'cases-v1.json').read_bytes()).hexdigest(),
        'mode':'scripted_fixture' if model is None else 'direct_local_provider',
        'model':'native FunctionModel' if model is None else describe_model(model), 'provider':provider,
        'budget':asdict(budget),'max_concurrency':1,'execution':'none',
        'qualification':'Draft plumbing only. Four frozen Python cases; no semantic qualification or baseline promotion.'}
    metadata |= factory_module.MANIFEST_IDENTITY
    (evidence/'configuration.json').write_text(json.dumps(metadata,indent=2))
    corpus=Dataset(name=role+'-frozen-parent-v1',cases=cases,evaluators=[OwnDraft(),NoUnknownToolAttempts()])
    if model is not None: corpus.evaluators.append(ProviderUsageCoverage())
    async def task(inputs):
        selected=model if model is not None else scripted_model(fixture_cases[inputs.input_digest],inputs,role)
        agent=factory(selected,output_retries=budget.output_retries)
        usage=RunUsage(); messages=[]; result=None; failure=None; started=perf_counter()
        known_tools=frozenset({'read_source','write_test_file'})|output_tool_names(selected)
        try:
            with capture_run_messages() as messages, models.override_allow_model_requests(model is not None):
                result=await asyncio.wait_for(agent.run(package.prompt_for(inputs),deps=SpecialistDependencies(inputs),
                    usage=usage,usage_limits=UsageLimits(request_limit=budget.request_limit,
                    tool_calls_limit=budget.tool_calls_limit,total_tokens_limit=budget.total_tokens_limit)),budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure={'type':type(exc).__name__,'detail':str(exc),
                'uncertain_delivery': isinstance(exc,(TimeoutError,asyncio.CancelledError)),
                'cause_type':type(exc.__cause__).__name__ if exc.__cause__ else None,
                'cause_detail':str(exc.__cause__) if exc.__cause__ else None}
            raise
        finally:
            responses=[m for m in messages if isinstance(m,ModelResponse)]
            receipt={'input_digest':inputs.input_digest,'input':inputs.model_dump(mode='json'),
                'output':result.output.model_dump(mode='json') if result else None,'failure':failure,
                'usage':TypeAdapter(RunUsage).dump_python(usage,mode='json'),
                'usage_source':'scripted_estimate' if model is None else 'native_responses_partial_on_failure',
                'provider_usage_present':None if model is None else bool(responses) and all(m.usage.has_values() for m in responses),
                'elapsed_seconds':perf_counter()-started,'messages':TypeAdapter(list[ModelMessage]).dump_python(messages,mode='json'),
                **message_counts(messages,known_tools)}
            attempt=evidence/f'attempt-{uuid4()}.json';attempt.write_text(json.dumps(receipt,indent=2))
            for key in ('unknown_tool_attempts','provider_usage_present'):set_eval_attribute(key,receipt[key])
            set_eval_attribute('receipt',str(attempt))
            for key,value in [('requests',usage.requests),('tool_calls',usage.tool_calls),('input_tokens',usage.input_tokens),('output_tokens',usage.output_tokens)]:record_count('observed_'+key,value)
    report=await corpus.evaluate(task,repeat=repeat,max_concurrency=1,retry_task=None,metadata=metadata,progress=False)
    (evidence/'report.json').write_bytes(TypeAdapter(type(report)).dump_json(report,indent=2))
    return report

def main(role):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--provider-config',type=Path)
    parser.add_argument('--repeat',type=int,choices=(1,2,3),default=1)
    args=parser.parse_args()
    async def run():
        if args.provider_config is None:return await evaluate(role,args.evidence,repeat=args.repeat)
        config=load_agent_config(args.provider_config,role+'_authoring')
        async with configured_model(config) as model:return await evaluate(role,args.evidence,model=model,provider=config.model_dump(mode='json',exclude={'api_key_env'}),repeat=args.repeat)
    report=asyncio.run(run())
    passed=bool(report.cases) and not report.failures and not report.report_evaluator_failures and all(not c.evaluator_failures and c.assertions and all(a.value for a in c.assertions.values()) for c in report.cases)
    print(json.dumps({'cases':len(report.cases),'passed':passed}))
    return 0 if passed else 1
