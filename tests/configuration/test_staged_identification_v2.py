"""Corrected target oracle measures function anchors, not whole-file wrapper lines."""
from pathlib import Path

from corsair.agents.issue_identification.contracts import IssueIdentification
from evals.issue_identification.evaluate import selection_checks
from evals.experiments.staged_baseline.identification_v2 import dataset, identity, reassess


def selected(case, start, end):
    source = next(source for source in case.inputs.source_files if source.path == case.metadata.path)
    return IssueIdentification(status='ready', scope=case.inputs.scope, reported_issue=case.inputs.issue,
        reason=None, target={'symbol':case.metadata.symbol, 'source':{'path':source.path, 'start_line':start,
        'end_line':end, 'quote':'\n'.join(source.content.splitlines()[start-1:end])}})


def test_explicit_function_oracles_accept_minimal_target_and_reject_boilerplate():
    targets = {'javascript_command_boundary':(1,), 'ruby_command_boundary':(1,2,3),
               'perl_command_boundary':(3,), 'java_command_boundary':(4,)}
    boilerplate = {'javascript_command_boundary':2, 'ruby_command_boundary':3,
                  'perl_command_boundary':1, 'java_command_boundary':5}
    corpus = dataset()
    assert len(corpus.cases) == 8
    for case in corpus.cases:
        name = case.name.rsplit('-',1)[0]
        assert case.metadata.required_lines == targets[name]
        good = selection_checks(case.inputs, selected(case,min(targets[name]),max(targets[name])), case.metadata)
        assert all(good.values())
        bad = selection_checks(case.inputs, selected(case,boilerplate[name],boilerplate[name]), case.metadata)
        assert bad['source_quote'] and not bad['source_range']
    assert set(identity()['source_manifest']) == {'cases-v1.json','identification-oracles-v2.json'}


def test_custom_dataset_identity_cannot_override_mode_or_budget(tmp_path):
    import asyncio
    import pytest
    from evals.issue_identification.evaluate import EvaluationBudget, evaluate
    evidence = tmp_path / 'refused'
    with pytest.raises(ValueError, match='only dataset fields'):
        asyncio.run(evaluate(evidence, EvaluationBudget(), corpus=dataset(),
            dataset_identity={'dataset':'v2','dataset_sha256':'0'*64,'mode':'pretend_live'}))
    assert not evidence.exists()


def test_reassessment_preserves_saved_outputs_and_records_no_new_execution(tmp_path):
    import json
    import pytest
    original = tmp_path / 'original-report.json'
    cases = []
    for case in dataset().cases:
        lines = case.metadata.required_lines
        cases.append({'name':case.name,'inputs':case.inputs.model_dump(mode='json'),
                      'output':selected(case,min(lines),max(lines)).model_dump(mode='json'),
                      'assertions':{'source_range':{'value':False}}})
    original.write_text(json.dumps({'cases':cases}))
    preserved = original.read_bytes()
    destination = tmp_path / 'reassessment.json'
    result = reassess(original,destination)
    assert original.read_bytes() == preserved
    assert result['mode'] == 'corrected_oracle_reassessment_not_new_model_run'
    assert result['new_model_requests'] == 0 and result['new_native_execution'] is False
    assert all(case['corrected_assertions']['source_range'] for case in result['cases'])
    assert all(not case['original_assertions']['source_range']['value'] for case in result['cases'])
    with pytest.raises(FileExistsError):
        reassess(original,destination)
