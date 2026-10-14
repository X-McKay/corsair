"""Native isolated staged wiring and input separation; no model endpoint or test-code execution."""
import asyncio
import json
import pytest
from evals.experiments.staged_baseline.evaluate import evaluate, passed, stage_run, author_reference

@pytest.mark.parametrize('stage,count',[('identification',8),('planning',5),('control_authoring',8),('exploit_authoring',8),('validity',3)])
def test_native_staged_scripted_reports(stage,count,tmp_path):
    destination=tmp_path/stage
    report=asyncio.run(evaluate(stage,destination))
    assert passed(report)
    assert len(report.cases)==count
    native=json.loads((destination/'report.json').read_text())
    assert len(native['cases'])==count and not native['failures']
    config=json.loads((destination/'configuration.json').read_text())
    assert config['execution']=='none' and config['max_concurrency']==1
    assert all(config[key] for key in ('prompt_version','config_version','skill_sha256','toolset_sha256','source_manifest'))
    receipts=[json.loads(p.read_text()) for p in destination.glob('attempt-*.json')]
    assert len(receipts)==count
    assert all(r['provider_usage_present'] is None and r['usage_source']=='scripted_estimate' for r in receipts)
    if stage=='validity':
        outcomes=json.loads((destination/'outcomes.json').read_text())
        assert outcomes['outcomes']=={'correct_approval':1,'correct_rejection':2}


def test_author_inputs_hold_only_own_identity_and_property():
    control=stage_run('control_authoring'); exploit=stage_run('exploit_authoring')
    for benign,security in zip(control.corpus.cases,exploit.corpus.cases):
        prompt=control.prompt(benign.inputs)
        assert security.inputs.test_path not in prompt
        assert 'adversarial_input' not in prompt
        assert benign.inputs.environment.baseline_test is None
        prompt=exploit.prompt(security.inputs)
        assert benign.inputs.test_path not in prompt
        assert 'control_input' not in prompt
        assert security.inputs.environment.baseline_test is None


def test_planning_native_reused_five_framework_inputs():
    stage=stage_run('planning')
    assert len(stage.corpus.cases)==5
    assert len({c.inputs.environment.framework for c in stage.corpus.cases})==5
    assert {type(e).__name__ for e in stage.corpus.evaluators}=={'MatchesPlan','ReadBeforePlanning'}


@pytest.mark.parametrize('language,real_call',[('javascript','runReport(runner,'),('ruby','run_report(runner,'),
    ('perl','Commands::run_report($runner,'),('java','Commands.runReport(runner,')])
def test_operator_reference_anchors_bind_application_assertions(language,real_call):
    for role in ('control','exploit'):
        content,anchors=author_reference(language,role)
        assert real_call in content
        assert anchors and all(1<=line<=len(content.splitlines()) for line in anchors)
        assert all(content.splitlines()[line-1].strip() for line in anchors)
