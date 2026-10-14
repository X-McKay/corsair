"""The public evaluation CLI retains usable versioned reference baselines."""
import json
import pytest
from evals.run import main, SUITES


def test_versioned_reference_can_be_promoted_without_changing_its_measurement(tmp_path):
    run = '20261014T010203Z-transfer-v2-live'
    folder = tmp_path / 'identification' / run
    folder.mkdir(parents=True)
    measurement = {'set': 'transfer-v2', 'mode': 'live', 'clean_attempts': 2, 'attempts': 8}
    encoded = json.dumps(measurement)
    (folder / 'summary.json').write_text(encoded)
    assert main(['identification', '--promote', run, '--results', str(tmp_path)]) == 0
    pointer = json.loads((folder.parent / 'baseline-transfer-v2-live.json').read_text())
    assert pointer['run'] == run
    assert (folder / 'summary.json').read_text() == encoded
    with pytest.raises(SystemExit):
        main(['identification', '--promote', '../outside', '--results', str(tmp_path)])


def test_independent_role_transfer_commands_remain_distinct():
    for role in ('control', 'exploit'):
        suite = SUITES[role + '_authoring']
        assert suite.sets['transfer'] == ('--agent', role + '_authoring')
        assert suite.set_modules['transfer'] == 'evals.experiments.staged_baseline.evaluate'
