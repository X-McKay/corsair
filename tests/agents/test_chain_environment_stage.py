"""SPEC-0068 environment stage of the E2E-0 chain in direct mode: the environment agent prepares the selected
toolchain in an operator sandbox, and only an admitted ready result replaces the declared environment."""
import asyncio
from dataclasses import replace

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.issue_analysis.contracts import SourceFile
from corsair.composition.direct import (OBSERVED_IDENTITY, UNOBSERVED, PreparedSandbox, SetupSource, StageModels,
                                        run_direct)
from corsair.nodes.runtime.contracts import RuntimeInputs
from corsair.nodes.runtime.environment import RuntimeCatalog, recipe_sha256
from corsair.nodes.runtime.matrix import load
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from evals.fixture_e2e.case import (fixture_case, reviewed_runners, scripted_assessment, scripted_authoring,
                                    scripted_identification, scripted_planning)
from evals.fixture_e2e.reviewed import DISCOVER, PREFIX, REVIEWED_TEST

BASELINE_ID = 'test_existing.py::test_reads_existing_document'
BUILD = ('python3.12', '-m', 'compileall', '-q', 'documents.py')
BASELINE = PREFIX + ('-q', BASELINE_ID)
CI = 'jobs:\n  test:\n    steps:\n      - run: python3.12 -m compileall -q documents.py\n      - run: pytest -q\n'
SETUP = SetupSource(commit='1' * 40, source_private=False, policy_profile='setup-public',
                    source_files=(SourceFile(path='.github/workflows/ci.yml', content=CI),))
ROW = 'cpython-3.12-pytest'
OK = {BUILD: (0, ''), DISCOVER: (0, f'{BASELINE_ID}\n1 test collected\n'), BASELINE: (0, '1 passed in 0.01s\n')}


def pyproject(requires: str) -> RuntimeInputs:
    return RuntimeInputs(files={'pyproject.toml': f'[project]\nrequires-python = "{requires}"\n'
                                                  f'[tool.pytest.ini_options]\n'.encode()})


def catalog() -> RuntimeCatalog:
    return RuntimeCatalog(load(), {ROW: 'docker.io/library/corsair-python@sha256:' + fixture_case().environment_identity.image_digest})


def ready_draft(**changes):
    return {'status': 'ready', 'toolchain_id': ROW, 'recipe': [], 'build_command': list(BUILD),
            'discovery_command': list(DISCOVER), 'framework': 'pytest', 'baseline_test_id': BASELINE_ID,
            'baseline_test_path': 'test_existing.py', 'baseline_test_command': list(BASELINE),
            'approved_test_paths': [REVIEWED_TEST]} | changes


def environment_model(commands, draft):
    """Reads the CI workflow, lists toolchains, runs `commands` in order, then returns `draft`."""
    calls = [('read_source', {'path': '.github/workflows/ci.yml'}),
             ('list_toolchains', {})] + [('run_setup_command', {'command': list(c)}) for c in commands]

    async def respond(messages, info):
        if calls:
            name, args = calls.pop(0)
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {'draft': draft})])
    return FunctionModel(respond)


class Sandboxes:
    """Host double for the operator's preparation port: recorded observations per exact command; no shell runs."""
    def __init__(self, observations, *, cleanup='confirmed', refuse=False):
        self.observations, self.cleanup, self.refuse = observations, cleanup, refuse
        self.prepared, self.released, self.commands = [], [], []

    def prepare(self, toolchain, operation):
        if self.refuse:
            raise RuntimeError('sandbox admission refused')
        self.prepared.append(toolchain)
        return PreparedSandbox(self, SandboxHandle(id='prep', name='prep', workspace='corsair', owner='test',
                                                   creation_operation=str(operation)), '/sandbox/scratch')

    def release(self, sandbox, operation):
        self.released.append(sandbox.handle)
        return self.cleanup

    def execute(self, handle, command, operation):
        self.commands.append(tuple(command))
        exit_code, stdout = self.observations.get(tuple(command), (126, 'unrecorded command'))
        return ExecutionReceipt(operation=str(operation), handle=handle, started_at='recorded', elapsed_seconds=0.1,
                                delivery='acknowledged', completion='terminal_observed', reason='recorded observation',
                                stdout=stdout.encode(), native_exit=exit_code)


@pytest.fixture
def run(tmp_path):
    (tmp_path / 'artifacts').mkdir(mode=0o700)
    (tmp_path / 'work').mkdir()

    def go(case, environment=None, **options):
        stage_models = StageModels(identification=scripted_identification(), planning=scripted_planning(),
                                   authoring=scripted_authoring(), assessment=scripted_assessment(),
                                   environment=environment)
        with LocalArtifacts(tmp_path / 'artifacts', max_bytes=1024 * 1024) as store, models.override_allow_model_requests(False):
            return asyncio.run(run_direct(case, stage_models, reviewed_runners(store, tmp_path / 'work'), **options))
    return go


def case():
    return replace(fixture_case(), runtime=pyproject('>=3.10'), setup=SETUP)


def test_an_admitted_ready_environment_replaces_the_declaration(run):
    sandboxes = Sandboxes(OK)
    result = run(case(), environment_model([BUILD, DISCOVER, BASELINE], ready_draft()), catalog=catalog(),
                 preparation=sandboxes)
    assert (result.stopped_at, result.reason) == (None, 'complete')
    assert result.attempts[0].stage == 'environment' and result.attempts[0].cleanup == 'confirmed'
    assert [t.toolchain_id for t in sandboxes.prepared] == [ROW] and len(sandboxes.released) == 1
    assert sandboxes.commands == [BUILD, DISCOVER, BASELINE]
    ready = result.environment
    assert (ready.status, ready.toolchain_image) == ('ready', result.runtime.image)
    # The assessment reads the gate's evidence, which now carries the observed recipe instead of the declared one.
    assessed = str(next(a for a in result.attempts if a.stage == 'assessment').messages)
    declared = fixture_case().environment_identity
    assert recipe_sha256(ready) in assessed and declared.recipe_sha256 not in assessed
    assert result.limitations[:4] == UNOBSERVED[:2] + OBSERVED_IDENTITY
    assert UNOBSERVED[2] not in result.limitations


def test_unconfirmed_sandbox_cleanup_is_a_limitation(run):
    result = run(case(), environment_model([BUILD, DISCOVER, BASELINE], ready_draft()), catalog=catalog(),
                 preparation=Sandboxes(OK, cleanup='unconfirmed'))
    assert result.stopped_at is None and 'environment sandbox cleanup unconfirmed' in result.limitations


def _stopped_before_identification(result):
    assert result.stopped_at == 'environment'
    assert [a.stage for a in result.attempts] in ([], ['environment'])
    assert result.identification is None and result.executions == () and result.gate is None


def test_a_blocked_environment_ends_the_run(run):
    failing = OK | {DISCOVER: (2, 'ERROR: file or directory not found: tests\n')}
    draft = {'status': 'blocked', 'layer': 'discovery', 'evidence': 'file or directory not found', 'run_ids': [2],
             'citations': []}
    result = run(case(), environment_model([BUILD, DISCOVER], draft), catalog=catalog(), preparation=Sandboxes(failing))
    _stopped_before_identification(result)
    assert result.reason.startswith('environment blocked at discovery: file or directory not found')
    assert result.environment.status == 'blocked'


def test_an_unsupported_environment_ends_the_run(run):
    draft = {'status': 'unsupported', 'requirement': 'CI runs pytest under tox',
             'citations': [{'path': '.github/workflows/ci.yml', 'start_line': 5, 'end_line': 5}]}
    result = run(case(), environment_model([], draft), catalog=catalog(), preparation=Sandboxes(OK))
    _stopped_before_identification(result)
    assert result.reason == 'environment unsupported: CI runs pytest under tox'


def test_a_ready_result_the_chain_contracts_cannot_hold_is_refused(run):
    # The agent admits a 34-token discovery command; the planner's environment evidence holds at most 32.
    long_discovery = DISCOVER + ('-p', 'no:warnings') * 8
    observations = OK | {long_discovery: (0, f'{BASELINE_ID}\n')}
    result = run(case(), environment_model([BUILD, long_discovery, BASELINE], ready_draft(discovery_command=list(long_discovery))),
                 catalog=catalog(), preparation=Sandboxes(observations))
    _stopped_before_identification(result)
    assert result.reason.startswith('ready environment refused: ')


@pytest.mark.parametrize('environment, preparation, reason', [
    (None, Sandboxes(OK), 'environment produced no output: PreparationMissing: '),
    (FunctionModel(lambda m, i: None), None, 'environment produced no output: PreparationMissing: '),
    (FunctionModel(lambda m, i: None), Sandboxes(OK, refuse=True),
     'environment produced no output: RuntimeError: sandbox admission refused'),
])
def test_a_stage_that_cannot_prepare_ends_the_run(run, environment, preparation, reason):
    result = run(case(), environment, catalog=catalog(), preparation=preparation)
    _stopped_before_identification(result)
    assert result.reason.startswith(reason)


def test_setup_source_without_a_runtime_selection_ends_the_run(run):
    result = run(replace(fixture_case(), setup=SETUP), environment_model([], ready_draft()), preparation=Sandboxes(OK))
    _stopped_before_identification(result)
    assert result.reason == 'setup source needs a runtime selected from build files; the case carries none'
