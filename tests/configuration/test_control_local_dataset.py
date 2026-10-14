"""Native YAML example preserves frozen inputs and evaluator-only annotations."""
from pathlib import Path
from pydantic_evals import Dataset
from corsair.agents.control_authoring import ControlInput, Drafted, Blocked, prompt_for
from evals.experiments.probe_specialists.cases import load_cases
from evals.experiments.probe_specialists.evaluate import inputs_for

PATH = Path('src/corsair/agents/control_authoring/evals/dataset.yaml')


def test_native_local_dataset_preserves_exact_frozen_inputs_and_label_boundary():
    corpus = Dataset[ControlInput, Drafted | Blocked, dict].from_file(PATH)
    assert len(corpus.cases) == 2
    for case, original in zip(corpus.cases, load_cases()[:2], strict=True):
        expected = ControlInput.model_validate(inputs_for(original, 'reported', 'control').model_dump())
        assert case.inputs.model_dump(mode='json') == expected.model_dump(mode='json')
        assert case.expected_output is None
        assert case.metadata['source_case'] == original['name']
        assert case.metadata['expected_checks']
        rendered = prompt_for(case.inputs)
        assert 'format-only-not-semantic-or-native-execution-baseline' not in rendered
        assert 'ordinary_behavior_real_production_seam' not in rendered
        assert 'source_revision' not in rendered
        assert 'expected_checks' not in rendered
        assert 'adversarial_input' not in case.inputs.model_dump(mode='json')['property_plan']
        case.metadata['expected_checks'] = ['evaluator-only-private-label']
        assert prompt_for(case.inputs) == rendered
