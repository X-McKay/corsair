"""SPEC-0042 hand-off to the environment agent: one selected toolchain, or a stop before the agent runs."""
import pytest

from corsair.agents.environment.contracts import ReadyEnvironment
from corsair.nodes.runtime.detect import detect
from corsair.nodes.runtime.environment import RuntimeStop, check_ready, environment_input
from corsair.nodes.runtime.matrix import load, select

PREPARED = {'cpython-3.12-pytest': 'docker.io/library/corsair-python@sha256:' + 'a' * 64}
FIELDS = dict(commit='1' * 40, source_private=False, policy_profile='setup-python',
              source_files=[{'path': 'pyproject.toml', 'content': 'x'}])


def project(requires: str):
    files = {'pyproject.toml': f'[project]\nrequires-python = "{requires}"\n[tool.pytest.ini_options]\n'.encode()}
    requirement = detect(files, 'python')
    return requirement, select(requirement, load())


def test_selected_row_is_the_only_toolchain():
    requirement, selection = project('>=3.10')
    result = environment_input(requirement, selection, load(), PREPARED, **FIELDS)
    assert [(t.toolchain_id, t.image, t.runtime) for t in result.toolchains] == [
        ('cpython-3.12-pytest', PREPARED['cpython-3.12-pytest'], 'cpython 3.12.15')]


@pytest.mark.parametrize('requires, prepared, reason', [
    ('>=3.7,<3.12', PREPARED, 'runtime unsupported: cpython'),
    ('>=3.10', {}, 'has no prepared image'),
])
def test_stop_replaces_the_agent_run(requires, prepared, reason):
    requirement, selection = project(requires)
    stop = environment_input(requirement, selection, load(), prepared, **FIELDS)
    assert isinstance(stop, RuntimeStop) and reason in stop.reason
    assert isinstance(environment_input('no build files recognised at the project root', None, load(), PREPARED, **FIELDS), RuntimeStop)


def test_ready_must_stay_on_the_selection():
    _, selection = project('>=3.10')
    image = PREPARED['cpython-3.12-pytest']
    check_ready(ReadyEnvironment.model_construct(toolchain_id='cpython-3.12-pytest', toolchain_image=image, framework='pytest'), selection, PREPARED)
    for wrong in (dict(toolchain_image='other@sha256:' + 'b' * 64, framework='pytest'), dict(toolchain_image=image, framework='junit5')):
        with pytest.raises(ValueError):
            check_ready(ReadyEnvironment.model_construct(toolchain_id='cpython-3.12-pytest', **wrong), selection, PREPARED)
