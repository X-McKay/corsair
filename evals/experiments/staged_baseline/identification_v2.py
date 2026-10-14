"""Corrected operator target-range oracle over unchanged staged-v1 source inputs.

The v1 dataset/runner/report remain intact. This sibling delegates fresh runs to
shared native identification evaluation; optional reassessment makes no requests.
"""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path

from pydantic_evals import Case, Dataset
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.issue_identification.contracts import IssueIdentification
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from evals.issue_identification.evaluate import (
    EvaluationBudget, MatchesSelection, SelectionOracle, evaluate as native_evaluate,
    passed, selection_checks,
)
from .cases import ROOT, identification_input

MANIFEST = ROOT / 'identification-manifest-v2.json'
ARTIFACTS = ('cases-v1.json', 'identification-oracles-v2.json')


def dataset():
    manifest = json.loads(MANIFEST.read_text())
    if set(manifest) != set(ARTIFACTS):
        raise ValueError('unexpected identification-v2 manifest artifacts')
    for name, digest in manifest.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'frozen identification-v2 artifact differs: {name}')
    sources = json.loads((ROOT / 'cases-v1.json').read_text())
    oracles = json.loads((ROOT / 'identification-oracles-v2.json').read_text())
    if set(oracles) != {case['name'] for case in sources}:
        raise ValueError('every frozen source case requires an explicit operator oracle')
    cases = []
    for case in sources:
        oracle = SelectionOracle.model_validate(oracles[case['name']])
        for revision in case['revisions']:
            inputs = IssueAnalysisInput.model_validate(identification_input(case, revision))
            cases.append(Case(name=case['name']+'-'+revision, inputs=inputs, metadata=oracle))
    return Dataset(name='staged-identification-v2', cases=cases, evaluators=[MatchesSelection()])


def identity():
    return {'dataset': 'staged-identification-target-range-v2',
            'dataset_sha256': sha256(MANIFEST.read_bytes()).hexdigest(),
            'source_manifest': json.loads(MANIFEST.read_text()),
            'evaluator_version': 'explicit-target-selection-oracles-v2',
            'evaluator_source_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}


async def evaluate(evidence, *, model=None):
    return await native_evaluate(Path(evidence), EvaluationBudget(repeat=1), model=model,
                                 corpus=dataset(), dataset_identity=identity())


def reassess(report_path, destination):
    """Re-score saved exact inputs/outputs; no model call or new native execution."""
    report_path, destination = Path(report_path), Path(destination)
    captured = report_path.read_bytes()
    report = json.loads(captured)
    cases = {case.name: case for case in dataset().cases}
    if len(report['cases']) != len(cases):
        raise ValueError('reassessment requires every original case exactly once')
    results = []
    seen = set()
    for old in report['cases']:
        name = old['name']
        if name in seen or name not in cases:
            raise ValueError('unknown or repeated original case')
        seen.add(name)
        case = cases[name]
        inputs = IssueAnalysisInput.model_validate_json(json.dumps(old['inputs']))
        if inputs != case.inputs:
            raise ValueError('saved inputs differ from frozen v1 source/task')
        output = IssueIdentification.model_validate_json(json.dumps(old['output']))
        results.append({'name': name, 'original_assertions': old['assertions'],
                        'corrected_assertions': selection_checks(inputs, output, case.metadata),
                        'preserved_output_sha256': sha256(json.dumps(old['output'], sort_keys=True).encode()).hexdigest()})
    result = identity() | {'mode': 'corrected_oracle_reassessment_not_new_model_run',
        'original_report': str(report_path.resolve()), 'original_report_sha256': sha256(captured).hexdigest(),
        'new_model_requests': 0, 'new_native_execution': False,
        'qualification': 'Changed evaluator target-range oracle only; no new agent run or semantic qualification',
        'cases': results}
    with destination.open('x') as stream:
        json.dump(result, stream, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--provider-config', type=Path)
    parser.add_argument('--reassess-report', type=Path)
    parser.add_argument('--reassessment-output', type=Path)
    args = parser.parse_args()
    if args.reassess_report:
        if not args.reassessment_output or args.evidence or args.provider_config:
            parser.error('reassessment requires only --reassess-report and --reassessment-output')
        result = reassess(args.reassess_report, args.reassessment_output)
        print(json.dumps({'mode': result['mode'], 'cases': len(result['cases']),
                          'corrected_passes': sum(all(case['corrected_assertions'].values()) for case in result['cases'])}))
        return
    if args.evidence is None or args.reassessment_output:
        parser.error('fresh evaluation requires --evidence')
    async def run():
        if args.provider_config is None:
            return await evaluate(args.evidence)
        config = load_agent_config(args.provider_config, 'identification')
        async with configured_model(config) as model:
            return await evaluate(args.evidence, model=model)
    report = asyncio.run(run())
    print(json.dumps({'dataset': 'staged-identification-v2', 'cases': len(report.cases), 'passed': passed(report)}))
    if not passed(report):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
