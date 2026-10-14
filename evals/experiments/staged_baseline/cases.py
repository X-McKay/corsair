"""Operator-owned projections: no paired source, oracle or execution claim enters input."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load_cases():
    manifest = json.loads((ROOT / 'manifest-v1.json').read_text())
    for name, digest in manifest.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'frozen staged artifact differs: {name}')
    return json.loads((ROOT / 'cases-v1.json').read_text())


def revision_inputs(case, revision):
    """Return author fixture input, leaving native baseline unavailable until measured.

    This is a proposed source-only property fixture. It must not be promoted to
    qualified environment evidence by inventing an executed baseline.
    """
    captured, property_ = case['revisions'][revision], case['property']
    return deepcopy({
        'property_plan': {'status': 'ready', 'scope': 'component',
            'condition': property_['condition'], 'control_input': property_['control_input'],
            'adversarial_input': property_['adversarial_input'],
            'security_property': property_['benign_behavior'] + ' ' + property_['safety_property'],
            'dependency_limits': property_['dependency_limits'], 'citations': captured['citations']},
        'source_files': captured['source_files'],
        **{key: case[key] for key in ('environment', 'control_test_id', 'control_test_path',
                                     'exploit_test_id', 'exploit_test_path')}})


def identification_input(case, revision):
    captured = case['revisions'][revision]
    return deepcopy({'fixture_id': 'staged-' + case['name'], 'issue': case['property']['condition'],
                     'scope': 'component', 'source_files': captured['source_files']})


def development_corpus_inputs():
    """One existing development-only case per Python/JS/Java/Perl language.

    Reuse upstream-checked source and source attribution instead of copying or
    exposing held-out ids. These identification inputs carry no native baseline.
    """
    from evals.corpus.cases import load, agent_input
    chosen = {}
    for case in load():
        if case.split == 'development' and case.language in {'python', 'javascript', 'java', 'perl'}:
            chosen.setdefault(case.language, case)
    return tuple(agent_input(case) for case in chosen.values())


def planning_cases():
    """Typed positive planning fixture inputs plus separate operator PlanOracle."""
    import yaml
    from corsair.agents.test_planning.contracts import TestPlanningInput
    from evals.test_planning.evaluate import PlanOracle
    load_cases()
    return tuple((case['name'], TestPlanningInput.model_validate_json(json.dumps(case['inputs'])),
                  PlanOracle.model_validate(case['metadata']))
                 for case in yaml.safe_load((ROOT / 'planning-cases-v1.yaml').read_text())['cases'])


def validity_cases():
    """Reuse frozen outcome-blind multilingual validity inputs; labels stay separate."""
    from corsair.agents.evidence_assessment.contracts import ValidityInput
    load_cases()
    return tuple((case['name'], ValidityInput.model_validate_json(json.dumps(case['inputs'])), case['expected'])
                 for case in json.loads((ROOT / 'validity-cases-v1.json').read_text()))


def environment_cases():
    """Recorded deterministic port responses, never host setup execution."""
    load_cases()
    return json.loads((ROOT / 'environment-cases-v1.json').read_text())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Export source-only staged fixture inputs; never calls models')
    parser.add_argument('--stage', choices=['environment', 'identification', 'planning', 'validity'], required=True)
    args = parser.parse_args()
    if args.stage == 'planning':
        output = [{'name':name, 'inputs':inputs.model_dump(mode='json'), 'metadata':oracle.model_dump(mode='json')}
                  for name, inputs, oracle in planning_cases()]
    elif args.stage == 'validity':
        output = [{'name':name, 'inputs':inputs.model_dump(mode='json'), 'expected':expected}
                  for name, inputs, expected in validity_cases()]
    elif args.stage == 'environment':
        output = environment_cases()
    else:
        output = [inputs.model_dump(mode='json') for inputs in development_corpus_inputs()]
    print(json.dumps(output, indent=2))
