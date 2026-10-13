"""SPEC-0060 runtime stage of the E2E-0 chain in direct mode: only a prepared, supported row lets the run continue."""
import asyncio
from dataclasses import replace

import pytest
from pydantic_ai import models

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.composition.direct import UNOBSERVED, StageModels, run_direct
from corsair.nodes.runtime.contracts import RuntimeInputs
from corsair.nodes.runtime.environment import RuntimeCatalog
from corsair.nodes.runtime.matrix import load
from evals.fixture_e2e.case import (fixture_case, reviewed_runners, scripted_assessment, scripted_authoring,
                                    scripted_identification, scripted_planning)

ROW = 'cpython-3.12-pytest'


def pyproject(requires: str) -> RuntimeInputs:
    return RuntimeInputs(files={'pyproject.toml': f'[project]\nrequires-python = "{requires}"\n'
                                                  f'[tool.pytest.ini_options]\n'.encode(), 'documents.py': b'\xff'})


def catalog(digest: str | None = None) -> RuntimeCatalog:
    """This node's prepared image for the Python row; by default the image the fixture's identity declares."""
    return RuntimeCatalog(load(), {ROW: 'docker.io/library/corsair-python@sha256:' + (digest or fixture_case().environment_identity.image_digest)})


@pytest.fixture
def run(tmp_path):
    (tmp_path / 'artifacts').mkdir(mode=0o700)
    (tmp_path / 'work').mkdir()
    stage_models = StageModels(identification=scripted_identification(), planning=scripted_planning(),
                               authoring=scripted_authoring(), assessment=scripted_assessment())

    def go(case, **options):
        with LocalArtifacts(tmp_path / 'artifacts', max_bytes=1024 * 1024) as store, models.override_allow_model_requests(False):
            return asyncio.run(run_direct(case, stage_models, reviewed_runners(store, tmp_path / 'work'), **options))
    return go


def test_a_supported_prepared_row_continues_and_is_recorded(run):
    result = run(replace(fixture_case(), runtime=pyproject('>=3.10')), catalog=catalog())
    assert (result.stopped_at, result.reason) == (None, 'complete')
    assert (result.runtime.status, result.runtime.selection.image_id) == ('supported', ROW)
    assert result.runtime.image.endswith(fixture_case().environment_identity.image_digest)
    assert result.limitations[:len(UNOBSERVED) + 1] == UNOBSERVED + (
        "Runtime selected from the baseline revision's build files; the candidate's were not read.",)


@pytest.mark.parametrize('inputs, prepared, status, reason', [
    (pyproject('>=3.7,<3.12'), True, 'unsupported', 'runtime unsupported: cpython'),
    (RuntimeInputs(files={'README.md': b'x'}), True, 'undetermined', 'no runtime requirement: no build files'),
    (RuntimeInputs(files={'pytest.ini': b'[pytest]\n'}), True, 'undetermined', 'runtime undetermined: '),
    (pyproject('>=3.10'), False, 'not_prepared', f'matrix row {ROW} has no prepared image on this node'),
])
def test_an_unselected_runtime_ends_the_run_before_any_stage(run, tmp_path, inputs, prepared, status, reason):
    result = run(replace(fixture_case(), runtime=inputs), catalog=catalog() if prepared else RuntimeCatalog(load(), {}))
    assert (result.stopped_at, result.runtime.status) == ('runtime', status)
    assert result.reason.startswith(reason) and result.reason == result.runtime.reason
    assert result.runtime.diagnostic is not None
    assert result.attempts == () and result.executions == () and result.gate is None
    assert not any((tmp_path / 'work').iterdir())


def test_a_declared_environment_off_the_selection_ends_the_run(run):
    result = run(replace(fixture_case(), runtime=pyproject('>=3.10')), catalog=catalog('b' * 64))
    assert (result.stopped_at, result.runtime.status, result.attempts) == ('runtime', 'supported', ())
    assert result.reason.startswith('declared environment image ') and f'is not the selected {ROW} image' in result.reason
    java = replace(fixture_case(), environment=fixture_case().environment.model_copy(update={'language': 'Java'}),
                   runtime=pyproject('>=3.10'))
    assert run(java, catalog=catalog()).reason == 'declared environment language Java is not the selected python'
    junit = replace(fixture_case(), environment=fixture_case().environment.model_copy(update={'framework': 'JUnit 4.12'}),
                    runtime=pyproject('>=3.10'))
    assert run(junit, catalog=catalog()).reason == ('declared environment framework JUnit 4.12 is not one the selection '
                                                   'admitted (pytest)')


def test_build_files_without_a_catalog_stop_with_the_failure_kind(run):
    result = run(replace(fixture_case(), runtime=pyproject('>=3.10')))
    assert (result.stopped_at, result.runtime, result.attempts) == ('runtime', None, ())
    assert result.reason == ('runtime selection failed: RuntimeCatalogMissing: The case carries build files but no '
                             'runtime catalog is configured')
