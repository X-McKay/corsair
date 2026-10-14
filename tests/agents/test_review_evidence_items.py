"""Frozen validity inventory preserves source bytes without leaking run outcomes."""

from hashlib import sha256
from types import SimpleNamespace

from corsair.agents.evidence_assessment.contracts import MAX_ITEM_CHARS
from corsair.agents.source.contracts import SourceFile
from corsair.agents.test_planning.contracts import ReadyTestPlan
from corsair.composition.evidence import _item, review_items
from evals.fixture_e2e.case import fixture_case, reference_plan
from tests.agents.test_evidence_assessment import PLAN


def test_path_metadata_does_not_truncate_maximum_admitted_source():
    content = 'x' * MAX_ITEM_CHARS
    item = _item('baseline-source-0', 'source', content, 'baseline', 0,
                 source_sha256='a' * 64, path='nested/application.py')
    assert item.complete
    assert item.content == content
    assert item.sha256 == sha256(content.encode()).hexdigest()
    assert item.path == 'nested/application.py'


def test_outcome_blind_inventory_contains_only_frozen_review_artifacts():
    draft = reference_plan()
    for ref in [*draft['citations'], *draft['control']['source_references'],
                *draft['security']['source_references']]:
        lines = next(source.content for source in fixture_case().issue.source_files
                     if source.path == ref['path']).splitlines()
        ref['quote'] = '\n'.join(lines[ref['start_line'] - 1:ref['end_line']])
    plan = ReadyTestPlan.model_validate(draft)
    source = SourceFile(path='documents.py', content='real application implementation\n')
    patch = SimpleNamespace(files=(SourceFile(path='test_documents.py', content='two native probes\n'),))
    items = review_items(PLAN, patch, {'baseline': (source,), 'candidate': (source,)},
                         {'baseline': 'a' * 64}, plan, 'reported unsafe condition')
    assert {item.kind for item in items} == {'plan', 'patch', 'source'}
    assert [item.item_id for item in items] == [
        'plan', 'test-plan', 'reported-condition', 'baseline-source-0', 'patch-0']
    observed_source = next(item for item in items if item.kind == 'source')
    assert observed_source.source_sha256 == 'a' * 64
    assert observed_source.content == source.content
    assert observed_source.path == source.path
    assert all(item.complete for item in items)


def frozen_review(quote_size=None):
    """Construct a saved review without executing a model or either native probe."""
    import json
    from corsair.agents.evidence_assessment.contracts import EvidenceAssessment
    from tests.agents.test_evidence_assessment import unit_draft, unit_inputs
    data = unit_draft()
    sources = {item.item_id: item.content for item in unit_inputs().items}
    def quote(value):
        if isinstance(value, dict):
            if {'item_id', 'start_line', 'end_line'} <= value.keys():
                value['quote'] = ('x' * quote_size if quote_size is not None else '\n'.join(
                    sources[value['item_id']].splitlines()[value['start_line'] - 1:value['end_line']]))
            for item in value.values():
                quote(item)
        elif isinstance(value, list):
            for item in value:
                quote(item)
    quote(data)
    data.update(execution='unknown', finding='inconclusive', fix='not_applicable',
                application_observations=[], sandbox_observations=[],
                admission={'admitted': True, 'disposition': {'execution': 'unknown', 'finding': 'inconclusive',
                    'fix': 'not_applicable'}, 'rejections': ()}, gate_limitations=[], bound_validity={})
    for review in data['validity_reviews']:
        data['bound_validity'][review['revision']] = {
            'artifact_sha256': sha256(json.dumps(review, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'observation_plan_sha256': PLAN.review_digest, 'source_sha256': 'a' * 64,
            'source_linked': True, 'condition_exercised': True, 'assertions_relevant': True,
            'dependency_scope_valid': True}
    return EvidenceAssessment.model_validate(data)


def test_two_revision_frozen_review_is_complete_without_pretty_print_overhead():
    import json
    from corsair.composition.evidence import _frozen_review_items
    review = frozen_review()
    assert len(review.model_dump_json(indent=2)) > MAX_ITEM_CHARS
    (item,) = _frozen_review_items(review)
    assert item.item_id == 'test-validity' and item.complete
    assert json.loads(item.content) == review.model_dump(mode='json')


def test_large_review_summaries_retain_both_probe_findings_bindings_and_citations():
    import json
    from corsair.composition.evidence import _frozen_review_items
    review = frozen_review(quote_size=4000)
    before = review.model_dump_json()
    items = _frozen_review_items(review)
    assert {item.item_id for item in items} == {'test-validity-baseline', 'test-validity-candidate'}
    for item, retained in zip(items, review.validity_reviews):
        summary = json.loads(item.content)
        assert item.complete
        assert summary['representation'] == 'summary_without_quotation_bodies'
        assert summary['bound_validity'] == review.bound_validity[retained.revision].model_dump(mode='json')
        for role in ('control', 'exploit'):
            actual = summary['review'][role]
            original = getattr(retained, role)
            assert actual['test_id'] == original.test_id
            assert actual['production_binding']['status'] == original.production_binding.status
            assert actual['production_binding']['call_site'] == original.production_binding.call_site.model_dump(exclude={'quote'})
            assert actual['input_exercise']['observed_input'] == original.input_exercise.observed_input
            assert actual['assertion']['asserted_property'] == original.assertion.asserted_property
            assert actual['dependencies']['substitutions'] == list(original.dependencies.substitutions)
    assert review.model_dump_json() == before


def test_oversized_finding_summary_is_refused_without_silent_truncation():
    import pytest
    from corsair.agents.evidence_assessment.contracts import EvidenceAssessment
    from corsair.composition.evidence import _frozen_review_items
    data = frozen_review(quote_size=4000).model_dump()
    for decision in data['validity_reviews']:
        for role in ('control', 'exploit'):
            for check in ('production_binding', 'input_exercise', 'assertion', 'dependencies'):
                decision[role][check]['evidence']['statement'] = 'x' * 2048
    with pytest.raises(ValueError, match='validity summary exceeds'):
        _frozen_review_items(EvidenceAssessment.model_validate(data))
