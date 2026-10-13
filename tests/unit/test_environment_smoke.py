"""SPEC-0071: operator smoke tests fit the environment agent's baseline admission for their framework (offline)."""
import shutil
import subprocess
import sys

import pytest

from corsair.agents.environment.frameworks import FRAMEWORKS, file_matches
from corsair.nodes.runtime.detect import detect
from corsair.nodes.runtime.environment import AGENT_FRAMEWORK, smoke_tests
from corsair.nodes.runtime.matrix import Matrix, load, select

SMOKE_TESTS = {AGENT_FRAMEWORK[f.name]: f.smoke for f in load().frameworks}


@pytest.mark.parametrize('framework', sorted(FRAMEWORKS))
def test_every_admitted_framework_has_a_smoke_test_its_baseline_rule_accepts(framework):
    smoke = SMOKE_TESTS[framework]
    assert smoke is not None and file_matches(framework, smoke.test_id, smoke.path)


def test_the_selection_offers_the_smoke_template_of_its_framework_row():
    chosen = select(detect({'requirements.txt': b'pytest\n'}, 'python'), load())
    (offered,) = smoke_tests(chosen, load())
    assert (offered.framework, offered.path, offered.test_id, offered.content) == (
        'pytest', SMOKE_TESTS['pytest'].path, SMOKE_TESTS['pytest'].test_id, SMOKE_TESTS['pytest'].content)


def test_rows_of_one_framework_must_carry_the_same_smoke_template():
    matrix = load().model_dump()
    rows = [f for f in matrix['frameworks'] if f['name'] == 'pytest']
    rows[0]['smoke'] = rows[0]['smoke'] | {'content': 'def test_other():\n    assert True\n'}
    with pytest.raises(ValueError, match='different smoke tests'):
        Matrix.model_validate(matrix)


def test_the_python_smoke_test_passes_under_pytest(tmp_path):
    smoke = SMOKE_TESTS['pytest']
    (tmp_path / smoke.path).parent.mkdir(parents=True)
    (tmp_path / smoke.path).write_text(smoke.content)
    run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-c', '/dev/null', '--rootdir', '.',
                          smoke.test_id], cwd=tmp_path, capture_output=True)
    assert run.returncode == 0 and FRAMEWORKS['pytest'].passed(run.stdout)


@pytest.mark.skipif(shutil.which('prove') is None, reason='prove not installed on this host')
def test_the_perl_smoke_test_passes_under_prove(tmp_path):
    smoke = SMOKE_TESTS['tap-harness']
    (tmp_path / smoke.path).parent.mkdir(parents=True)
    (tmp_path / smoke.path).write_text(smoke.content)
    run = subprocess.run(['prove', '--norc', '-v', smoke.test_id], cwd=tmp_path, capture_output=True)
    assert run.returncode == 0 and FRAMEWORKS['tap-harness'].passed(run.stdout)


@pytest.mark.skipif(shutil.which('ruby') is None, reason='ruby not installed on this host')
def test_the_ruby_smoke_test_passes_under_minitest(tmp_path):
    smoke = SMOKE_TESTS['minitest']
    (tmp_path / smoke.path).parent.mkdir(parents=True)
    (tmp_path / smoke.path).write_text(smoke.content)
    run = subprocess.run(['ruby', smoke.test_id], cwd=tmp_path, capture_output=True)
    if b'cannot load such file -- minitest' in run.stderr:
        pytest.skip('minitest gem not installed on this host')
    assert run.returncode == 0 and FRAMEWORKS['minitest'].passed(run.stdout)
