"""Offline guards on the image-only case table: each entry names a prepared image, valid ids and both outcomes."""
import pytest

from corsair.ports.test_runner import JavaTestId
from tests.qualification.image_cases import CASES, outcome
from tests.qualification.prepare_toolchains import BASES


def test_case_table_entries_are_complete():
    assert CASES and set(CASES) <= set(BASES)
    for cases in CASES.values():
        for case in cases:
            control, security = case['ids']
            assert JavaTestId.parse(control).source_path() == JavaTestId.parse(security).source_path() == case['pov']['path']
            assert set(case['expect']) == {'fix', 'vulnerable'} and case['expect']['fix'][0] == case['expect']['vulnerable'][0] == 'passed'
            assert all(len(case[key]) == 40 for key in ('fix', 'vulnerable')) and len(case['overlay_sha256']) == 64


@pytest.mark.parametrize('rows', [
    [['a.B#control', 'passed'], ['a.B#security', 'error']],
    [['a.B#control', 'passed', ''], ['a.B#security', 'error', 'TestTimedOutException']],
])
def test_outcome_reads_both_harness_row_shapes(rows):
    assert outcome({'cases': rows}, ('a.B#control', 'a.B#security', 'a.B#absent')) == ('passed', 'error', 'missing')


@pytest.mark.parametrize('rows', [[['a.B#control']], [['a.B#control', 'passed', '', 'extra']], [{'id': 'a.B#control'}]])
def test_outcome_refuses_other_row_shapes(rows):
    with pytest.raises(AssertionError):
        outcome({'cases': rows}, ('a.B#control',))
