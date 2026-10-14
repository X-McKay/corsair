"""Frozen planning v2 positive transfer fixtures with distinct independent author paths.

Uses the same production planning factory and native evaluation loop. Operator fixture
baseline observations are synthetic; neither native runtime nor composition is qualified.
"""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import yaml
from pydantic_evals import Case, Dataset
from corsair.agents.test_planning.contracts import TestPlanningInput
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from evals.test_planning.evaluate import PlanOracle, EvaluationBudget, evaluate, passed

ROOT=Path(__file__).parent
CASES=ROOT/'planning-cases-v2.yaml'
MANIFEST=ROOT/'planning-manifest-v2.json'


def dataset():
    raw=CASES.read_bytes(); manifest=json.loads(MANIFEST.read_text())
    if sha256(raw).hexdigest()!=manifest['sha256']:
        raise ValueError('frozen planning v2 dataset digest changed')
    # v1 remains attributable; never silently replace the superseded artifact.
    if sha256((ROOT/manifest['supersedes_file']).read_bytes()).hexdigest()!=manifest['supersedes_sha256']:
        raise ValueError('frozen planning v1 differs from the v2 lineage manifest')
    parsed=yaml.safe_load(raw)
    return Dataset(name=parsed['name'], cases=[Case(name=case['name'],
        inputs=TestPlanningInput.model_validate(case['inputs']), metadata=PlanOracle.model_validate(case['metadata']))
        for case in parsed['cases']])


def dataset_identity():
    manifest=json.loads(MANIFEST.read_text())
    return {'dataset':manifest['dataset'],'dataset_sha256':manifest['sha256'],
        'source_manifest':manifest,'evaluator_version':'planning-v2-independent-path-fixtures',
        'evaluator_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}



async def run(evidence, *, model=None, provider=None, repeat=1):
    return await evaluate(Path(evidence),EvaluationBudget(repeat=repeat),model=model,provider=provider,
        corpus=dataset(),dataset_identity=dataset_identity())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--provider-config',type=Path)
    parser.add_argument('--repeat',type=int,choices=(1,),default=1)
    args=parser.parse_args()
    async def selected():
        if args.provider_config is None:return await run(args.evidence,repeat=args.repeat)
        config=load_agent_config(args.provider_config,'planning')
        async with configured_model(config) as model:return await run(args.evidence,model=model,
            provider=config.model_dump(mode='json',exclude={'api_key_env'}),repeat=args.repeat)
    report=asyncio.run(selected());print(json.dumps({'cases':len(report.cases),'failures':len(report.failures),'passed':passed(report)}))
    return 0 if passed(report) else 1

if __name__=='__main__':raise SystemExit(main())
