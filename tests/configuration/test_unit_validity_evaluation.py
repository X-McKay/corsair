"""Freeze semantic validity cases and check evaluator sensitivity to unsafe blanket approval."""
import json
from hashlib import sha256
from types import SimpleNamespace

from evals.evidence_assessment.unit_test import CASES, FLAGS, ValidityScore, dataset


def test_unit_validity_case_manifest_is_frozen():
    cases = json.loads(CASES.read_text())
    actual = {case['name']: sha256(json.dumps(case, sort_keys=True).encode()).hexdigest() for case in cases}
    expected = json.loads(CASES.with_name('unit_test_manifest_v2.json').read_text())
    assert actual == expected


def test_blanket_validity_approval_fails_every_negative_case():
    cases = dataset().cases
    assert len(cases) == 7
    output = SimpleNamespace(validity_reviews=[SimpleNamespace(revision='baseline', **dict.fromkeys(FLAGS, True))],
        evidence=None, gate_result=None, bound_validity={'baseline': SimpleNamespace(**dict.fromkeys(FLAGS, True))})
    scores = {case.name: ValidityScore().evaluate(SimpleNamespace(output=output, metadata=case.metadata))
              for case in cases}
    assert scores['real-seam-return-and-exception']['semantic_validity']
    assert all(not score['semantic_validity'] for name, score in scores.items()
               if name != 'real-seam-return-and-exception')


def test_classification_keeps_false_approval_and_rejection_separate():
    from evals.evidence_assessment.unit_test import review_classification, outcome_summary
    def output(**flags):
        return SimpleNamespace(bound_validity={'baseline': SimpleNamespace(**(dict.fromkeys(FLAGS, True) | flags))})
    assert review_classification(output(), {'source_linked': False}) == 'dangerous_false_approval'
    assert review_classification(output(source_linked=False), {'source_linked': False}) == 'correct_rejection'
    assert review_classification(output(assertions_relevant=False), {'source_linked': False}) == 'rejection_wrong_reason'
    assert review_classification(output(source_linked=False), dict.fromkeys(FLAGS, True)) == 'false_rejection'
    report = SimpleNamespace(cases=[], failures=[SimpleNamespace(error_message='UnexpectedModelBehavior: Exceeded maximum output retries (1)'),
        SimpleNamespace(error_message='TimeoutError')], report_evaluator_failures=[])
    assert outcome_summary(report)['outcomes'] == {'contract_failure': 1, 'task_failure': 1}
    report = SimpleNamespace(cases=[SimpleNamespace(evaluator_failures=['bug'], labels={})], failures=[], report_evaluator_failures=[])
    assert outcome_summary(report)['outcomes'] == {'evaluator_defect': 1}


def test_original_validity_dataset_remains_frozen():
    path = CASES.with_name('unit_test_cases.json')
    original = json.loads(path.read_text())
    assert {case['name']: sha256(json.dumps(case, sort_keys=True).encode()).hexdigest() for case in original} == json.loads(path.with_name('unit_test_manifest.json').read_text())


def test_successor_retains_original_semantic_inputs_and_oracles():
    old = json.loads(CASES.with_name('unit_test_cases.json').read_text())
    new = json.loads(CASES.read_text())
    assert [(c['name'], c['inputs'], c['expected']) for c in old] == [(c['name'], c['inputs'], c['expected']) for c in new]


def test_transfer_cases_are_separate_and_frozen():
    transfer = dataset(CASES.with_name('unit_transfer_cases_v2.json'))
    assert len(transfer.cases) == 3
    assert not {c.name for c in transfer.cases} & {c.name for c in dataset().cases}


def test_standard_summary_surfaces_semantic_outcomes_and_evaluator_identity(tmp_path):
    from evals.run import summarize, compare
    version = 'unit-validity-v2-structured-classification'
    (tmp_path / 'configuration.json').write_text(json.dumps({'evaluator_version': version}))
    (tmp_path / 'report.json').write_text(json.dumps({'cases': [{
        'name': 'invalid-pair', 'assertions': {'semantic_validity': {'value': False}},
        'evaluator_failures': [], 'attributes': {}, 'metrics': {}, 'scores': {}, 'task_duration': 0.1}], 'failures': []}))
    (tmp_path / 'outcomes.json').write_text(json.dumps({'evaluator_version': version,
        'attempts': 1, 'outcomes': {'dangerous_false_approval': 1}, 'report_evaluator_defects': 0}))
    summary = summarize(tmp_path)
    assert summary['identity']['evaluator_version'] == version
    assert summary['semantic_outcomes']['outcomes']['dangerous_false_approval'] == 1
    rendered = compare({'agent': 'assessment', 'run': 'current', 'summary': summary}, None, None)
    assert 'dangerous_false_approval=1' in rendered
    assert 'Contract failures are not successful semantic rejections' in rendered
