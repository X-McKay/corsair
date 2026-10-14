"""Final assessment over actual reviewed native split fixtures and immutable reviews.

Capture uses the production run_chain typed ports and unchanged native factories.
Only exact operator-reviewed host bytes execute. A separate frozen corpus evaluates
post-execution AssessmentInput; it never mixes source-only ValidityInput into it.
"""
import argparse
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import logfire
from pydantic import BaseModel, ConfigDict
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from evals.native_skills import load_skills
from pydantic_ai.models.function import FunctionModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.evidence_assessment.contracts import AssessmentInput, EvidenceAssessment
from corsair.composition.direct import (AGENTS, CompositionBudget, _invoke, run_chain,
    stage_call, stage_limits, stage_output_retries)
from corsair.composition.progress import ignore
from corsair.core.disposition import Disposition, admit, assess
from evals.evidence_assessment.evaluate import EvaluationBudget, evaluate as native_evaluate, passed, _cited
from evals.fixture_chain.evaluate import ChainInput, ChainOracle, chain_case, chain_runners, scripted_stages
from evals.fixture_e2e.case import scripted_assessment
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from .cases import ROOT

CASES = ROOT / 'assessment-unit-disposition-v2.json'
MANIFEST = ROOT / 'assessment-unit-disposition-manifest-v2.json'
VARIANTS = {'report_then_rejection':('vulnerable','fixed'),
            'rejection_then_report':('fixed','vulnerable'),
            'report_both':('vulnerable','vulnerable'),
            'rejection_both':('fixed','fixed')}


class UnitOracle(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    gate: Disposition
    honest: Disposition
    required_reads: tuple[str, ...]
    receipt_items: dict[str, tuple[str, ...]]
    review_items: tuple[str, ...]


def native_and_review_binding(inputs):
    evidence = inputs.evidence
    if evidence.plan.observation_mode != 'unit_test':
        return False
    expected = {evidence.plan.control_test_id, evidence.plan.security_test_id}
    plan_digest = evidence.plan.review_digest
    try:
        reviews = {json.loads(item.content)['review']['revision']:json.loads(item.content)
                   for item in inputs.items if item.kind=='test_validity'}
    except (ValueError,KeyError,TypeError):
        return False
    for revision in ('baseline', 'candidate'):
        runs = getattr(evidence,revision)
        if len(runs) != 1:
            return False
        run = runs[0]
        validity = run.test_validity
        if (run.delivery != 'acknowledged' or run.completion != 'terminal_observed'
                or set(run.discovered_test_ids) != expected or {o.test_id for o in run.outcomes} != expected
                or len(run.outcomes) != 2 or run.patch_sha256 != evidence.plan.frozen_patch_sha256
                or validity is None or validity.source_sha256 != run.source_sha256
                or validity.observation_plan_sha256 != plan_digest
                or reviews.get(revision,{}).get('bound_validity') != validity.model_dump(mode='json')
                or any(outcome.outcome not in ('passed','failed') for outcome in run.outcomes)
                or next(outcome for outcome in run.outcomes if outcome.test_id==evidence.plan.control_test_id).outcome != 'passed'
                or not all((validity.source_linked, validity.condition_exercised,
                            validity.assertions_relevant, validity.dependency_scope_valid))):
            return False
    return True


@dataclass
class ScoredUnitDisposition(Evaluator[AssessmentInput, EvidenceAssessment, UnitOracle]):
    def evaluate(self, ctx):
        inputs, output, oracle = ctx.inputs, ctx.output, ctx.metadata
        result = assess(inputs.evidence)
        proposal = Disposition(execution=output.execution,finding=output.finding,fix=output.fix)
        cited = _cited(output)
        required_revisions = {'baseline'} if proposal.finding in ('reproduced','not_reproduced') else set()
        if proposal.fix == 'verified':
            required_revisions.add('candidate')
        return {'contract':output.admission == admit(proposal,result) and output.gate_limitations == result.limitations,
                'admitted':output.admission.admitted, 'calibrated':proposal == oracle.gate,
                'actual_native_pair_bound':native_and_review_binding(inputs),
                'immutable_review_preserved':output.evidence == inputs.evidence,
                'unit_receipt_grounded':all(set(oracle.receipt_items[revision]) & cited for revision in required_revisions),
                'frozen_review_read':set(oracle.review_items) <= set(ctx.attributes.get('read_items') or ())}


def artifact_paths(version='v2'):
    if version not in ('v1','v2'):
        raise ValueError('unknown frozen unit disposition version')
    return (ROOT / f'assessment-unit-disposition-{version}.json',
            ROOT / f'assessment-unit-disposition-manifest-{version}.json')


def dataset(version='v2'):
    cases_path,manifest_path=artifact_paths(version)
    manifest = json.loads(manifest_path.read_text())
    if set(manifest) != {cases_path.name} or sha256(cases_path.read_bytes()).hexdigest() != manifest[cases_path.name]:
        raise ValueError('frozen unit disposition corpus differs from manifest')
    frozen = json.loads(cases_path.read_text())
    cases=[]
    for case in frozen['cases']:
        inputs = AssessmentInput.model_validate_json(json.dumps(case['inputs']))
        oracle = UnitOracle.model_validate_json(json.dumps(case['metadata']))
        if not native_and_review_binding(inputs) or assess(inputs.evidence).permitted != oracle.gate:
            raise ValueError('captured native outcomes/review or operator gate differ')
        cases.append(Case(name=case['name'],inputs=inputs,metadata=oracle))
    return Dataset(name=f'assessment-unit-disposition-{version}',cases=cases,evaluators=[ScoredUnitDisposition()])


async def capture(version='v2'):
    """Four bounded production routes using scripted models and real reviewed bytes."""
    cases_path,manifest_path=artifact_paths(version)
    if cases_path.exists() or manifest_path.exists():
        raise FileExistsError('unit disposition corpus is already frozen')
    logfire.configure(send_to_logfire=False,console=False)
    budget = CompositionBudget()
    captured=[]
    with TemporaryDirectory(prefix='corsair-unit-disposition-capture-') as temporary:
        root=Path(temporary)
        for name,(baseline,candidate) in VARIANTS.items():
            location=root/name;location.mkdir(); (location/'objects').mkdir(mode=0o700);(location/'work').mkdir(mode=0o700)
            # Oracle gate is independently prescribed for the known fixture mapping.
            finding='reproduced' if baseline=='vulnerable' else 'not_reproduced'
            fix='verified' if baseline=='vulnerable' and candidate=='fixed' else 'not_verified'
            oracle_gate=Disposition(execution='completed',finding=finding,fix=fix)
            inputs=ChainInput(revisions={'development':baseline,'baseline':baseline,'candidate':candidate},source='saved')
            fixture=chain_case(inputs)
            selected=scripted_stages(inputs,ChainOracle(stopped_at=None,gate=oracle_gate,assessment_admitted=True))
            final_inputs=[]
            async def invoke(stage, stage_inputs):
                if isinstance(stage_inputs,AssessmentInput):
                    final_inputs.append(stage_inputs)
                agent=AGENTS[stage](selected[stage],output_retries=stage_output_retries(stage,budget))
                prompt,deps=stage_call(stage,stage_inputs,budget,None)
                return await _invoke(stage,agent,prompt,deps,stage_limits(stage,stage_inputs,budget),ignore)
            async def select(_):
                raise AssertionError('declared reviewed fixture must not select a runtime')
            with LocalArtifacts(location/'objects',max_bytes=4*1024*1024) as store:
                runners=chain_runners(store,location/'work',inputs.revisions)
                async def execute(revision,patch,**request):
                    return runners(revision).run(patch,**request)
                with models.override_allow_model_requests(False):
                    run=await run_chain(fixture,invoke,execute,select,new_operation=uuid4)
                if run.stopped_at is not None or len(final_inputs)!=1 or run.gate.permitted != oracle_gate:
                    raise ValueError(f'fixture capture failed {name}: {run.reason}')
                if not all(execution.observed.cleanup=='confirmed' for execution in run.executions):
                    raise ValueError('fixture cleanup not confirmed')
                final=final_inputs[0]
                receipts={revision:tuple(item.item_id for item in final.items if item.kind=='receipt' and item.revision==revision)
                          for revision in ('baseline','candidate')}
                review_items=tuple(item.item_id for item in final.items if item.kind=='test_validity')
                metadata=UnitOracle(gate=oracle_gate,honest=oracle_gate,required_reads=tuple(item.item_id for item in final.items),
                                    receipt_items=receipts,review_items=review_items)
                captured.append({'name':name,'inputs':final.model_dump(mode='json'),'metadata':metadata.model_dump(mode='json'),
                                 'native_capture':{'revision_runs':2,'per_probe_outcomes':4,'cleanup':'confirmed'}})
    data={'version':f'assessment-unit-disposition-{version}','provenance':{'mode':'production_run_chain_typed_port_capture',
          'models':'native FunctionModel; no provider requests','native_execution':'exact operator-reviewed host reference bytes',
          'semantic_review':'scripted outcome-blind fixture review; not production validity calibration',
          'capture_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
          'fixture_source_sha256':sha256(Path(scripted_assessment.__code__.co_filename).read_bytes()).hexdigest()},'cases':captured}
    with cases_path.open('x') as stream:json.dump(data,stream,indent=2)
    with manifest_path.open('x') as stream:json.dump({cases_path.name:sha256(cases_path.read_bytes()).hexdigest()},stream,indent=2)
    dataset(version) # Check the frozen production input, native pair and independent oracle binding.
    return data


def scripted_final_model(inputs, oracle):
    """Read each actual frozen item and cite native receipts, never a witness-only oracle."""
    items = tuple(item.item_id for item in inputs.items)
    async def respond(messages, info):
        activation = load_skills(messages, info, ['assess-evidence'])
        if activation is not None:
            return activation
        done = sum(isinstance(part, ToolReturnPart) and part.tool_name == "read_evidence" for message in messages for part in message.parts)
        if done < len(items):
            return ModelResponse(parts=[ToolCallPart('read_evidence', {'item_id':items[done]})])
        def citation(item_id):
            return {'item_id':item_id,'start_line':1,'end_line':1}
        receipts = [item for item in inputs.items if item.kind=='receipt']
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            'execution':oracle.honest.execution,'finding':oracle.honest.finding,'fix':oracle.honest.fix,
            'application_observations':[{'statement':'Native outcomes of both planned probes on '+item.revision,
                'citations':[citation(item.item_id)]} for item in receipts],
            'sandbox_observations':[],
            'interpretation':{'statement':'Frozen unit validity and both native probe outcomes support the scoped disposition',
                'citations':[citation(item.item_id) for item in receipts]},
            'limitations':['Scripted final disposition plumbing over actual reviewed fixture observations; not live interpretation qualification']})])
    return FunctionModel(respond)


async def evaluate(evidence, *, model=None, version='v2'):
    corpus=dataset(version)
    cases_path,manifest_path=artifact_paths(version)
    scripted={case.name:scripted_final_model(case.inputs,case.metadata) for case in corpus.cases}
    identity={'dataset':f'assessment-unit-disposition-{version}','dataset_sha256':sha256(manifest_path.read_bytes()).hexdigest(),
              'source_manifest':json.loads(manifest_path.read_text()),'evaluator_version':'unit-native-pair-disposition-v2',
              'evaluator_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
              'witness_record_schema':'not_required_unit_observation', 'execution':'captured_actual_reviewed_fixture_outcomes',
              'qualification':'Isolated final AssessmentInput reasoning; scripted source review does not calibrate production validity'}
    return await native_evaluate(Path(evidence),EvaluationBudget(repeat=1,task_seconds=600),model=model,scripted=scripted,
                                 corpus=corpus,dataset_identity=identity)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--version',choices=('v1','v2'),default='v2')
    parser.add_argument('--repeat',type=int,choices=(1,),default=1)
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--provider-config',type=Path)
    args=parser.parse_args()
    async def run():
        if args.capture:
            if args.evidence or args.provider_config:parser.error('capture has no provider or model evaluation')
            data=await capture(args.version);print(json.dumps({'captured_cases':len(data['cases']),'native_probe_outcomes':16}));return
        if args.evidence is None:parser.error('evaluation requires fresh --evidence')
        if args.provider_config is None:report=await evaluate(args.evidence,version=args.version)
        else:
            config=load_agent_config(args.provider_config,'assessment')
            async with configured_model(config) as model:report=await evaluate(args.evidence,model=model,version=args.version)
        print(json.dumps({'cases':len(report.cases),'passed':passed(report)}))
        if not passed(report):raise SystemExit(1)
    asyncio.run(run())


if __name__=='__main__':main()
