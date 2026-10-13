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
