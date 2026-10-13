"""OpenShell TestWorkspace over fake lifecycle/upload ports and the real operator verifier on local paths."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell_workspace import (VERIFY, CliUpload, OpenShellTestWorkspace, UploadError,
                                                  WorkspaceConfig, WorkspaceError, _patch_manifest)
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.ports.artifacts import SourceFile, SourceSnapshot
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PreparedWorkspace
from tests.unit.test_pytest_runner import DISCOVER, FIXTURE, PREFIX

PYTHON = '/usr/local/bin/python3.12'
SOURCE = {'pkg/app.py': ('100644', b'def run():\n    return 1\n'), 'tool.sh': ('100755', b'#!/bin/sh\nexit 0\n')}
PATCH = ApprovedPatch((PatchFile('tests/test_app.py', b'def test_a(): pass\n'),), ('tests/test_app.py',))


@pytest.fixture
def store(tmp_path):
    root = tmp_path / 'objects'; root.mkdir(mode=0o700)
    with LocalArtifacts(root, max_bytes=1024*1024) as artifacts:
        yield artifacts


def snapshot(store, files=SOURCE):
    entries = tuple(SourceFile(path, mode, '0'*40, store.put(data)) for path, (mode, data) in sorted(files.items()))
    return SourceSnapshot('1'*40, '2'*40, entries, store.put(b'manifest'))


class Lifecycle:
    def __init__(self, *, fail=None):
        self.calls, self.fail = [], fail or {}

    def create(self, operation):
        self.calls.append(('create', operation))
        if 'create' in self.fail: raise self.fail['create']
        return SandboxHandle(str(uuid4()), 'cs-test', 'default', 'owner', str(operation))

    def wait_ready(self, handle, operation):
        self.calls.append(('wait_ready', operation))
        if 'wait_ready' in self.fail: raise self.fail['wait_ready']

    def delete(self, handle, operation):
        self.calls.append(('delete', operation))
        if 'delete' in self.fail: raise self.fail['delete']


class Upload:
    """Local stand-in for the native CLI: tar semantics preserve file and directory modes."""
    def __init__(self, *, error=None, tamper=None):
        self.calls, self.error, self.tamper = [], error, tamper

    def upload(self, handle, local, remote_parent, operation):
        self.calls.append((local, remote_parent, operation))
        if self.error: raise self.error
        shutil.copytree(local, Path(remote_parent) / local.name)
        if self.tamper: self.tamper(Path(remote_parent) / local.name)


class Verifier:
    """Runs only the fixed operator verifier, locally; anything else would be workload code."""
    def __init__(self):
        self.calls = []

    def execute(self, handle, command, operation):
        assert command[:6] == (PYTHON, '-I', '-S', '-B', '-c', VERIFY)
        self.calls.append(operation)
        done = subprocess.run([sys.executable, *command[1:]], capture_output=True, timeout=30, env={})
        return ExecutionReceipt(str(operation), handle, 'local', 0.1, 'acknowledged', 'terminal_observed', 'terminal',
                                stdout=done.stdout, stderr=done.stderr, native_exit=done.returncode,
                                worker_cleanup='confirmed')


def workspace(store, tmp_path, *, lifecycle=None, upload=None, files=SOURCE):
    staging, remote = tmp_path / 'staging', tmp_path / 'remote'
    staging.mkdir(mode=0o700, exist_ok=True); remote.mkdir(mode=0o700, exist_ok=True)
    config = WorkspaceConfig(staging, str(remote), 'workspace', PYTHON)
    parts = lifecycle or Lifecycle(), Verifier(), upload or Upload()
    return OpenShellTestWorkspace(*parts, store, snapshot(store, files), config), parts, config


def modes(root):
    return {p.relative_to(root).as_posix(): p.stat().st_mode & 0o777 for p in sorted(root.rglob('*'))}


def test_prepare_delivers_source_and_patch_and_admits_exact_tree(store, tmp_path):
    adapter, (lifecycle, verifier, upload), config = workspace(store, tmp_path)
    operation = uuid4()
    prepared = adapter.prepare(PATCH, operation)
    assert [c[0] for c in lifecycle.calls] == ['create', 'wait_ready']
    assert lifecycle.calls[0][1] == uuid5(operation, 'create') and prepared.handle.creation_operation == str(uuid5(operation, 'create'))
    assert verifier.calls == [uuid5(operation, 'absent'), uuid5(operation, 'verify')]
    assert len(upload.calls) == 1 and upload.calls[0][1] == config.remote_parent
    root = Path(config.remote_root)
    assert modes(root) == {'pkg': 0o700, 'pkg/app.py': 0o400, 'tests': 0o700, 'tests/test_app.py': 0o400, 'tool.sh': 0o500}
    assert prepared.source == adapter._snapshot.manifest and prepared.patch_sha256 == PATCH.sha256
    manifest = json.loads(store.get(prepared.tests))
    assert manifest == dict(version=1, patch_sha256=PATCH.sha256, files=[dict(
        path='tests/test_app.py', sha256=hashlib.sha256(PATCH.files[0].content).hexdigest(), size=len(PATCH.files[0].content))])
    assert not any(config.staging.iterdir()), 'host staging copy is removed once the CLI exits'
    assert adapter.release(prepared, operation) == 'confirmed' and lifecycle.calls[-1] == ('delete', uuid5(operation, 'release'))


@pytest.mark.parametrize('patch', [
    ApprovedPatch((PatchFile('pkg/app.py', b'x'),), ('pkg/app.py',)),
    ApprovedPatch((PatchFile('tool.sh/test_x.py', b'x'),), ('tool.sh/test_x.py',)),
    ApprovedPatch((PatchFile('pkg', b'x'),), ('pkg',))])
def test_patch_overlapping_source_is_refused_before_any_sandbox(store, tmp_path, patch):
    adapter, (lifecycle, verifier, upload), config = workspace(store, tmp_path)
    with pytest.raises(ValueError, match='overlap'):
        adapter.prepare(patch, uuid4())
    assert lifecycle.calls == [] and upload.calls == [] and not any(config.staging.iterdir())


def test_workspace_bounds_refuse_oversize_source(store, tmp_path):
    files = {f'f{n}.py': ('100644', b'x') for n in range(64)}
    with pytest.raises(ValueError, match='bound'):
        workspace(store, tmp_path, files=files)
    with pytest.raises(ValueError, match='regular'):
        workspace(store, tmp_path, files={'link': ('120000', b'target')})


def corrupt(root): os.chmod(root/'pkg/app.py', 0o600); (root/'pkg/app.py').write_bytes(b'changed'); os.chmod(root/'pkg/app.py', 0o400)
def extra(root): (root/'extra.py').write_bytes(b'')
def link(root): os.symlink('/etc/passwd', root/'tests/link')
def loose(root): os.chmod(root/'tool.sh', 0o700)
def hardlink(root): os.link(root/'pkg/app.py', root/'pkg/second')


@pytest.mark.parametrize('tamper', [corrupt, extra, link, loose, hardlink])
def test_any_remote_difference_refuses_and_discards_the_sandbox(store, tmp_path, tamper):
    adapter, (lifecycle, verifier, upload), config = workspace(store, tmp_path, upload=Upload(tamper=tamper))
    operation = uuid4()
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, operation)
    assert (refused.value.layer, refused.value.cleanup) == ('admission', 'confirmed')
    assert lifecycle.calls[-1] == ('delete', uuid5(operation, 'discard')) and len(upload.calls) == 1
    assert refused.value.receipt.operation == str(uuid5(operation, 'verify'))


def test_existing_remote_root_is_refused_before_upload(store, tmp_path):
    adapter, (lifecycle, verifier, upload), config = workspace(store, tmp_path)
    Path(config.remote_root).mkdir()
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, uuid4())
    assert refused.value.layer == 'admission' and 'before upload' in refused.value.detail and upload.calls == []
    assert refused.value.cleanup == 'confirmed'


@pytest.mark.parametrize('delivery', ['unknown', 'not_dispatched'])
def test_upload_failure_is_never_replayed_and_discards(store, tmp_path, delivery):
    upload = Upload(error=UploadError('native upload exit 1', delivery))
    adapter, (lifecycle, verifier, _), config = workspace(store, tmp_path, upload=upload)
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, uuid4())
    assert refused.value.layer == 'upload' and f'delivery {delivery}' in refused.value.detail
    assert len(upload.calls) == 1 and len(verifier.calls) == 1 and lifecycle.calls[-1][0] == 'delete'
    assert not any(config.staging.iterdir())


def test_unconfirmed_discard_and_release_stay_unconfirmed(store, tmp_path):
    lifecycle = Lifecycle(fail={'delete': RuntimeError('deletion not observed')})
    adapter, _, _ = workspace(store, tmp_path, lifecycle=lifecycle, upload=Upload(tamper=extra))
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, uuid4())
    assert refused.value.cleanup == 'unconfirmed'
    handle = SandboxHandle('id', 'n', 'default', 'owner', 'op')
    prepared = PreparedWorkspace(handle, store.put(b's'), store.put(b't'), PATCH.sha256)
    assert adapter.release(prepared, uuid4()) == 'unconfirmed'


def test_failed_create_is_unconfirmed_without_a_handle(store, tmp_path):
    lifecycle = Lifecycle(fail={'create': RuntimeError('create delivery unknown')})
    adapter, (_, verifier, upload), config = workspace(store, tmp_path, lifecycle=lifecycle)
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, uuid4())
    assert (refused.value.layer, refused.value.cleanup) == ('sandbox', 'unconfirmed')
    assert [c[0] for c in lifecycle.calls] == ['create'] and verifier.calls == upload.calls == []
    assert not any(config.staging.iterdir())


def test_cli_upload_argv_pin_and_unknown_delivery(tmp_path):
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    log = tmp_path / 'argv'
    binary = tmp_path / 'openshell'
    binary.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {log}\nexit "${{CODE:-0}}"\n'); binary.chmod(0o700)
    pin = hashlib.sha256(binary.read_bytes()).hexdigest()
    handle = SandboxHandle('id', 'cs-abc', 'default', 'owner', 'op')
    with CliUpload(binary, pin, gateway='qualification', env={'PATH': '/usr/bin:/bin'}, timeout_seconds=5, receipts=receipts) as cli:
        operation = uuid4()
        cli.upload(handle, tmp_path / 'workspace', '/tmp', operation)
        assert log.read_text().splitlines() == ['--gateway', 'qualification', '--workspace', 'default', 'sandbox', 'upload',
                                                '--no-git-ignore', 'cs-abc', str(tmp_path / 'workspace'), '/tmp']
        assert json.loads((receipts / f'{operation}.result.json').read_text())['delivery'] == 'acknowledged'
    with CliUpload(binary, pin, gateway='q', env={'PATH': '/usr/bin:/bin', 'CODE': '3'}, timeout_seconds=5, receipts=receipts) as cli:
        operation = uuid4()
        with pytest.raises(UploadError) as failed:
            cli.upload(handle, tmp_path / 'workspace', '/tmp', operation)
        assert failed.value.delivery == 'unknown'
        assert json.loads((receipts / f'{operation}.result.json').read_text())['exit_code'] == 3
    log.unlink()
    with CliUpload(binary, '0'*64, gateway='q', env={}, timeout_seconds=5, receipts=receipts) as cli:
        with pytest.raises(UploadError) as failed:
            cli.upload(handle, tmp_path / 'workspace', '/tmp', uuid4())
        assert failed.value.delivery == 'not_dispatched' and not log.exists()


class LocalRun:
    """Test-only host execution of the reviewed SPEC-0018 bytes in the delivered local root."""
    def __init__(self, root):
        self.root = root

    def execute(self, handle, command, operation):
        argv = [sys.executable if token == 'python3.12' else token for token in command]
        started = time.monotonic()
        done = subprocess.run(argv, cwd=self.root, env={'PATH': os.environ['PATH']}, capture_output=True, timeout=60)
        return ExecutionReceipt(str(operation), handle, 'local', time.monotonic()-started, 'acknowledged',
                                'terminal_observed', 'terminal', stdout=done.stdout, stderr=done.stderr,
                                native_exit=done.returncode, worker_cleanup='confirmed')


@pytest.mark.parametrize('variant', ['vulnerable', 'fixed'])
def test_runner_composes_over_the_workspace_with_repository_relative_ids(store, tmp_path, variant):
    reviewed = (FIXTURE / 'test_documents.py').read_bytes()
    files = {'documents.py': ('100644', (FIXTURE / variant / 'documents.py').read_bytes())}
    adapter, (lifecycle, _, _), config = workspace(store, tmp_path, files=files)
    patch = ApprovedPatch((PatchFile('test_documents.py', reviewed),), ('test_documents.py',))
    ids = ('test_documents.py::test_benign_control', 'test_documents.py::test_security_rejects_outside_read')
    runner = PytestRunner(adapter, LocalRun(config.remote_root), store,
                          PytestRunnerConfig(PREFIX, str(tmp_path / 'junit.xml'), config.remote_root))
    result = runner.run(patch, control_test_id=ids[0], security_test_id=ids[1], discovery_command=DISCOVER, operation=uuid4())
    assert (result.failure_layer, result.cleanup, result.execution.status) == (None, 'confirmed', 'completed'), result.detail
    assert store.get(result.workspace.tests) == _patch_manifest(patch, {f.path: store.put(f.content) for f in patch.files})
    assert lifecycle.calls[-1][0] == 'delete' and result.execution.claims.claims.tests_sha256 == result.workspace.tests.sha256
    security = result.execution.cases[1]
    assert security.outcome == ('failed' if variant == 'vulnerable' else 'passed')
    if variant == 'vulnerable':
        assert (security.failure.path, security.failure.function) == ('test_documents.py', 'test_security_rejects_outside_read')



def test_unexpected_error_after_create_still_discards(store, tmp_path):
    adapter, (lifecycle, _, upload), _ = workspace(store, tmp_path, upload=Upload(error=OSError('host failure')))
    operation = uuid4()
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, operation)
    assert (refused.value.layer, refused.value.cleanup) == ('sandbox', 'confirmed')
    assert lifecycle.calls[-1] == ('delete', uuid5(operation, 'discard')) and len(upload.calls) == 1


def test_timed_out_upload_retains_staging_for_unknown_descendants(store, tmp_path):
    upload = Upload(error=UploadError('timed out', 'unknown', descendants_unknown=True))
    adapter, (lifecycle, _, _), config = workspace(store, tmp_path, upload=upload)
    operation = uuid4()
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, operation)
    assert (refused.value.layer, refused.value.staging, refused.value.cleanup) == ('upload', 'retained', 'confirmed')
    assert (config.staging / operation.hex / 'workspace' / 'tests/test_app.py').read_bytes() == PATCH.files[0].content


def cli(tmp_path, code=0, sleep=0):
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700, exist_ok=True)
    binary = tmp_path / 'openshell'
    binary.write_text(f'#!/bin/sh\nsleep {sleep}\nexit {code}\n'); binary.chmod(0o700)
    return CliUpload(binary, hashlib.sha256(binary.read_bytes()).hexdigest(), gateway='q', env={'PATH': '/usr/bin:/bin'},
                     timeout_seconds=1, receipts=receipts), receipts


def test_cli_timeout_marks_descendants_unknown(tmp_path):
    upload, receipts = cli(tmp_path, sleep=5)
    with upload, pytest.raises(UploadError) as failed:
        upload.upload(SandboxHandle('id', 'n', 'default', 'o', 'op'), tmp_path, '/tmp', uuid4())
    assert (failed.value.delivery, failed.value.descendants_unknown) == ('unknown', True)


@pytest.mark.parametrize('code, delivery', [(0, 'acknowledged'), (3, 'unknown')])
def test_lost_result_receipt_keeps_known_delivery(tmp_path, code, delivery):
    upload, receipts = cli(tmp_path, code=code)
    operation = uuid4()
    with upload:
        original = upload._journal.write
        def fail_result(op, suffix, value):
            if suffix == 'result': raise OSError(28, 'No space left on device')
            original(op, suffix, value)
        upload._journal.write = fail_result
        with pytest.raises(UploadError) as failed:
            upload.upload(SandboxHandle('id', 'n', 'default', 'o', 'op'), tmp_path, '/tmp', operation)
    assert failed.value.delivery == delivery and 'No space left' in failed.value.storage_error
    assert (receipts / f'{operation}.intent.json').exists() and not (receipts / f'{operation}.result.json').exists()


def test_receipt_storage_failure_is_attributed_to_upload(store, tmp_path):
    upload = Upload(error=UploadError('result receipt storage: full', 'acknowledged', storage_error='full'))
    adapter, _, _ = workspace(store, tmp_path, upload=upload)
    with pytest.raises(WorkspaceError) as refused:
        adapter.prepare(PATCH, uuid4())
    assert refused.value.layer == 'upload' and 'delivery acknowledged; receipt storage full' in refused.value.detail
    assert (refused.value.staging, refused.value.cleanup) == ('removed', 'confirmed')
