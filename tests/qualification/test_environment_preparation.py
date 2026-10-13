"""Live SPEC-0070 gate: the chain's environment stage in an OpenShell sandbox prepared by `OpenShellPreparation`.

A captured revision holding the SPEC-0018 vulnerable module and its existing test is placed in a fresh sandbox
of the prepared CPython 3.12 image, the dependency-setup policy is loaded, and a scripted environment model runs
its setup, discovery and baseline commands there through `run_direct`. The gate asserts the stage's mechanics
(ready admitted from real receipts, policy loaded, release confirmed, no sandbox left) and that `sweep` removes a
sandbox a lost worker left; the rest of the chain runs on the operator's sandbox runners and is recorded.
"""
from dataclasses import asdict, replace
import asyncio
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest
import yaml
from openshell import SandboxClient, TlsConfig

from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.adapters.openshell_policy import CliPolicy
from corsair.adapters.openshell_preparation import OpenShellPreparation
from corsair.adapters.openshell_workspace import CliUpload, OpenShellTestWorkspace, WorkspaceConfig
from corsair.agents.environment.contracts import Toolchain
from corsair.composition.direct import StageModels, run_direct
from corsair.nodes.runtime.contracts import RuntimeInputs
from corsair.nodes.runtime.environment import RuntimeCatalog
from corsair.nodes.runtime.matrix import load
from corsair.nodes.source_fetch import WorkspaceBudget
from corsair.ports.execution import ExecutionLimits
from corsair.ports.sandbox import LifecycleLimits
from deploy.openshell.artifacts import TOOLS
from evals.fixture_e2e.case import (BASELINE_TEST, FIXTURE, scripted_assessment, scripted_authoring,
                                    scripted_identification, scripted_planning)
from evals.fixture_e2e.sandbox import DISCOVER, PREFIX, PYTHON, sandbox_case, sandbox_runners
from tests.agents.test_chain_environment_stage import SETUP, environment_model, ready_draft
from tests.qualification.gateway import gateway  # noqa: F401 (fixture)
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import LOCK, ROOT
from tests.qualification.test_adapter_lifecycle import adapter_gateway  # noqa: F401 (fixture)
from tests.qualification.test_fixture_e2e import MEMORY, cluster_clean
from tests.qualification.test_recovery import recovery_spec
from tests.qualification.test_test_workspace import capture, plain

ROW = 'cpython-3.12-pytest'
BASELINE_ID = 'test_existing.py::test_reads_existing_document'
BUILD = ('/usr/bin/env', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONPATH=.', PYTHON, '-I', '-c', 'import documents')
BASELINE = PREFIX + ('-q', BASELINE_ID)
PYPROJECT = '[project]\nname = "documents"\nrequires-python = ">=3.10"\n[tool.pytest.ini_options]\n'
SOURCES = ['src/corsair/adapters/openshell_preparation.py', 'src/corsair/adapters/openshell_policy.py',
           'src/corsair/adapters/openshell_workspace.py', 'src/corsair/composition/direct.py',
           'src/corsair/nodes/phase_policy.py', 'tests/qualification/test_environment_preparation.py',
           'policies/openshell/identity.yaml', 'deploy/runtime-lock.yaml', 'deploy/runtime-matrix.yaml',
           'pyproject.toml', 'uv.lock']


def setup_repository(kube, root: Path) -> tuple[Path, str]:
    """Bare repository holding the vulnerable module, its existing test and a pyproject; the case's setup source."""
    repo = root / 'setup.git'
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    git = lambda *args: kube.native(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never',
                                     '--git-dir', str(repo), *args], env=env).stdout.strip()
    git('init', '--bare', '--quiet')
    for name, data in (('documents.py', (FIXTURE / 'vulnerable' / 'documents.py').read_bytes()),
                       ('test_existing.py', BASELINE_TEST.encode()), ('pyproject.toml', PYPROJECT.encode())):
        raw = root / f'setup-{name}'
        raw.write_bytes(data); raw.chmod(0o400)
        git('update-index', '--add', '--cacheinfo', '100644', git('hash-object', '-w', str(raw)), name)
    commit = root / 'setup-commit.raw'
    commit.write_bytes(('tree ' + git('write-tree') + '\nauthor Fixture <fixture@invalid> 1 +0000\n'
                        'committer Fixture <fixture@invalid> 1 +0000\n\nenvironment preparation fixture\n').encode())
    return repo, git('hash-object', '-t', 'commit', '-w', str(commit))


@pytest.mark.environment_preparation
def test_environment_stage_in_an_openshell_preparation_sandbox(kube, adapter_gateway):  # noqa: F811
    native = adapter_gateway
    summary = dict(outcome='failed', scope='SPEC-0070 environment stage preparation; scripted environment model',
                   application_retries=0, stage_retries=0)
    kube.evidence.chmod(0o700)
    (kube.evidence/'environment-preparation-hashes.json').write_text(json.dumps(
        {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
    dirs = {name: kube.evidence/name for name in ('objects', 'source-receipts', 'lifecycle-receipts', 'verifier-receipts',
            'runner-receipts', 'upload-receipts', 'policy-receipts', 'preparation-receipts', 'staging', 'repos')}
    for directory in dirs.values():
        directory.mkdir(mode=0o700)
    owner = uuid4()
    workspace = WorkspaceConfig(dirs['staging'], '/tmp', 'workspace', PYTHON)
    limits = ExecutionLimits(262144, 120, 150, 512*1024*1024)
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
    env = {'PATH': '/usr/bin:/bin', 'XDG_CONFIG_HOME': str(native['mtls'].parents[3])}
    pin = lambda path: Executable(path, hashlib.sha256(path.read_bytes()).hexdigest())
    base_policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    try:
        image = summary['image'] = image_receipt('python')
        with (LocalArtifacts(dirs['objects'], max_bytes=4*1024*1024) as store,
              GitSource(pin(Path('/usr/bin/git')), pin(Path('/usr/bin/prlimit')), store=store, limits=SourceLimits(),
                        receipts=dirs['source-receipts']) as source,
              SandboxClient(native['endpoint'], tls=tls, timeout=60) as client,
              OpenShellLifecycle(client, spec=recovery_spec(image['image'], MEMORY), workspace='default', owner=owner,
                                 receipts=dirs['lifecycle-receipts'],
                                 limits=LifecycleLimits(ready_seconds=300, delete_seconds=90)) as lifecycle,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=workspace.remote_parent,
                                 limits=limits, receipts=dirs['verifier-receipts']) as verifier,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=workspace.remote_root,
                                 limits=limits, receipts=dirs['runner-receipts']) as execution,
              CliUpload(TOOLS/'openshell', LOCK['openshell']['cli']['binary_sha256'], gateway='qualification', env=env,
                        timeout_seconds=120, receipts=dirs['upload-receipts']) as upload,
              CliPolicy(TOOLS/'openshell', LOCK['openshell']['cli']['binary_sha256'], gateway='qualification', env=env,
                        timeout_seconds=60, receipts=dirs['policy-receipts']) as policy):
            setup = source.capture(*setup_repository(kube, dirs['repos']), uuid4())
            summary['setup_snapshot'] = plain(setup)

            def source_workspace(selected_image):
                # One prepared image per run: the gate's lifecycle is built for it.
                assert selected_image == image['image'], selected_image
                return OpenShellTestWorkspace(lifecycle, verifier, upload, store, setup, workspace)
            preparation = OpenShellPreparation(
                source_workspace, execution, policy, snapshot=setup, private_source=False, base_policy=base_policy,
                resolvers={'python': (PYTHON,)}, scratch_location='/tmp/corsair-scratch', receipts=dirs['preparation-receipts'],
                budget=WorkspaceBudget(workspace_bytes=1 << 28, reserve_bytes=1 << 30, node_path=str(ROOT)))

            # A lost worker: prepared, never released; the operator's sweep removes it.
            stray = preparation.prepare(Toolchain(toolchain_id=ROW, image=image['image'], language='python',
                                                  runtime='CPython 3.12', tools=()), uuid4())
            summary['stray'] = dict(handle=asdict(stray.handle), sweep=preparation.sweep())
            assert list(summary['stray']['sweep'].values()) == ['confirmed'], summary['stray']
            cluster_clean(kube, 400)

            snapshots = {variant: source.capture(*capture(kube, dirs['repos'], variant), uuid4())
                         for variant in ('vulnerable', 'fixed')}
            case = replace(sandbox_case(snapshots, image['manifest_digest'], dict(asdict(limits), memory=MEMORY)),
                           runtime=RuntimeInputs(files={'pyproject.toml': PYPROJECT.encode()}),
                           setup=SETUP.model_copy(update={'commit': setup.commit}))
            models = StageModels(identification=scripted_identification(),
                                 planning=scripted_planning(case.environment.discovery_command),
                                 authoring=scripted_authoring(), assessment=scripted_assessment(),
                                 environment=environment_model([BUILD, DISCOVER, BASELINE], ready_draft(
                                     build_command=list(BUILD), discovery_command=list(DISCOVER),
                                     baseline_test_command=list(BASELINE))))
            runners = sandbox_runners(lifecycle, verifier, execution, upload, store, snapshots, workspace)
            started = time.monotonic()
            run = asyncio.run(run_direct(case, models, runners, catalog=RuntimeCatalog(load(), {ROW: image['image']}),
                                         preparation=preparation))
            summary.update(elapsed_seconds=round(time.monotonic() - started, 1), stopped_at=run.stopped_at,
                           reason=run.reason, limitations=list(run.limitations),
                           environment=run.environment and run.environment.model_dump(mode='json'),
                           stages=[dict(stage=a.stage, failure=a.failure and repr(a.failure), cleanup=a.cleanup)
                                   for a in run.attempts])
            assert run.environment is not None and run.environment.status == 'ready', run.reason
            assert run.attempts[0].cleanup == 'confirmed', summary['stages']
            assert [r.command for r in run.environment.receipts] == [BUILD, DISCOVER, BASELINE]
            loaded = sorted(dirs['policy-receipts'].glob('*.result.json'))
            summary['policies'] = [json.loads(p.read_text()) for p in loaded]
            assert [(p['phase'], p['loaded']) for p in summary['policies']] == [('dependency_setup', True)] * 2
            cluster_clean(kube, 400)
            summary['cluster_sandboxes_absent'] = True
        summary['outcome'] = 'passed'
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error_detail=str(error)[:4096])
        raise
    finally:
        (kube.evidence/'environment-preparation.json').write_text(json.dumps(summary, indent=2, default=str))
