"""Corrected positive fixture authority, frozen lineage and native planning output binding."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import pytest
import yaml
from corsair.ports.test_runner import names_test_in
from evals.experiments.staged_baseline import planning_v2
from evals.test_planning.evaluate import EvaluationBudget, evaluate, passed


def test_v2_changes_only_declared_paths_and_source_local_target_extents():
    original=(planning_v2.ROOT/'planning-cases-v1.yaml').read_bytes()
    lineage=json.loads(planning_v2.MANIFEST.read_text())
    assert sha256(original).hexdigest()==lineage['supersedes_sha256']
    before=yaml.safe_load(original)['cases']
    after=yaml.safe_load(planning_v2.CASES.read_text())['cases']
    changes={'python-recording-positive':('test_control.py','test_security.py'),
             'jest-recording-positive':('preview_control.test.js','preview_security.test.js')}
    assert [c['name'] for c in before]==[c['name'] for c in after]
    for old,new in zip(before,after):
        expected=deepcopy(old)
        if old['name'] in changes:
            paths=changes[old['name']]
            expected['inputs']['environment']['approved_test_paths']=list(paths)
            for role,path in zip(('control','security'),paths):
                spec=expected['metadata']['reference_plan'][role]
                spec['test_path']=path
                spec['test_id']=path+'::'+spec['test_id'].split('::',1)[1]
        extent_changes={'perl_command_boundary-fixture-positive':('run_report',3),'java_command_boundary-fixture-positive':('runReport',4)}
        if old['name'] in extent_changes:
            symbol,line=extent_changes[old['name']]
            target=expected['inputs']['identification']['target']
            source=next(s for s in expected['inputs']['source_files'] if s['path']==target['source']['path'])
            target['symbol']=symbol
            target['source'].update(start_line=line,end_line=line,quote=source['content'].splitlines()[line-1])
            expected['metadata']['symbol']=symbol
            expected['metadata']['required_lines']=[line]
            plan=expected['metadata']['reference_plan']
            for ref in plan['citations']:
                if ref['path']==source['path']:ref.update(start_line=line,end_line=line)
            for role in ('control','security'):
                for ref in plan[role]['source_references']:
                    if ref['path']==source['path']:ref.update(start_line=line,end_line=line)
        assert new==expected


def test_all_five_positive_fixtures_admit_two_independent_new_native_paths():
    cases=planning_v2.dataset().cases
    assert len(cases)==5
    assert len({c.inputs.environment.framework for c in cases})==5
    for case in cases:
        env=case.inputs.environment
        reference=case.metadata.reference_plan
        specs=[reference[role] for role in ('control','security')]
        assert len(env.approved_test_paths)==2
        assert specs[0]['test_path']!=specs[1]['test_path']
        assert all(s['test_path'] in env.approved_test_paths and names_test_in(s['test_id'],s['test_path']) for s in specs)
        assert not set(env.approved_test_paths)&{s.path for s in case.inputs.source_files}
        assert env.baseline_test.path in {s.path for s in case.inputs.source_files}


def test_five_framework_native_plans_use_distinct_paths(tmp_path):
    evidence=tmp_path/'evidence'
    report=asyncio.run(planning_v2.run(evidence))
    assert passed(report) and len(report.cases)==5
    for case in report.cases:
        assert case.output.status=='ready'
        assert case.output.control.test_path!=case.output.security.test_path
        assert names_test_in(case.output.control.test_id,case.output.control.test_path)
        assert names_test_in(case.output.security.test_id,case.output.security.test_path)
    config=json.loads((evidence/'configuration.json').read_text())
    assert config['dataset']=='staged-planning-v2-independent-paths'
    assert config['dataset_sha256']==json.loads(planning_v2.MANIFEST.read_text())['sha256']
    assert config['execution']=='synthetic_fixture_baseline_not_executed'
    assert config['budget']==EvaluationBudget(repeat=1).model_dump()


def test_frozen_v2_refuses_changed_fixture_bytes(tmp_path,monkeypatch):
    changed=tmp_path/'planning-cases-v2.yaml'
    changed.write_bytes(planning_v2.CASES.read_bytes()+b'\n')
    monkeypatch.setattr(planning_v2,'CASES',changed)
    with pytest.raises(ValueError,match='frozen planning v2'):
        planning_v2.dataset()


def test_supplied_corpus_requires_its_dataset_identity(tmp_path):
    with pytest.raises(ValueError,match='must be given together'):
        asyncio.run(evaluate(tmp_path/'absent',EvaluationBudget(repeat=1),corpus=planning_v2.dataset()))
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('identity', ['wrong-type',{'dataset':'x','dataset_sha256':'a'*64,'mode':'scripted_fixture'}])
def test_supplied_identity_refuses_type_or_protected_mode_override(tmp_path,identity):
    with pytest.raises(ValueError,match='dictionary|unsupported planning dataset identity fields'):
        asyncio.run(evaluate(tmp_path/'absent',EvaluationBudget(repeat=1),corpus=planning_v2.dataset(),dataset_identity=identity))
    assert not (tmp_path/'absent').exists()


def test_perl_java_targets_follow_production_identification_occurrence_contract():
    from corsair.agents.issue_identification.validation import _symbol_occurs
    for case in planning_v2.dataset().cases:
        target=case.inputs.identification.target
        assert _symbol_occurs(target.symbol,target.source.quote)
        if case.name.startswith('perl'):
            assert (target.symbol,target.source.start_line,target.source.end_line)==('run_report',3,3)
            assert all('Commands::run_report' in case.metadata.reference_plan[r]['implementation_call'] for r in ('control','security'))
        if case.name.startswith('java'):
            assert (target.symbol,target.source.start_line,target.source.end_line)==('runReport',4,4)
            assert all('Commands.runReport' in case.metadata.reference_plan[r]['implementation_call'] for r in ('control','security'))
