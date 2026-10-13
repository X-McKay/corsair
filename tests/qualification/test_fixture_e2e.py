"""Live E2E-0 over the OpenShell test workspace: the SPEC-0018 chain with every test run in a fresh sandbox.

One all-scripted control run first proves the sandbox route end to end; then each live run puts the
named stages on the operator's local model. The gate asserts the control and the runtime (confirmed
cleanup, no remaining Sandbox resources); live agent outcomes are recorded, never asserted. Every run
requests the SPEC-0033 operator probe witness; the gate verdict and witness admission are recorded, and the
witness itself is qualified by `make qualify-witness`, not here.
"""
from dataclasses import asdict
import asyncio
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution
from corsair.adapters.openshell_workspace import CliUpload, WorkspaceConfig
from corsair.inference.config import load_inference
from corsair.ports.execution import ExecutionLimits
from corsair.ports.sandbox import LifecycleLimits
from deploy.openshell.artifacts import TOOLS
from evals.fixture_e2e.run import STAGES, record_run, stage_configs, summary as run_summary
from evals.fixture_e2e.sandbox import PYTHON, sandbox_case, sandbox_runners
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import LOCK, ROOT
from tests.qualification.gateway import gateway  # noqa: F401 (fixture)
from tests.qualification.test_adapter_lifecycle import adapter_gateway  # noqa: F401 (fixture)
from tests.qualification.test_recovery import recovery_spec
from tests.qualification.test_test_workspace import capture, plain

MEMORY = '512Mi'
SOURCES = ['evals/fixture_e2e/case.py', 'evals/fixture_e2e/reviewed.py', 'evals/fixture_e2e/run.py',
           'evals/fixture_e2e/sandbox.py', 'src/corsair/composition/direct.py', 'src/corsair/composition/evidence.py',
           'src/corsair/adapters/openshell_workspace.py', 'src/corsair/adapters/pytest_runner.py',
           'src/corsair/adapters/openshell.py', 'src/corsair/adapters/openshell_execution.py',
           'src/corsair/core/disposition.py', 'src/corsair/nodes/witness.py', 'src/corsair/nodes/witness_probe.py', 'tests/qualification/test_fixture_e2e.py',
           'benchmarks/fixtures/path-traversal/test_documents.py',
           'benchmarks/fixtures/path-traversal/vulnerable/documents.py',
           'benchmarks/fixtures/path-traversal/fixed/documents.py', 'policies/openshell/identity.yaml',
           'deploy/qualification/toolchains/python/wheels.json', 'deploy/runtime-lock.yaml', 'pyproject.toml',
           'uv.lock']


def cluster_clean(kube, seconds):
    """The cluster's own view after a run: no Sandbox CR or boundary pod remains in the namespace.

    A stage timeout cancels the agent while a development run may still be finishing in its worker
    thread, which then releases its sandbox; the deadline covers one prepare plus two executions.
    """
    deadline = time.monotonic() + seconds
    while True:
        crs = [i['metadata']['name'] for i in kube.get('sandboxes', '-n', 'openshell')['items']]
        pods = [p['metadata']['name'] for p in kube.get('pods', '-n', 'openshell')['items']
                if p['metadata'].get('labels', {}).get('openshell.ai/boundary-role')]
        if not crs and not pods:
            return
        assert time.monotonic() < deadline, f'Sandbox resources remain: {crs} {pods}'
        time.sleep(5)


def native_record(evidence: Path) -> list[dict]:
    """Per native runner observation: purpose, failure layer, cleanup and outcomes, from the saved journal."""
    entries = json.loads((evidence / 'native-runs.json').read_text())
    out = []
    for entry in entries:
        observed = entry['observed'] or {}
        execution = observed.get('execution') or {}
        discovery = observed.get('discovery') or {}
        out.append(dict(purpose=entry['purpose'], failure=entry['failure'], failure_layer=observed.get('failure_layer'),
                        cleanup=observed.get('cleanup'), detail=(observed.get('detail') or '')[:512],
                        discovered=discovery.get('test_ids'), discovery_status=discovery.get('status'),
                        cases=[(c['test_id'], c['outcome']) for c in execution.get('cases') or ()],
                        native_exit=(execution.get('receipt') or {}).get('native_exit')))
    return out


@pytest.mark.fixture_e2e
def test_fixture_chain_in_fresh_sandbox_workspaces(kube, adapter_gateway, request):  # noqa: F811
    native = adapter_gateway
    live = tuple(stage for stage in (request.config.getoption('--e2e-live') or '').split(',') if stage)
    repetitions = int(request.config.getoption('--e2e-runs') or 1)
    provider = request.config.getoption('--provider-config')
    assert not set(live) - set(STAGES) and 0 <= repetitions <= 6, (live, repetitions)
    config = load_inference(Path(provider)) if live and repetitions else None
    profile_path = request.config.getoption('--e2e-stage-profiles')
    profiles = json.loads(Path(profile_path).read_bytes()) if profile_path and config else None
    if profiles is not None:
        stage_configs(config, profiles)
    summary = dict(outcome='failed', scope='SPEC-0018 E2E-0 chain through OpenShellTestWorkspace; fixture only',
                   live_stages=list(live), stage_profiles=None, application_retries=0, stage_retries=0, runs=[],
                   witness='SPEC-0033 operator probe in the test interpreter; tamper-evident, not tamper-proof')
    summary['stage_profiles'] = profiles
    kube.evidence.chmod(0o700)
    (kube.evidence/'fixture-e2e-hashes.json').write_text(json.dumps(
        {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
    dirs = {name: kube.evidence/name for name in ('objects', 'source-receipts', 'lifecycle-receipts',
            'verifier-receipts', 'runner-receipts', 'upload-receipts', 'staging', 'repos', 'e2e')}
    for directory in dirs.values():
        directory.mkdir(mode=0o700)
    owner = uuid4()
    workspace = WorkspaceConfig(dirs['staging'], '/tmp', 'workspace', PYTHON)
    limits = ExecutionLimits(262144, 120, 150, 512*1024*1024)
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
    env = {'PATH': '/usr/bin:/bin', 'XDG_CONFIG_HOME': str(native['mtls'].parents[3])}
    pin = lambda path: Executable(path, hashlib.sha256(path.read_bytes()).hexdigest())
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
                        timeout_seconds=120, receipts=dirs['upload-receipts']) as upload):
            snapshots = {variant: source.capture(*capture(kube, dirs['repos'], variant), uuid4())
                         for variant in ('vulnerable', 'fixed')}
            summary['snapshots'] = {variant: plain(snapshot) for variant, snapshot in snapshots.items()}
            case = sandbox_case(snapshots, image['manifest_digest'], dict(asdict(limits), memory=MEMORY))
            runners = sandbox_runners(lifecycle, verifier, execution, upload, store, snapshots, workspace)
            route = dict(route='openshell_test_workspace', image=image['image'], memory=MEMORY,
                         workspace_root=workspace.remote_root, execution_limits=asdict(limits))
            plan = [('control-scripted', ())] + [(f'live-{index+1}', live) for index in range(repetitions)]
            for label, stages in plan:
                evidence = dirs['e2e']/label
                evidence.mkdir(mode=0o700)
                record = dict(label=label, live_stages=list(stages))
                summary['runs'].append(record)
                started = time.monotonic()
                try:
                    run = asyncio.run(record_run(evidence, stages, config if stages else None, case, runners, route,
                                                     profiles if stages else None))
                finally:
                    record['elapsed_seconds'] = round(time.monotonic()-started, 1)
                    if (evidence/'native-runs.json').exists():
                        record['native_runs'] = native_record(evidence)
                record.update(run_summary(run), limitations=list(run.limitations),
                              witnesses=[w.reason for w in run.witnesses])
                cluster_clean(kube, 400)
                record['cluster_sandboxes_absent'] = True
                assert all(n['cleanup'] == 'confirmed' for n in record['native_runs']), record['native_runs']
                if not stages:
                    # The control: the reviewed bytes through every real sandbox step; the verdict is recorded.
                    assert (run.stopped_at, run.reason) == (None, 'complete'), run.reason
                    baseline, candidate = run.executions
                    assert [c.outcome for c in baseline.observed.execution.cases] == ['passed', 'failed']
                    assert [c.outcome for c in candidate.observed.execution.cases] == ['passed', 'passed']
                    assert record['gate'] is not None and record['gate']['execution'] == 'completed', record['gate']
                record['outcome'] = 'recorded'
        summary['outcome'] = 'passed'
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error_detail=str(error)[:4096])
        raise
    finally:
        summary['staging_empty'] = not any(dirs['staging'].iterdir())
        (kube.evidence/'fixture-e2e.json').write_text(json.dumps(summary, indent=2, default=str))
