"""Independent budgets/inputs and review binding; no generated code execution."""
import asyncio,json
from dataclasses import replace
import pytest
from corsair.ports.test_runner import ApprovedPatch,PatchFile
from evals.experiments.probe_specialists.cases import load_cases,reference_patches
from evals.experiments.probe_specialists.evaluate import Budget,evaluate,run_role
from evals.experiments.probe_specialists.native import execute_pair,inventory_hashes


def test_scripted_role_runs_have_separate_budgets_and_no_peer_input(tmp_path):
    report=asyncio.run(evaluate(tmp_path/'run'))
    assert len(report['attempts'])==24
    assert all(a['draft_completed'] for a in report['attempts'])
    assert len(report['pairs'])==16
    for attempt in report['attempts']:
        receipt=json.loads((tmp_path/'run'/attempt['receipt']).read_text())
        assert receipt['usage']['requests']==3
        role=attempt['role']
        if role=='joint':assert receipt['budget']['request_limit']==40
        else:
            assert receipt['budget']['request_limit']==20
            inputs=receipt['input']
            assert 'frozen_control' not in inputs
            assert len(inputs['environment']['approved_test_paths'])==1
            assert ('adversarial_input' if role=='control' else 'control_input') not in inputs['property_plan']
        assert receipt['semantic_validity'] is None and receipt['execution']=='none'


def test_one_role_failure_does_not_consume_the_other_budget():
    case=load_cases()[0]
    first=asyncio.run(run_role(case,'reported','control',budget=replace(Budget(),request_limit=1)))
    second=asyncio.run(run_role(case,'reported','exploit'))
    assert first['failure']['type']=='UsageLimitExceeded'
    assert second['draft_completed'] and second['usage']['requests']==3


def test_supporting_source_change_prevents_native_launch(tmp_path):
    case=load_cases()[0]
    files=tuple(PatchFile(path,content.encode()) for path,content in reference_patches()[case['name']].items())
    patch=ApprovedPatch(files,tuple(file.path for file in files))
    inventories={name:{f['path']:f['content'].encode() for f in rev['source_files']} for name,rev in case['revisions'].items()}
    review={'status':'supported','patch_sha256':patch.sha256,'source_inventory':inventory_hashes(inventories)}
    review['source_inventory']['fixed']['test_existing.py']='0'*64
    with pytest.raises(ValueError,match='complete captured inventory'):
        execute_pair(patch,review,inventories,(case['control_test_id'],case['exploit_test_id']),tmp_path/'native')
    assert not (tmp_path/'native').exists()
