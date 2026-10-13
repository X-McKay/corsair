"""Live OpenShell TestWorkspace: reviewed SPEC-0018 pair through the real runner inside fresh sandboxes.

Captured fixture source plus the reviewed test file only; no model-authored code, no general source
delivery and no security disposition. Each run creates and deletes its own sandbox.
"""
from dataclasses import asdict, is_dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig
from pydantic import BaseModel

from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.adapters.openshell_workspace import CliUpload, OpenShellTestWorkspace, WorkspaceConfig
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.composition.evidence import run_evidence
from corsair.core.disposition import AssessmentEvidence, EnvironmentIdentity, ExpectedFailure, ObservationPlan, assess
from corsair.nodes.witness import witness_evidence
from corsair.ports.execution import ExecutionLimits
from corsair.ports.sandbox import LifecycleLimits
from corsair.ports.test_runner import ApprovedPatch, PatchFile, WitnessRequest
from deploy.openshell.artifacts import TOOLS
from tests.qualification.gateway import gateway
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import LOCK, ROOT
from tests.qualification.test_adapter_lifecycle import adapter_gateway
from tests.qualification.test_recovery import PYTHON, recovery_spec

FIXTURE = ROOT / 'benchmarks/fixtures/path-traversal'
IDS = ('test_documents.py::test_benign_control', 'test_documents.py::test_security_rejects_outside_read')
PREFIX = ('/usr/bin/env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONPATH=.', PYTHON,
          '-m', 'pytest', '-c', '/dev/null', '--rootdir', '.', '--noconftest', '--import-mode=importlib',
          '-p', 'no:cacheprovider', '--basetemp', '/tmp/corsair-scratch')
DISCOVER = PREFIX + ('--collect-only', '-q')
REPETITIONS = 2
# The admitted identification target for this fixture and the reviewed security assertion lines.
REQUEST = WitnessRequest('documents.py', 'read_document')
SECURITY_ASSERTION_LINES = (64, 65, 66)
WHEELS = ROOT / 'deploy/qualification/toolchains/python/wheels.json'
WITNESS_SOURCES = ['src/corsair/nodes/witness.py', 'src/corsair/nodes/witness_probe.py',
                   'src/corsair/core/disposition.py', 'src/corsair/composition/evidence.py']
SOURCES = ['src/corsair/adapters/openshell_workspace.py', 'src/corsair/adapters/pytest_runner.py',
           'src/corsair/ports/test_runner.py', 'src/corsair/reports/junit.py', 'src/corsair/adapters/openshell.py',
           'src/corsair/adapters/openshell_execution.py', 'src/corsair/adapters/git_source.py',
           'tests/qualification/test_test_workspace.py', 'benchmarks/fixtures/path-traversal/test_documents.py',
           'benchmarks/fixtures/path-traversal/vulnerable/documents.py',
           'benchmarks/fixtures/path-traversal/fixed/documents.py', 'policies/openshell/identity.yaml',
           'deploy/runtime-lock.yaml', 'pyproject.toml', 'uv.lock']


def plain(value):
    """JSON evidence: bytes as digest plus base64, typed claims as their own dump."""
    if is_dataclass(value):
        return {k: plain(v) for k, v in asdict(value).items()}
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, bytes):
        return dict(sha256=hashlib.sha256(value).hexdigest(), size=len(value), base64=base64.b64encode(value).decode())
    return value


def capture(kube, root, variant):
    """Bare repository holding only the variant source; GitSource captures the authoritative snapshot."""
    repo = root / f'{variant}.git'
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    git = lambda *args: kube.native(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never',
                                     '--git-dir', str(repo), *args], env=env).stdout.strip()
    git('init', '--bare', '--quiet')
    raw = root / f'{variant}-documents.py'
    raw.write_bytes((FIXTURE / variant / 'documents.py').read_bytes()); raw.chmod(0o400)
    git('update-index', '--add', '--cacheinfo', '100644', git('hash-object', '-w', str(raw)), 'documents.py')
    commit = root / f'{variant}-commit.raw'
    commit.write_bytes(('tree ' + git('write-tree') + '\nauthor Fixture <fixture@invalid> 1 +0000\n'
                        'committer Fixture <fixture@invalid> 1 +0000\n\ntest workspace fixture\n').encode())
    return repo, git('hash-object', '-t', 'commit', '-w', str(commit))


def sandboxes_absent(kube, names, record):
    """Native deletion confirmation plus the cluster's own view: no Sandbox CR or boundary pod remains."""
    deadline = time.monotonic() + 90
    while True:
        crs = [i['metadata']['name'] for i in kube.get('sandboxes', '-n', 'openshell')['items']]
        pods = [p['metadata']['name'] for p in kube.get('pods', '-n', 'openshell')['items']
                if p['metadata'].get('labels', {}).get('openshell.ai/boundary-role')]
        if not crs and not pods:
            record['cluster_sandboxes_absent'] = True
            return
        assert time.monotonic() < deadline, f'Sandbox resources remain: {crs} {pods} for {names}'
        time.sleep(2)


@pytest.mark.test_workspace
def test_reviewed_pair_runs_in_fresh_sandbox_workspaces(kube, adapter_gateway):
    reviewed_pair(kube, adapter_gateway, witness=False)


@pytest.mark.witness
def test_operator_probe_witness_lets_the_gate_verify_the_reviewed_pair(kube, adapter_gateway):
    """SPEC-0033: the same recipe with the operator probe; both records must be admitted and the gate must verify."""
    reviewed_pair(kube, adapter_gateway, witness=True)


def gate_result(runs, image, patch):
    """The SPEC-0027 gates over the live runs; environment identity is the declared shared recipe, not observed."""
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    identity = EnvironmentIdentity(image_digest=digest(image), recipe_sha256=digest(PREFIX),
                                   dependency_inventory_sha256=hashlib.sha256(WHEELS.read_bytes()).hexdigest(),
                                   policy_revision='qualification-default', limits_sha256=digest('execution-limits'))
    plan = ObservationPlan(control_test_id=IDS[0], security_test_id=IDS[1],
                           expected_failure=ExpectedFailure(exception_type='AssertionError', path='test_documents.py',
                                                            function='test_security_rejects_outside_read',
                                                            assertion_lines=SECURITY_ASSERTION_LINES),
                           expected_safe_behavior='ValueError', frozen_patch_sha256=patch.sha256)
    evidence = {}
    for variant, revision in (('vulnerable', 'baseline'), ('fixed', 'candidate')):
        evidence[revision] = tuple(run_evidence(result, environment=identity, witness=found.witness,
                                                sandbox_events=found.sandbox_events)
                                   for v, result, found in runs if v == variant)
    return assess(AssessmentEvidence(plan=plan, **evidence))


def reviewed_pair(kube, adapter_gateway, *, witness):
    native = adapter_gateway
    name = 'witness' if witness else 'test-workspace'
    summary = dict(outcome='failed', scope='reviewed SPEC-0018 pair through OpenShellTestWorkspace and PytestRunner',
                   application_retries=0, native_internal_attempts='unknown', runs=[],
                   witness=('operator probe in the test interpreter (SPEC-0033); tamper-evident, not tamper-proof'
                            if witness else 'absent: JUnit and captured output are workload claims'))
    witnessed = []
    kube.evidence.chmod(0o700)
    (kube.evidence/f'{name}-hashes.json').write_text(json.dumps(
        {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES + (WITNESS_SOURCES if witness else [])},
        indent=2))
    dirs = {name: kube.evidence/name for name in ('objects', 'source-receipts', 'lifecycle-receipts',
            'verifier-receipts', 'runner-receipts', 'upload-receipts', 'staging', 'repos')}
    for directory in dirs.values():
        directory.mkdir(mode=0o700)
    reviewed = (FIXTURE/'test_documents.py').read_bytes()
    patch = ApprovedPatch((PatchFile('test_documents.py', reviewed),), ('test_documents.py',))
    owner = uuid4()
    config = WorkspaceConfig(dirs['staging'], '/tmp', 'workspace', PYTHON)
    limits = ExecutionLimits(262144, 120, 150, 512*1024*1024)
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
    # The gateway fixture registers its native CLI gateway under this private XDG configuration root.
    env = {'PATH': '/usr/bin:/bin', 'XDG_CONFIG_HOME': str(native['mtls'].parents[3])}
    pin = lambda path: Executable(path, hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        image = image_receipt('python')
        summary['image'] = image
        with (LocalArtifacts(dirs['objects'], max_bytes=1024*1024) as store,
              GitSource(pin(Path('/usr/bin/git')), pin(Path('/usr/bin/prlimit')), store=store, limits=SourceLimits(),
                        receipts=dirs['source-receipts']) as source,
              SandboxClient(native['endpoint'], tls=tls, timeout=60) as client,
              OpenShellLifecycle(client, spec=recovery_spec(image['image'], '512Mi'), workspace='default', owner=owner,
                                 receipts=dirs['lifecycle-receipts'], limits=LifecycleLimits(ready_seconds=300, delete_seconds=90)) as lifecycle,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=config.remote_parent, limits=limits,
                                 receipts=dirs['verifier-receipts']) as verifier,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=config.remote_root, limits=limits,
                                 receipts=dirs['runner-receipts']) as execution,
              CliUpload(TOOLS/'openshell', LOCK['openshell']['cli']['binary_sha256'], gateway='qualification', env=env,
                        timeout_seconds=120, receipts=dirs['upload-receipts']) as upload):
            for variant in ('vulnerable', 'fixed'):
                repo, commit = capture(kube, dirs['repos'], variant)
                snapshot = source.capture(repo, commit, uuid4())
                workspace = OpenShellTestWorkspace(lifecycle, verifier, upload, store, snapshot, config)
                runner = PytestRunner(workspace, execution, store, PytestRunnerConfig(
                    PREFIX, '/tmp/corsair-junit.xml', config.remote_root,
                    witness_record_path='/tmp/corsair-witness.json' if witness else None))
                for repetition in range(REPETITIONS):
                    operation = uuid4()
                    record = dict(variant=variant, repetition=repetition+1, operation=str(operation), snapshot=plain(snapshot))
                    summary['runs'].append(record)
                    started = time.monotonic()
                    result = runner.run(patch, control_test_id=IDS[0], security_test_id=IDS[1], discovery_command=DISCOVER,
                                        operation=operation, witness=REQUEST if witness else None)
                    record.update(elapsed_seconds=time.monotonic()-started, result=plain(result))
                    assert result.workspace is not None, result.detail
                    sandboxes_absent(kube, [result.workspace.handle.name], record)
                    assert (result.failure_layer, result.cleanup) == (None, 'confirmed'), result.detail
                    assert result.discovery.status == 'discovered' and set(result.discovery.test_ids) == set(IDS)
                    assert result.execution.status == 'completed' and result.workspace.source == snapshot.manifest
                    control, security = result.execution.cases
                    assert control.outcome == 'passed'
                    if variant == 'vulnerable':
                        assert security.outcome == 'failed' and result.execution.receipt.native_exit == 1
                        failure = security.failure
                        assert (failure.type, failure.path, failure.function) == (
                            'AssertionError', 'test_documents.py', 'test_security_rejects_outside_read')
                    else:
                        assert security.outcome == 'passed' and result.execution.receipt.native_exit == 0
                    assert store.get(result.execution.junit) == result.execution.receipt.stdout
                    if witness:
                        found = witness_evidence(result.witness, REQUEST, IDS[1])
                        record['witness'] = dict(reason=found.reason, sandbox_events=None if found.sandbox_events is None
                                                 else [e.model_dump() for e in found.sandbox_events],
                                                 witness=found.witness.model_dump() if found.witness else None)
                        assert found.reason == 'admitted' and found.sandbox_events == (), found.reason
                        observed = (found.witness.path_reached, found.witness.effect, found.witness.safe_behavior)
                        assert observed == ((True, 'observed', None) if variant == 'vulnerable'
                                            else (True, 'absent', 'ValueError'))
                        witnessed.append((variant, result, found))
                    record['outcome'] = 'passed'
            if witness:
                gate = gate_result(witnessed, image, patch)
                summary['gate'] = gate.model_dump()
                assert gate.permitted.model_dump() == dict(execution='completed', finding='reproduced', fix='verified')
                assert gate.limitations == ()
        summary['outcome'] = 'passed'
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error_detail=str(error))
        raise
    finally:
        summary['staging_empty'] = not any(dirs['staging'].iterdir())
        (kube.evidence/f'{name}.json').write_text(json.dumps(summary, indent=2, default=str))
