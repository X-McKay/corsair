"""Actual reviewed native pair capture, immutable source review and evaluator isolation."""
import asyncio
from dataclasses import replace
import json

import pytest
from evals.experiments.staged_baseline.unit_disposition import dataset, native_and_review_binding
from evals.evidence_assessment.evaluate import EvaluationBudget, evaluate


def test_frozen_final_inputs_have_both_native_outcomes_and_bound_source_reviews():
    corpus = dataset()
    assert len(corpus.cases) == 4
    for case in corpus.cases:
        inputs = case.inputs
        assert native_and_review_binding(inputs)
        assert inputs.evidence.plan.observation_mode == 'unit_test'
        for revision in ('baseline', 'candidate'):
            run = getattr(inputs.evidence, revision)[0]
            assert {o.test_id for o in run.outcomes} == {inputs.evidence.plan.control_test_id,inputs.evidence.plan.security_test_id}
            control = next(o for o in run.outcomes if o.test_id == inputs.evidence.plan.control_test_id)
            assert control.outcome == 'passed'
            assert run.test_validity.source_sha256 == run.source_sha256
            assert run.test_validity.observation_plan_sha256 == inputs.evidence.plan.review_digest
        assert case.metadata.review_items
        assert all(case.metadata.receipt_items[revision] for revision in ('baseline','candidate'))


def test_missing_probe_or_mismatched_frozen_review_cannot_be_admitted():
    inputs = dataset().cases[0].inputs
    run = inputs.evidence.baseline[0]
    one_probe = run.model_copy(update={'outcomes':run.outcomes[:1]})
    assert not native_and_review_binding(inputs.model_copy(update={
        'evidence':inputs.evidence.model_copy(update={'baseline':(one_probe,)})}))
    wrong_source = run.model_copy(update={'source_sha256':'0'*64})
    assert not native_and_review_binding(inputs.model_copy(update={
        'evidence':inputs.evidence.model_copy(update={'baseline':(wrong_source,)})}))
    wrong_plan = run.model_copy(update={'test_validity':run.test_validity.model_copy(update={'observation_plan_sha256':'0'*64})})
    assert not native_and_review_binding(inputs.model_copy(update={
        'evidence':inputs.evidence.model_copy(update={'baseline':(wrong_plan,)})}))


@pytest.mark.parametrize('field',['mode','model','budget','task_retries','max_concurrency'])
def test_custom_identity_cannot_override_model_mode_or_execution_caps(tmp_path,field):
    evidence = tmp_path/'refused'
    identity = {'dataset':'unit','dataset_sha256':'0'*64,field:'pretend'}
    with pytest.raises(ValueError,match='only dataset fields'):
        asyncio.run(evaluate(evidence,EvaluationBudget(repeat=1),corpus=dataset(),dataset_identity=identity))
    assert not evidence.exists()


def test_v2_frozen_review_cites_each_own_call_input_and_assertion_lines():
    for case in dataset('v2').cases:
        items={item.item_id:item for item in case.inputs.items}
        for item in case.inputs.items:
            if item.kind!='test_validity':
                continue
            review=json.loads(item.content)['review']
            own_paths=[]
            for role,actual_input in [('control','document.txt'),('exploit','../outside.txt')]:
                probe=review[role]
                call=probe['production_binding']['call_site']
                patch=items[call['item_id']]
                quote='\n'.join(patch.content.splitlines()[call['start_line']-1:call['end_line']])
                assert 'documents.read_document' in quote and actual_input in quote
                assert probe['input_exercise']['observed_input']==actual_input
                expected_path='test_'+role+'.py'
                assert probe['test_id'].split('::')[0]==expected_path
                from evals.fixture_e2e.case import split_reviewed_tests
                assert patch.content.splitlines()==split_reviewed_tests()[expected_path].read_text().splitlines()
                assertion_citations=probe['assertion']['evidence']['citations']
                assertion_quotes=['\n'.join(items[citation['item_id']].content.splitlines()[citation['start_line']-1:citation['end_line']])
                                  for citation in assertion_citations if citation['item_id']==patch.item_id]
                assert any('assert ' in quote for quote in assertion_quotes)
                if role=='exploit':
                    assert any('result != "synthetic-outside-sentinel"' in quote for quote in assertion_quotes)
                    assert all('outside.read_text' not in quote for quote in assertion_quotes)
                own_paths.append(expected_path)
            assert own_paths==['test_control.py','test_exploit.py']


def test_v1_defective_callsite_is_preserved_as_historical_input():
    corpus=dataset('v1')
    assert len(corpus.cases)==4
    for case in corpus.cases:
        for item in case.inputs.items:
            if item.kind=='test_validity':
                review=json.loads(item.content)['review']
                assert review['control']['production_binding']['call_site']['item_id']==review['exploit']['production_binding']['call_site']['item_id']
