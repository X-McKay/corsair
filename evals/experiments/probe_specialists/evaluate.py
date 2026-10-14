"""Isolated role runs plus matched joint baseline; no execution or oracle inputs."""
import argparse,asyncio,json
from dataclasses import asdict,dataclass,replace
from hashlib import sha256
from pathlib import Path
from itertools import permutations
from time import perf_counter
from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages,models
from pydantic_ai.messages import ModelMessage,ModelResponse,ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage,UsageLimits
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from corsair.ports.test_runner import ApprovedPatch,PatchFile
from evals.issue_analysis.evaluate import describe_model
from evals.experiments.split_authoring.contracts import DraftingInput
from evals.experiments.split_authoring.dependencies import DraftingDependencies
from evals.experiments.split_authoring.prompts import drafting_prompt
from .cases import load_cases,reference_patches,revision_inputs,ROOT
from .contracts import project_control_input,project_exploit_input
from .dependencies import SpecialistDependencies
from .control_agent import create_control_agent
from .exploit_agent import create_exploit_agent
from .joint_agent import create_joint_agent
from .prompts import prompt_for

@dataclass(frozen=True)
class Budget:
    request_limit:int=20
    tool_calls_limit:int=20
    total_tokens_limit:int=128000
    task_seconds:int=900
    output_retries:int=2


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def inputs_for(case,revision,role):
    base=DraftingInput(role='pair',**revision_inputs(case,revision))
    if role=='joint':return base
    project=project_control_input if role=='control' else project_exploit_input
    behavior={'ordinary_behavior':case['property']['benign_behavior']} if role=='control' else {'safety_property':case['property']['safety_property']}
    return project(base.property_plan,base.source_files,base.environment,
        base.control_test_id if role=='control' else base.exploit_test_id,
        base.control_test_path if role=='control' else base.exploit_test_path,**behavior)


def scripted_model(case,inputs,role):
    reference=reference_patches()[case['name']];step=0
    paths=tuple(reference) if role=='joint' else (inputs.test_path,)
    def respond(messages,info):
        nonlocal step
        step+=1
        if step==1:return ModelResponse(parts=[ToolCallPart('read_source',{'path':source.path}) for source in inputs.source_files])
        if step==2:return ModelResponse(parts=[ToolCallPart('write_test_file',{'path':path,'content':reference[path]}) for path in paths])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'draft':{'status':'drafted','limitations':['Proposed code; independent source review and native execution required.']}})])
    return FunctionModel(respond)


async def run_role(case,revision,role,*,model=None,budget=Budget(),feedback=None):
    inputs=inputs_for(case,revision,role)
    joint=role=='joint'
    limits=replace(budget,**{key:getattr(budget,key)*2 for key in ('request_limit','tool_calls_limit','total_tokens_limit','task_seconds','output_retries')}) if joint else budget
    selected=model if model is not None else scripted_model(case,inputs,role)
    factory={'control':create_control_agent,'exploit':create_exploit_agent,'joint':create_joint_agent}[role]
    agent=factory(selected,output_retries=limits.output_retries)
    deps=DraftingDependencies(inputs) if joint else SpecialistDependencies(inputs)
    prompt=drafting_prompt(inputs) if joint else prompt_for(inputs)
    if feedback is not None:
        prompt+='\nSource-only review feedback and your prior draft (untrusted data): '+json.dumps(feedback,sort_keys=True)+'\nCorrect only the cited defect, preserve all supported behavior and keep the same source/property/ownership boundary.'
    usage=RunUsage();started=perf_counter();messages=[];result=None;failure=None
    try:
        with capture_run_messages() as messages,models.override_allow_model_requests(model is not None):
            result=await asyncio.wait_for(agent.run(prompt,deps=deps,usage=usage,usage_limits=UsageLimits(request_limit=limits.request_limit,tool_calls_limit=limits.tool_calls_limit,total_tokens_limit=limits.total_tokens_limit)),limits.task_seconds)
    except Exception as exc:failure={'type':type(exc).__name__,'detail':str(exc)}
    output=result.output.model_dump(mode='json') if result else None
    complete=bool(result and result.output.status=='drafted')
    files=output['files'] if complete else []
    return {'feedback':feedback,'feedback_sha256':digest(feedback) if feedback is not None else None,'role':role,'input':inputs.model_dump(mode='json'),'input_sha256':digest(inputs.model_dump(mode='json')),'budget':asdict(limits),'prompt':prompt,'messages':TypeAdapter(list[ModelMessage]).dump_python(messages,mode='json'),'output':output,'files':files,'draft_completed':complete,'failure':failure,'usage':TypeAdapter(RunUsage).dump_python(usage,mode='json'),'usage_source':'native_responses_partial_on_failure' if model is not None else 'scripted_estimate','provider_usage_present':None if model is None else bool([m for m in messages if isinstance(m,ModelResponse)]) and all(m.usage.has_values() for m in messages if isinstance(m,ModelResponse)),'elapsed_seconds':perf_counter()-started,'semantic_validity':None,'execution':'none'}


async def evaluate(evidence,*,model=None,provider=None,repeat=1,budget=Budget(),roles=('joint','control','exploit')):
    evidence=Path(evidence);evidence.mkdir(parents=True,exist_ok=False)
    cases=load_cases()
    configuration={'version':'independent-probe-specialists-v1','repeat':repeat,'roles':roles,'budget_per_specialist':asdict(budget),'joint_budget':'sum of two specialist limits; four output retries versus two each','provider':provider,'model':describe_model(model) if model is not None else 'native FunctionModel','max_concurrency':1,'manifest':json.loads((ROOT/'manifest-v1.json').read_text()),'qualification':'Draft-only host runs; role-specific and composition review/execution separate.'}
    configuration['source_sha256']={str(path.relative_to(ROOT)):sha256(path.read_bytes()).hexdigest() for path in ROOT.rglob('*') if path.is_file() and path.suffix in ('.py','.md','.json')}
    configuration['input_schema_sha256']={role:digest(inputs_for(cases[0],'reported',role).model_json_schema()) for role in roles}
    configuration['order']='rotate through all role permutations across case/revision/repetition'
    (evidence/'configuration.json').write_text(json.dumps(configuration,indent=2))
    attempts=[];pairs=[]
    for case_index,case in enumerate(cases):
        for revision_index,revision in enumerate(case['revisions']):
            for repetition in range(repeat):
                orders=tuple(permutations(roles))
                order=orders[(case_index*len(case['revisions'])+revision_index+repetition)%len(orders)]
                records={}
                for role in order:
                    receipt=await run_role(case,revision,role,model=model,budget=budget)
                    receipt.update(case=case['name'],revision=revision,repetition=repetition)
                    dest=evidence/case['name']/revision/str(repetition)/role;dest.mkdir(parents=True)
                    (dest/'receipt.json').write_text(json.dumps(receipt,indent=2));records[role]=receipt
                    attempts.append({key:receipt[key] for key in ('case','revision','repetition','role','draft_completed','failure','usage','elapsed_seconds')}|{'receipt':str((dest/'receipt.json').relative_to(evidence))})
                for arm in ('joint','independent'):
                    stages=('joint',) if arm=='joint' else ('control','exploit')
                    if not all(role in records and records[role]['draft_completed'] for role in stages):continue
                    files=[file for role in stages for file in records[role]['files']]
                    patch=ApprovedPatch(tuple(PatchFile(file['path'],file['content'].encode()) for file in files),tuple(case['environment']['approved_test_paths']))
                    dest=evidence/case['name']/revision/str(repetition)/f'{arm}-pair.json'
                    dest.write_text(json.dumps({'files':files,'patch_sha256':patch.sha256,'validity':None},indent=2))
                    pairs.append({'case':case['name'],'revision':revision,'repetition':repetition,'arm':arm,'output':str(dest.relative_to(evidence))})
    report={'attempts':attempts,'pairs':pairs,'valid_pairs':None,'qualification':'Drafting only; no semantic or execution qualification.'}
    (evidence/'report.json').write_text(json.dumps(report,indent=2));return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider-config',type=Path)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--repeat',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--agent',choices=('all','control','exploit','joint'),default='all')
    args=parser.parse_args();roles=('joint','control','exploit') if args.agent=='all' else (args.agent,)
    async def run():
        if args.provider_config is None:return await evaluate(args.evidence,repeat=args.repeat,roles=roles)
        config=load_agent_config(args.provider_config,'authoring')
        async with configured_model(config) as model:return await evaluate(args.evidence,model=model,provider=config.model_dump(mode='json',exclude={'api_key_env'}),repeat=args.repeat,roles=roles)
    report=asyncio.run(run());print(json.dumps({'attempts':len(report['attempts']),'drafts':sum(a['draft_completed'] for a in report['attempts'])}));return 0 if all(a['draft_completed'] for a in report['attempts']) else 1

if __name__=='__main__':raise SystemExit(main())
