"""Live SPEC-0046 check: the native pytest runner on a real CPython 3.7 benchmark case in fresh OpenShell sandboxes.

CVE-2021-32839 (sqlparse) at its #42 baseline and fix commits, acquired by the SPEC-0037 host fetch into this run
and captured by GitSource; the capture must reproduce the manifests recorded in benchmarks/source-pins.json. The
approved patch adds the fix commit's own tests/test_format.py under a new path (the workspace refuses patches that
overlap captured source; upstream tests are read from the capture at run time, never committed here). The run qualifies discovery, execution, JUnit admission and probe behaviour on the 3.7
image only; it is not a security disposition (the upstream test is functional and passes at both commits).
"""
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.git_source import Executable, GitSource
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.adapters.openshell_workspace import CliUpload, OpenShellTestWorkspace, WorkspaceConfig
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.nodes.witness import witness_evidence
from corsair.ports.execution import ExecutionLimits
from corsair.ports.sandbox import LifecycleLimits
from corsair.ports.test_runner import ApprovedPatch, PatchFile, WitnessRequest
from deploy.openshell.artifacts import TOOLS
from evals.benchmark.sources import CAPTURE, case_dir
from tests.qualification.gateway import gateway
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import LOCK, ROOT
from tests.qualification.test_adapter_lifecycle import adapter_gateway
from tests.qualification.test_recovery import recovery_spec
from tests.qualification.test_test_workspace import plain, sandboxes_absent

CASE = 'CVE-2021-32839'
PYTHON = '/usr/local/bin/python3.7'
PREFIX = ('/usr/bin/env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONPATH=.', PYTHON,
          '-m', 'pytest', '-c', '/dev/null', '--rootdir', '.', '--noconftest', '--import-mode=importlib',
          '-p', 'no:cacheprovider', '--basetemp', '/tmp/corsair-scratch')
DISCOVER = PREFIX + ('--collect-only', '-q')
UPSTREAM_TEST = 'tests/test_format.py'
TEST_FILE = 'tests/test_corsair_upstream_format.py'
IDS = (TEST_FILE + '::TestFormat::test_strip_comments_single',
       TEST_FILE + '::TestFormat::test_strip_comments_preserves_linebreak')
# The identified function of the fix; the effect file never exists, so only reach and exits would be recorded.
REQUEST = WitnessRequest('sqlparse/filters/others.py', 'StripCommentsFilter._process', 'corsair-absent.txt')
SOURCES = ['tests/qualification/test_python37_case.py', 'src/corsair/adapters/openshell_workspace.py',
           'src/corsair/adapters/pytest_runner.py', 'src/corsair/reports/junit.py', 'src/corsair/nodes/witness.py',
           'src/corsair/nodes/witness_probe.py', 'evals/benchmark/sources.py', 'benchmarks/source-pins.json',
           'deploy/qualification/toolchains/python37/Dockerfile', 'deploy/qualification/toolchains/python37/requirements.txt',
           'policies/openshell/identity.yaml', 'deploy/runtime-lock.yaml', 'pyproject.toml', 'uv.lock']


@pytest.mark.python37_case
def test_real_python37_case_runs_through_the_runner(kube, adapter_gateway):
    native = adapter_gateway
    pins = json.loads((ROOT / 'benchmarks/source-pins.json').read_text())['cases'][CASE]
    revisions = {'baseline': (pins['first_parent']['commit'], pins['capture']['first_parent']['manifest']),
                 'fix': (pins['commit'], pins['capture']['commit']['manifest'])}
    fetched = Path(os.environ['CORSAIR_CASE_SOURCES']).resolve()
    repo = case_dir(fetched, CASE) / 'repo'
    summary = dict(outcome='failed', case=CASE, scope='SPEC-0046 runner on a real CPython 3.7 case; not a disposition',
                   application_retries=0, native_internal_attempts='unknown', runs=[])
    kube.evidence.chmod(0o700)
    (kube.evidence / 'python37-case-hashes.json').write_text(json.dumps(
        {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
    dirs = {name: kube.evidence / name for name in ('objects', 'source-receipts', 'lifecycle-receipts',
            'verifier-receipts', 'runner-receipts', 'upload-receipts', 'staging')}
    for directory in dirs.values():
        directory.mkdir(mode=0o700)
    owner = uuid4()
    config = WorkspaceConfig(dirs['staging'], '/tmp', 'workspace', PYTHON, max_files=256)
    limits = ExecutionLimits(262144, 120, 150, 512 * 1024 * 1024)
    tls = TlsConfig(ca_path=native['mtls'] / 'ca.crt', cert_path=native['mtls'] / 'tls.crt', key_path=native['mtls'] / 'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls'] / 'ca.crt', native['mtls'] / 'tls.crt', native['mtls'] / 'tls.key')
    env = {'PATH': '/usr/bin:/bin', 'XDG_CONFIG_HOME': str(native['mtls'].parents[3])}
    pin = lambda path: Executable(path, hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        image = image_receipt('python37')
        summary['image'] = image
        with (LocalArtifacts(dirs['objects'], max_bytes=CAPTURE.max_file_bytes) as store,
              GitSource(pin(Path('/usr/bin/git')), pin(Path('/usr/bin/prlimit')), store=store, limits=CAPTURE,
                        receipts=dirs['source-receipts'], skip_nonregular=True) as source,
              SandboxClient(native['endpoint'], tls=tls, timeout=60) as client,
              OpenShellLifecycle(client, spec=recovery_spec(image['image'], '512Mi'), workspace='default', owner=owner,
                                 receipts=dirs['lifecycle-receipts'], limits=LifecycleLimits(ready_seconds=300, delete_seconds=90)) as lifecycle,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=config.remote_parent, limits=limits,
                                 receipts=dirs['verifier-receipts']) as verifier,
              OpenShellExecution(connection, workspace='default', owner=owner, workdir=config.remote_root, limits=limits,
                                 receipts=dirs['runner-receipts']) as execution,
              CliUpload(TOOLS / 'openshell', LOCK['openshell']['cli']['binary_sha256'], gateway='qualification', env=env,
                        timeout_seconds=120, receipts=dirs['upload-receipts']) as upload):
            snapshots = {}
            for revision, (commit, manifest) in revisions.items():
                snapshot = snapshots[revision] = source.capture(repo, commit, uuid4())
                # The same bytes #42 captured: the manifest digest and size match the committed pins.
                assert (snapshot.manifest.sha256, snapshot.manifest.size) == (manifest['sha256'], manifest['size'])
            upstream = next(f for f in snapshots['fix'].files if f.path == UPSTREAM_TEST)
            patch = ApprovedPatch((PatchFile(TEST_FILE, store.get(upstream.artifact)),), (TEST_FILE,))
            summary['patch_sha256'] = patch.sha256
            for revision, snapshot in snapshots.items():
                workspace = OpenShellTestWorkspace(lifecycle, verifier, upload, store, snapshot, config)
                runner = PytestRunner(workspace, execution, store, PytestRunnerConfig(
                    PREFIX, '/tmp/corsair-junit.xml', config.remote_root, witness_record_path='/tmp/corsair-witness.json'))
                operation = uuid4()
                record = dict(revision=revision, operation=str(operation), manifest=plain(snapshot.manifest))
                summary['runs'].append(record)
                started = time.monotonic()
                result = runner.run(patch, control_test_id=IDS[0], security_test_id=IDS[1], discovery_command=DISCOVER,
                                    operation=operation, witness=REQUEST)
                record.update(elapsed_seconds=time.monotonic() - started, result=plain(result))
                assert result.workspace is not None, result.detail
                sandboxes_absent(kube, [result.workspace.handle.name], record)
                assert (result.failure_layer, result.cleanup) == (None, 'confirmed'), result.detail
                assert result.discovery.status == 'discovered' and set(result.discovery.test_ids) == set(IDS)
                assert result.execution.status == 'completed' and result.workspace.source == snapshot.manifest
                assert [case.outcome for case in result.execution.cases] == ['passed', 'passed']
                assert result.execution.receipt.native_exit == 0
                assert store.get(result.execution.junit) == result.execution.receipt.stdout
                # CPython 3.7 cannot host the probe's observation: the record names that and is refused.
                found = witness_evidence(result.witness, REQUEST, IDS[1])
                record['witness'] = dict(status=result.witness.status, reason=found.reason)
                assert result.witness.status == 'captured' and found.witness is None
                assert found.reason.startswith('witness probe unsupported on this runtime: CPython 3.7.'), found.reason
                record['outcome'] = 'passed'
        summary['outcome'] = 'passed'
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error_detail=str(error))
        raise
    finally:
        summary['staging_empty'] = not any(dirs['staging'].iterdir())
        (kube.evidence / 'python37-case.json').write_text(json.dumps(summary, indent=2, default=str))
