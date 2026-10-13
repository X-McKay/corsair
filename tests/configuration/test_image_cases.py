"""Offline guards on the image-only case table: each entry names a prepared image, valid ids and both outcomes."""
from corsair.ports.test_runner import JavaTestId
from tests.qualification.image_cases import CASES
from tests.qualification.prepare_toolchains import BASES


def test_case_table_entries_are_complete():
    assert CASES and set(CASES) <= set(BASES)
    for cases in CASES.values():
        for case in cases:
            control, security = case['ids']
            assert JavaTestId.parse(control).source_path() == JavaTestId.parse(security).source_path() == case['pov']['path']
            assert case['expect'] == {'fix': ('passed', 'passed'), 'vulnerable': ('passed', 'not passed')}
            assert all(len(case[key]) == 40 for key in ('fix', 'vulnerable')) and len(case['overlay_sha256']) == 64
