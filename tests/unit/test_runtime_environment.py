"""SPEC-0042 hand-off to the environment agent: one selected toolchain, or a stop before the agent runs."""
import pytest

from corsair.agents.environment.contracts import ReadyEnvironment
from corsair.nodes.runtime.detect import detect
from corsair.nodes.runtime.contracts import MAX_INPUT_BYTES, RuntimeInputs, RuntimeOutcome
from corsair.nodes.runtime.environment import RuntimeCatalog, check_ready, environment_input, runtime_inputs, select_runtime
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


@pytest.mark.parametrize('requires, prepared, status, reason', [
    ('>=3.7,<3.12', PREPARED, 'unsupported', 'runtime unsupported: cpython'),
    ('>=3.10', {}, 'not_prepared', 'has no prepared image'),
])
def test_stop_replaces_the_agent_run(requires, prepared, status, reason):
    requirement, selection = project(requires)
    stop = environment_input(requirement, selection, load(), prepared, **FIELDS)
    assert isinstance(stop, RuntimeOutcome) and stop.status == status and reason in stop.reason and stop.image is None
    stop = environment_input('no build files recognised at the project root', None, load(), PREPARED, **FIELDS)
    assert (stop.status, stop.requirement, stop.detection) == ('undetermined', None, 'no build files recognised at the project root')


def test_select_runtime_names_the_prepared_image_or_the_reason():
    catalog = RuntimeCatalog(load(), PREPARED)
    pyproject = lambda requires: RuntimeInputs(files={'pyproject.toml': f'[project]\nrequires-python = "{requires}"\n'
                                                                        f'[tool.pytest.ini_options]\n'.encode()})
    supported = select_runtime(pyproject('>=3.10'), catalog)
    assert (supported.status, supported.image, supported.selection.image_id) == (
        'supported', PREPARED['cpython-3.12-pytest'], 'cpython-3.12-pytest')
    assert select_runtime(pyproject('<3.8'), catalog).status == 'unsupported'
    assert select_runtime(RuntimeInputs(files={'README.md': b'x'}), catalog).status == 'undetermined'
    undeclared = select_runtime(RuntimeInputs(files={'pytest.ini': b'[pytest]\n'}), catalog)
    assert undeclared.status == 'undetermined' and undeclared.requirement is not None


@pytest.mark.parametrize('prepared', [{'not-a-row': PREPARED['cpython-3.12-pytest']}, {'cpython-3.12-pytest': 'corsair-python:latest'}])
def test_catalog_refuses_unpinned_or_unknown_prepared_images(prepared):
    with pytest.raises(ValueError):
        RuntimeCatalog(load(), prepared)


def test_outcome_fields_must_agree_with_the_status():
    supported = select_runtime(RuntimeInputs(files={'pyproject.toml': b'[project]\nrequires-python = ">=3.10"\n[tool.pytest.ini_options]\n'}),
                               RuntimeCatalog(load(), PREPARED))
    for wrong in (dict(image=None), dict(status='unsupported'), dict(detection='x')):
        with pytest.raises(ValueError):
            RuntimeOutcome.model_validate(supported.model_dump() | wrong)
    data = RuntimeInputs(files={'pom.xml': b'\xff\xfe'}, language='java')
    assert RuntimeInputs.model_validate_json(data.model_dump_json()) == data


def test_ready_must_stay_on_the_selection():
    _, selection = project('>=3.10')
    image = PREPARED['cpython-3.12-pytest']
    check_ready(ReadyEnvironment.model_construct(toolchain_id='cpython-3.12-pytest', toolchain_image=image, framework='pytest'), selection, PREPARED)
    for wrong in (dict(toolchain_image='other@sha256:' + 'b' * 64, framework='pytest'), dict(toolchain_image=image, framework='junit5')):
        with pytest.raises(ValueError):
            check_ready(ReadyEnvironment.model_construct(toolchain_id='cpython-3.12-pytest', **wrong), selection, PREPARED)


def test_runtime_stop_distinguishes_new_image_from_preparation_and_keeps_ranges():
    requirement, selection = project(">=3.7,<3.12")
    result = environment_input(requirement, selection, load(), PREPARED, **FIELDS)
    assert result.diagnostic.code == "image_unavailable"
    assert requirement.components[0].allowed in result.diagnostic.render()
    assert result.diagnostic.evidence == ("pyproject.toml:2", "pyproject.toml:3")
    requirement, selection = project(">=3.10")
    result = environment_input(requirement, selection, load(), {}, **FIELDS)
    assert result.diagnostic.code == "image_not_prepared"
    assert "Do not create a replacement row" in result.diagnostic.render()


def test_framework_only_mismatch_does_not_prescribe_a_new_runtime():
    requirement = detect({"pyproject.toml": b'[project]\nrequires-python=">=3.12"\n[project.optional-dependencies]\ntest=["pytest<8"]\n'}, 'python')
    result = environment_input(requirement, select(requirement, load()), load(), PREPARED, **FIELDS)
    assert result.diagnostic.code == "framework_unqualified"
    assert "Qualify the framework/runner" in result.diagnostic.render()


def test_undetermined_stops_before_environment_input_validation():
    result = environment_input("no build files", None, load(), {}, commit="invalid")
    assert result.diagnostic.code == "runtime_undetermined"
    assert result.diagnostic.owner == "developer"


def test_inputs_over_the_payload_bound_are_omitted_by_name_and_leave_selection_undetermined():
    pyproject = b'[project]\nrequires-python = ">=3.10"\n[tool.pytest.ini_options]\n'
    lock = b'#' * MAX_INPUT_BYTES
    inputs = runtime_inputs({'pyproject.toml': pyproject, 'poetry.lock': lock, 'src/app.py': b'x'})
    assert (set(inputs.files), inputs.omitted) == ({'pyproject.toml'}, ('poetry.lock',))
    outcome = select_runtime(inputs, RuntimeCatalog(load(), PREPARED))
    assert outcome.status == 'undetermined' and 'poetry.lock omitted from the chain inputs' in outcome.reason
    assert outcome.diagnostic.code == 'runtime_undetermined'
    with pytest.raises(ValueError):
        RuntimeInputs(files={'pyproject.toml': pyproject, 'poetry.lock': lock})
    assert select_runtime(runtime_inputs({'pyproject.toml': pyproject}), RuntimeCatalog(load(), PREPARED)).diagnostic is None
