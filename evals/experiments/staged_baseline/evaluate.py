"""Ordered isolated stage entry point over the frozen development transfer corpus.

Each invocation runs one stage, serially. Scripted responses prove wiring only;
live calls are explicit. No generated probe executes here and no baseline is promoted.
"""
import argparse
import asyncio
from dataclasses import dataclass, asdict
from hashlib import sha256
import importlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from openai import APIConnectionError
from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from evals.native_skills import load_skills
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_evals import Case, Dataset, set_eval_attribute
from evals.issue_analysis.evaluate import describe_model, record_count
from evals.issue_analysis.live import NoUnknownToolAttempts, ProviderUsageCoverage, message_counts, output_tool_names
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from .cases import ROOT, load_cases, identification_input, planning_cases, validity_cases, revision_inputs

STAGES = ('identification', 'planning', 'control_authoring', 'exploit_authoring', 'validity')

@dataclass(frozen=True)
class StageRun:
    corpus: Dataset
    factory: object
    dependencies: object
    prompt: object
    scripted: dict
    identity: dict
    budget: object
    tool_names: frozenset


def identification_stage():
    from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
    from corsair.agents.issue_identification import agent
    from corsair.agents.issue_identification.dependencies import FixtureDependencies
    from evals.issue_identification.evaluate import SelectionOracle, MatchesSelection, scripted_model, EvaluationBudget
    cases = []; scripted = {}
    # Exact operator-selected local symbols, as required by the production occurrence contract.
    symbols = {'javascript_command_boundary':'runReport', 'ruby_command_boundary':'run_report',
               'perl_command_boundary':'run_report', 'java_command_boundary':'runReport'}
    for case in load_cases():
        for revision, captured in case['revisions'].items():
            inputs = IssueAnalysisInput.model_validate(identification_input(case, revision))
            citation = captured['citations'][0]
            oracle = SelectionOracle(status='ready', symbol=symbols[case['name']], path=citation['path'],
                required_lines=tuple(range(citation['start_line'], citation['end_line']+1)))
            cases.append(Case(name=case['name']+'-'+revision, inputs=inputs, metadata=oracle))
            scripted[inputs.model_dump_json()] = scripted_model(inputs, oracle)
    return StageRun(Dataset(name='staged-identification-v1', cases=cases, evaluators=[MatchesSelection()]),
        agent.create_issue_identification_agent, FixtureDependencies, agent.identification_prompt, scripted,
        identity_for(agent), EvaluationBudget(repeat=1), frozenset({'read_source'}))


def planning_stage():
    from corsair.agents.test_planning import agent
    from corsair.agents.test_planning.dependencies import PlanningDependencies
    from evals.test_planning.evaluate import MatchesPlan, ReadBeforePlanning, scripted_model, EvaluationBudget
    cases=[]; scripted={}
    for name, inputs, oracle in planning_cases():
        cases.append(Case(name=name, inputs=inputs, metadata=oracle))
        scripted[inputs.model_dump_json()] = scripted_model(oracle)
    return StageRun(Dataset(name='staged-planning-v1', cases=cases, evaluators=[MatchesPlan(), ReadBeforePlanning()]),
        agent.create_test_planning_agent, PlanningDependencies, agent.planning_prompt, scripted,
        identity_for(agent), EvaluationBudget(repeat=1), frozenset({'read_source'}))


def author_reference(language, role):
    """Operator-curated native fixture probes. These never enter live model inputs."""
    control = role == 'control'
    name = 'quarterly' if control else 'quarterly; echo injected'
    if language == 'javascript':
        content = "const test = require('node:test');\nconst assert = require('node:assert/strict');\nconst { runReport } = require('../commands');\n"
        content += f"test('{ 'benign_control' if control else 'security_safety' }', () => {{\n  let seen;\n  const runner = {{ run(command, shell) {{ seen = {{command, shell}}; return 'sentinel'; }} }};\n  const result = runReport(runner, {json.dumps(name)});\n"
        assertion = "  assert.equal(result, 'sentinel');\n  assert.ok(seen.command === 'report quarterly' || JSON.stringify(seen.command) === JSON.stringify(['report', 'quarterly']));" if control else "  assert.equal(seen.shell, false);\n  assert.deepEqual(seen.command, ['report', 'quarterly; echo injected']);"
        return content + assertion + '\n});\n', (8, 9)
    if language == 'ruby':
        content = "require 'minitest/autorun'\nrequire_relative '../commands'\n"
        content += f"class {'ControlTest' if control else 'ExploitTest'} < Minitest::Test\n  def {'test_benign_control' if control else 'test_security_safety'}\n    seen = nil\n    runner = Object.new\n    runner.define_singleton_method(:run) {{ |command, shell| seen = [command, shell]; 'sentinel' }}\n    result = run_report(runner, {json.dumps(name)})\n"
        assertion = "    assert_equal 'sentinel', result\n    assert_includes ['report quarterly', ['report', 'quarterly']], seen[0]" if control else "    assert_equal false, seen[1]\n    assert_equal ['report', 'quarterly; echo injected'], seen[0]"
        return content + assertion + '\n  end\nend\n', (9, 10)
    if language == 'perl':
        content = "use strict; use warnings;\nuse Test::More;\nuse lib '.';\nuse Commands;\n{ package RecordingRunner; sub new { bless {}, shift } sub run { my ($self,$command,$shell)=@_; $self->{command}=$command; $self->{shell}=$shell; return 'sentinel'; } }\n"
        content += f"subtest '{'benign_control' if control else 'security_safety'}' => sub {{\n  my $runner = RecordingRunner->new;\n  my $result = Commands::run_report($runner, '{name}');\n"
        assertion = "  is($result, 'sentinel');\n  ok(ref($runner->{command}) ? join(' ', @{$runner->{command}}) eq 'report quarterly' : $runner->{command} eq 'report quarterly');" if control else "  ok(!$runner->{shell});\n  is_deeply($runner->{command}, ['report', 'quarterly; echo injected']);"
        return content + assertion + '\n};\ndone_testing;\n', (9, 10)
    if language == 'java':
        content = "package example;\nimport org.junit.jupiter.api.Test;\nimport static org.junit.jupiter.api.Assertions.*;\n"
        content += f"class {'ControlTest' if control else 'ExploitTest'} {{\n  @Test void {'benign_control' if control else 'security_safety'}() {{\n    Object[] seen = new Object[2];\n    Commands.Runner runner = (command, shell) -> {{ seen[0] = command; seen[1] = shell; return \"sentinel\"; }};\n    Object result = Commands.runReport(runner, {json.dumps(name)});\n"
        assertion = '    assertEquals("sentinel", result);\n    assertTrue("report quarterly".equals(seen[0]) || java.util.List.of("report", "quarterly").equals(seen[0]));' if control else '    assertEquals(false, seen[1]);\n    assertEquals(java.util.List.of("report", "quarterly; echo injected"), seen[0]);'
        return content + assertion + '\n  }\n}\n', (9, 10)
    raise ValueError('No operator-curated author reference for language')


def author_script(inputs, content, assertion_lines):
    step=0
    def respond(messages, info):
        nonlocal step
        activation=load_skills(messages, info, ['control-probe' if type(inputs).__name__ == 'ControlInput' else 'exploit-probe', 'native-probe-boundary'])
        if activation is not None:
            return activation
        step += 1
        if step == 1:
            return ModelResponse(parts=[ToolCallPart('read_source',{'path':s.path}) for s in inputs.source_files])
        if step == 2:
            return ModelResponse(parts=[ToolCallPart('write_test_file',{'path':inputs.test_path,'content':content})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'draft':{'status':'drafted',
            'assertion_lines': assertion_lines,'limitations':['Source-only proposed fixture; no native execution or semantic qualification']}})])
    return FunctionModel(respond)


def authoring_stage(role):
    from corsair.agents.probe_authoring.contracts import ControlInput, ExploitInput, ControlPropertyPlan, ExploitPropertyPlan
    from corsair.agents.probe_authoring.dependencies import SpecialistDependencies
    from corsair.agents.source.contracts import SourceFile
    from corsair.agents.test_planning.contracts import EnvironmentEvidence
    from evals.probe_authoring.evaluate import OwnDraft
    from evals.experiments.probe_specialists.evaluate import Budget
    package=importlib.import_module('corsair.agents.'+role+'_authoring')
    agent=importlib.import_module(package.__name__+'.agent')
    cases=[]; scripted={}
    for case in load_cases():
        for revision in case['revisions']:
            captured=revision_inputs(case,revision)
            plan=captured['property_plan']
            boundary={key:plan[key] for key in ('status','scope','condition','dependency_limits','citations')}
            if role=='control':
                property_plan=ControlPropertyPlan(**boundary, control_input=plan['control_input'],ordinary_behavior=case['property']['benign_behavior'])
                cls=ControlInput
            else:
                property_plan=ExploitPropertyPlan(**boundary,adversarial_input=plan['adversarial_input'],safety_property=case['property']['safety_property'])
                cls=ExploitInput
            path=case[role+'_test_path']; env=EnvironmentEvidence.model_validate(captured['environment']|{'approved_test_paths':(path,)})
            inputs=cls(property_plan=property_plan,source_files=tuple(SourceFile.model_validate(s) for s in captured['source_files']),
                environment=env,test_id=case[role+'_test_id'],test_path=path)
            cases.append(Case(name=case['name']+'-'+revision,inputs=inputs))
            content, anchors=author_reference(env.language,role)
            scripted[inputs.model_dump_json()]=author_script(inputs,content,anchors)
    return StageRun(Dataset(name='staged-'+role+'-authoring-v1',cases=cases,evaluators=[OwnDraft()]),
        getattr(package,'create_'+role+'_agent'),SpecialistDependencies,package.prompt_for,scripted,
        identity_for(agent),Budget(),frozenset({'read_source','write_test_file'}))


def validity_stage():
    from corsair.agents.evidence_assessment import agent
    from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
    from evals.evidence_assessment.unit_test import ValidityScore, scripted_model
    from evals.evidence_assessment.evaluate import EvaluationBudget
    raw={c['name']:c for c in json.loads((ROOT/'validity-cases-v1.json').read_text())}
    cases=[];scripted={}
    for name,inputs,expected in validity_cases():
        metadata={'expected':expected,'scripted_review':raw[name]['scripted_review']}
        cases.append(Case(name=name,inputs=inputs,metadata=metadata))
        scripted[inputs.model_dump_json()]=scripted_model(inputs,metadata)
    return StageRun(Dataset(name='staged-validity-v1',cases=cases,evaluators=[ValidityScore()]),
        agent.create_evidence_assessment_agent,AssessmentDependencies,agent.assessment_prompt,scripted,
        identity_for(agent),EvaluationBudget(repeat=1),frozenset({'read_evidence'}))


def identity_for(agent):
    identity = {key.lower():getattr(agent,key) for key in ('PROMPT_VERSION','CONFIG_VERSION','SKILL_SHA256','TOOLSET_SHA256')}
    return identity | getattr(agent, 'MANIFEST_IDENTITY', {})


def stage_run(agent):
    if agent=='identification':return identification_stage()
    if agent=='planning':return planning_stage()
    if agent=='validity':return validity_stage()
    return authoring_stage('control' if agent=='control_authoring' else 'exploit')


def read_paths(messages):
    from pydantic_ai.messages import ToolReturnPart
    from corsair.agents.source.contracts import SourceRead
    paths=set()
    for message in messages:
        for part in message.parts:
            if isinstance(part,ToolReturnPart) and part.tool_name=='read_source' and part.outcome=='success':
                try:
                    paths.add(SourceRead.model_validate(part.content).path)
                except ValueError:
                    # Typed missing-path/past-end observations are not successful source reads.
                    continue
    return sorted(paths)


async def evaluate(agent, evidence, *, model=None, provider=None, repeat=1):
    import logfire
    logfire.configure(send_to_logfire=False,console=False)
    stage=stage_run(agent); evidence=Path(evidence); evidence.mkdir(parents=True,exist_ok=False)
    budget=stage.budget
    budget_data=budget.model_dump() if hasattr(budget,'model_dump') else asdict(budget)
    metadata=stage.identity|{'stage':agent,'mode':'scripted_fixture' if model is None else 'direct_local_provider',
        'model':describe_model(model) if model else 'native FunctionModel','provider':provider,
        'budget':budget_data,'repeat':repeat,'max_concurrency':1,'task_retries':0,
        'evaluator_version':'ordered-staged-isolated-v1','dataset':'staged-development-transfer-v1',
        'dataset_sha256':sha256((ROOT/'manifest-v1.json').read_bytes()).hexdigest(),
        'source_manifest':json.loads((ROOT/'manifest-v1.json').read_text()),
        'factory_source_sha256':sha256(Path(stage.factory.__code__.co_filename).read_bytes()).hexdigest(),
        'evaluator_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'provider_configuration_sha256':sha256(json.dumps(provider,sort_keys=True).encode()).hexdigest() if provider is not None else None,
        'input_schema_sha256':sha256(json.dumps(stage.corpus.cases[0].inputs.model_json_schema(),sort_keys=True).encode()).hexdigest(),
        'execution':'none','qualification':'Isolated source/fixture stage. No generated tests executed, no baseline promoted; scripted scores measure wiring only.'}
    (evidence/'configuration.json').write_text(json.dumps(metadata,indent=2))
    stage.corpus.evaluators.append(NoUnknownToolAttempts())
    if model is not None:stage.corpus.evaluators.append(ProviderUsageCoverage())
    async def task(inputs):
        selected=model if model is not None else stage.scripted[inputs.model_dump_json()]
        known=stage.tool_names|{"load_capability"}|output_tool_names(selected)
        usage=RunUsage();messages=[];result=None;failure=None;started=perf_counter()
        limits=budget.limits(inputs).usage_limits() if agent=='validity' else UsageLimits(request_limit=budget.request_limit,
            tool_calls_limit=budget.tool_calls_limit,total_tokens_limit=budget.total_tokens_limit)
        try:
            with capture_run_messages() as messages,models.override_allow_model_requests(model is not None):
                result=await asyncio.wait_for(stage.factory(selected,output_retries=budget.output_retries).run(
                    stage.prompt(inputs),deps=stage.dependencies(inputs),usage=usage,usage_limits=limits),budget.task_seconds)
            return result.output
        except BaseException as exc:
            failure={'type':type(exc).__name__,'detail':str(exc),
                'uncertain_delivery':isinstance(exc,(TimeoutError,asyncio.CancelledError,APIConnectionError)),
                'cause_type':type(exc.__cause__).__name__ if exc.__cause__ else None,
                'cause_detail':str(exc.__cause__) if exc.__cause__ else None}
            raise
        finally:
            responses=[m for m in messages if isinstance(m,ModelResponse)]
            receipt={'input_digest':sha256(inputs.model_dump_json().encode()).hexdigest(),'input':inputs.model_dump(mode='json'),
                'output':result.output.model_dump(mode='json') if result else None,'failure':failure,
                'elapsed_seconds':perf_counter()-started,'usage_limits':TypeAdapter(UsageLimits).dump_python(limits,mode='json'),
                'timeout_seconds':budget.task_seconds,'output_retries':budget.output_retries,'usage':TypeAdapter(RunUsage).dump_python(usage,mode='json'),
                'usage_source':'scripted_estimate' if model is None else 'native_responses_partial_on_failure',
                'provider_usage_present':None if model is None else bool(responses) and all(m.usage.has_values() for m in responses),
                'response_ids':[m.provider_response_id for m in responses],
                'read_paths':read_paths(messages),'messages':TypeAdapter(list[ModelMessage]).dump_python(messages,mode='json'),
                **message_counts(messages,known)}
            attempt=evidence/f'attempt-{uuid4()}.json';attempt.write_text(json.dumps(receipt,indent=2))
            for key in ('read_paths','unknown_tool_attempts','provider_usage_present'):set_eval_attribute(key,receipt[key])
            set_eval_attribute('receipt',str(attempt))
            for key in ('requests','tool_calls','input_tokens','output_tokens'):record_count('observed_'+key,getattr(usage,key))
    report=await stage.corpus.evaluate(task,repeat=repeat,max_concurrency=1,retry_task=None,metadata=metadata,progress=False)
    (evidence/'report.json').write_bytes(TypeAdapter(type(report)).dump_json(report,indent=2))
    if agent=='validity':
        from evals.evidence_assessment.unit_test import outcome_summary
        (evidence/'outcomes.json').write_text(json.dumps(outcome_summary(report),indent=2))
    return report


def passed(report):
    return bool(report.cases) and not report.failures and not report.report_evaluator_failures and all(
        not case.evaluator_failures and case.assertions and all(a.value for a in case.assertions.values()) for case in report.cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent',choices=STAGES,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--provider-config',type=Path)
    parser.add_argument('--repeat',type=int,choices=(1,),default=1)
    args=parser.parse_args()
    async def run():
        if args.provider_config is None:return await evaluate(args.agent,args.evidence,repeat=args.repeat)
        config=load_agent_config(args.provider_config,'assessment' if args.agent=='validity' else args.agent)
        async with configured_model(config) as model:return await evaluate(args.agent,args.evidence,model=model,
            provider=config.model_dump(mode='json',exclude={'api_key_env'}),repeat=args.repeat)
    report=asyncio.run(run());print(json.dumps({'agent':args.agent,'cases':len(report.cases),'failures':len(report.failures),'passed':passed(report)}))
    return 0 if passed(report) else 1

if __name__=='__main__':raise SystemExit(main())
