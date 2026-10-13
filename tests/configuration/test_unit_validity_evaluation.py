"""Freeze semantic validity cases and check evaluator sensitivity to unsafe blanket approval."""
import json
from hashlib import sha256
from types import SimpleNamespace

from evals.evidence_assessment.unit_test import CASES, FLAGS, ValidityScore, dataset


def test_unit_validity_case_manifest_is_frozen():
    cases = json.loads(CASES.read_text())
    actual = {case['name']: sha256(json.dumps(case, sort_keys=True).encode()).hexdigest() for case in cases}
    expected = json.loads(CASES.with_name('unit_test_manifest.json').read_text())
    assert actual == expected


def test_blanket_validity_approval_fails_every_negative_case():
    cases = dataset().cases
    assert len(cases) == 7
    output = SimpleNamespace(validity_reviews=[SimpleNamespace(revision='baseline', **dict.fromkeys(FLAGS, True))],
        evidence=None, gate_result=None, bound_validity={'baseline': object()})
    scores = {case.name: ValidityScore().evaluate(SimpleNamespace(output=output, metadata=case.metadata))
              for case in cases}
    assert scores['real-seam-return-and-exception']['semantic_validity']
    assert all(not score['semantic_validity'] for name, score in scores.items()
               if name != 'real-seam-return-and-exception')
