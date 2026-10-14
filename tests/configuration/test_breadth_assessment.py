"""Breadth validity set: per-language coverage, generated digests, and sensitivity to unsafe blanket approval."""
import json
from collections import Counter
from types import SimpleNamespace

from evals.cases import load_set
from evals.evidence_assessment import build_breadth
from evals.evidence_assessment.unit_test import FLAGS, ValidityScore, dataset


def _score(case, **flags):
    output = SimpleNamespace(validity_reviews=[SimpleNamespace(revision='baseline', **flags)],
                             evidence=None, gate_result=None, bound_validity={'baseline': object()})
    return ValidityScore().evaluate(SimpleNamespace(output=output, metadata=case.metadata))['semantic_validity']


def test_breadth_set_loads_with_claimed_language_counts():
    cases = dataset('breadth').cases
    meta = {c.name: c.case for c in load_set('evidence_assessment', 'breadth')}
    assert {c.name for c in cases} == set(meta)
    assert Counter(m['language'] for m in meta.values()) == {'java': 11, 'javascript': 11, 'ruby': 11, 'perl': 11}
    for language in ('java', 'javascript', 'ruby', 'perl'):
        kinds = Counter(m['kind'] for m in meta.values() if m['language'] == language)
        assert kinds == {'positive': 2, 'negative': 9}
    # Each invalid property appears once per language and constrains exactly one flag.
    for case in cases:
        if meta[case.name]['kind'] == 'negative':
            assert len(case.metadata) == 1 and not any(case.metadata.values())
        else:
            assert case.metadata == dict.fromkeys(FLAGS, True)


def test_breadth_cases_are_regenerated_from_readable_source():
    rendered = build_breadth.render()
    for case in load_set('evidence_assessment', 'breadth'):
        assert {part: json.loads(content) for part, content in rendered[case.name].items()} == {
            'input': case.input, 'oracle': case.oracle, 'case': case.case}


def test_breadth_inputs_carry_no_evaluator_labels():
    for case in dataset('breadth').cases:
        text = case.inputs.model_dump_json().lower()
        assert case.name not in text
        assert not any(word in text for word in ('vacuous', 'copied', 'oracle', 'source_linked', 'invalid case'))


def test_blanket_validity_approval_fails_every_invalid_breadth_case():
    cases = dataset('breadth').cases
    blanket = {case.name: _score(case, **dict.fromkeys(FLAGS, True)) for case in cases}
    valid = {case.name for case in cases if case.metadata == dict.fromkeys(FLAGS, True)}
    assert len(valid) == 8
    assert all(blanket[name] for name in valid)
    assert not any(passed for name, passed in blanket.items() if name not in valid)
    # A blanket rejection fails every valid pair, so neither constant answer passes the set.
    assert not any(_score(case, **dict.fromkeys(FLAGS, False)) for case in cases if case.name in valid)
