"""Native v0.1.3 SDK lifecycle/exec and CLI transfers; no application adapter."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import time
import uuid

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from openshell import SandboxClient, TlsConfig, DeletionOutcome
from openshell._proto import openshell_pb2, sandbox_pb2
import pytest
import yaml

from tests.qualification.gateway import gateway, inspect_identity, wait_resource_absent, workspace_storage
from tests.qualification.support import ROOT, LOCK

WORKSPACE = 'default'


def inert_spec():
    """Construct only this fixed operator fixture with native spec types."""
    policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    assert set(policy) == {'version', 'filesystem_policy', 'landlock', 'network_policies'}
    assert policy['network_policies'] == {} and policy['landlock'] == {'compatibility': 'hard_requirement'}
    return openshell_pb2.SandboxSpec(
        template=openshell_pb2.SandboxTemplate(image=LOCK['openshell']['images']['workload'], resources={'cpu': '1', 'memory': '512Mi'}),
        policy=sandbox_pb2.SandboxPolicy(version=policy['version'], filesystem=sandbox_pb2.FilesystemPolicy(**policy['filesystem_policy']), landlock=sandbox_pb2.LandlockPolicy(**policy['landlock'])),
        command=['/bin/sleep', '600'], tty=False,
    )


def native_value(value):
    if isinstance(value, Message):
        return MessageToDict(value, preserving_proto_field_name=True)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [native_value(item) for item in value]
    return value


class SdkReceipts:
    """Host-owned observations of these explicit native SDK calls; no retries."""
    def __init__(self, client, evidence):
        self.client, self.evidence, self.counter = client, evidence, 0

    def call(self, method, *args, **kwargs):
        self.counter += 1
        receipt = {'operation': method, 'args': list(args), 'kwargs': {k: native_value(v) for k, v in kwargs.items()}, 'started_at': datetime.now(timezone.utc).isoformat(), 'completion': 'unknown'}
        # Only the qualification's synthetic stdin is permitted, encoded by hash.
        if isinstance(receipt['kwargs'].get('stdin'), bytes):
            data = receipt['kwargs']['stdin']
            receipt['kwargs']['stdin'] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        started = time.monotonic()
        try:
            result = getattr(self.client, method)(*args, **kwargs)
            receipt.update(completion='acknowledged', result=native_value(result))
            return result
        except Exception as error:
            receipt['error_type'] = type(error).__name__
            receipt['error'] = str(error)
            if isinstance(error, grpc.RpcError):
                receipt.update(grpc_code=error.code().name, grpc_details=error.details())
                status = getattr(error, 'raw_status', None)
                if status is not None:
                    receipt['native_status'] = MessageToDict(status, preserving_proto_field_name=True)
            raise
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - started
            (self.evidence / f'sdk-{self.counter:04d}.json').write_text(json.dumps(receipt, indent=2))



@pytest.mark.lifecycle
def test_native_lifecycle_execution_and_transfers(kube, gateway):
    sources = ['tests/qualification/test_lifecycle.py', 'pyproject.toml', 'uv.lock']
    (kube.evidence / 'lifecycle-source-hashes.json').write_text(json.dumps({p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}, indent=2))
    packages = ('openshell', 'grpcio', 'protobuf', 'googleapis-common-protos', 'httpx', 'cloudpickle')
    summary = {'outcome': 'failed', 'repetitions': [], 'packages': {p: importlib.metadata.version(p) for p in packages}, 'workspace': WORKSPACE, 'internal_rpc_retry_counts': 'unknown'}
    assert summary['packages']['openshell'] == LOCK['openshell']['version'].removeprefix('v')
    mtls = gateway['mtls']
    tls = TlsConfig(ca_path=mtls / 'ca.crt', cert_path=mtls / 'tls.crt', key_path=mtls / 'tls.key')
    with SandboxClient(gateway['endpoint'], tls=tls, timeout=60) as client:
        sdk = SdkReceipts(client, kube.evidence)
        try:
            assert sdk.call('health').version == summary['packages']['openshell']
            assert sdk.call('list_all', workspace=WORKSPACE) == []
            for repetition in range(3):
                record = {'index': repetition + 1, 'name': 'life-' + uuid.uuid4().hex[:12], 'outcome': 'failed', 'cleanup_confirmed': False, 'create_delivery': 'unknown'}
                summary['repetitions'].append(record)
                started = time.monotonic()
                name, sandbox, resources = record['name'], None, []
                try:
                    sandbox = sdk.call('create', workspace=WORKSPACE, name=name, spec=inert_spec())
                    record.update(create_delivery='acknowledged', sandbox_id=sandbox.id)
                    ready = sdk.call('wait_ready', name, workspace=WORKSPACE, timeout_seconds=120)
                    assert ready.id == sandbox.id and ready.phase == openshell_pb2.SANDBOX_PHASE_READY
                    actual = json.loads(gateway['cli']('sandbox', 'get', name, '-o', 'json').stdout)
                    assert actual['id'] == sandbox.id and actual['policy'].get('network_policies', {}) == {}
                    assert not json.loads(gateway['cli']('sandbox', 'provider', 'list', name, '-o', 'json').stdout)['providers']
                    record['policy'] = actual['policy']
                    pair = inspect_identity(kube, actual, record)
                    cr = kube.get('sandboxes', '-n', 'openshell')['items'][0]
                    resources = [('sandbox', cr['metadata']['name'], cr['metadata']['uid'])] + [('pod', p['metadata']['name'], p['metadata']['uid']) for p in pair.values()]
                    record['resources'] = resources
                    record['workspace_storage'] = workspace_storage(kube, pair, record['sandbox_uid'])
                    result = sdk.call('exec', name, ['/bin/sh', '-c', "printf 'native stdout\\n'; printf 'native stderr\\n' >&2; exit 23"], workspace=WORKSPACE, no_login_shell=True, timeout_seconds=20)
                    assert (result.exit_code, result.stdout, result.stderr) == (23, 'native stdout\n', 'native stderr\n')
                    record['nonzero_exit'] = asdict(result)
                    result = sdk.call('exec', name, ['/bin/sh', '-ec', 'test "$QUALIFICATION" = exact; test "$PWD" = /tmp; cat > /tmp/read-write.txt; cat /tmp/read-write.txt'], workspace=WORKSPACE, workdir='/tmp', env={'QUALIFICATION': 'exact'}, stdin=b'native read/write\n', no_login_shell=True, timeout_seconds=20)
                    assert (result.exit_code, result.stdout, result.stderr) == (0, 'native read/write\n', '')
                    payload = bytes(range(256)) * 4 + b'\x00native-transfer\xff\n'
                    source = kube.evidence / f'payload-{repetition + 1}.bin'
                    source.write_bytes(payload)
                    expected = hashlib.sha256(payload).hexdigest()
                    # Explicit ignored evidence fixture only; no repository upload.
                    cwd = sdk.call('exec', name, ['/bin/pwd'], workspace=WORKSPACE, no_login_shell=True, timeout_seconds=20)
                    assert cwd.exit_code == 0 and cwd.stderr == '' and cwd.stdout.startswith('/') and cwd.stdout.count('\n') == 1
                    record['native_workdir'] = cwd.stdout.rstrip('\n')
                    remote = record['native_workdir'] + '/' + source.name
                    gateway['cli']('sandbox', 'upload', '--no-git-ignore', name, str(source))
                    result = sdk.call('exec', name, ['/usr/bin/sha256sum', remote], workspace=WORKSPACE, no_login_shell=True, timeout_seconds=20)
                    assert (result.exit_code, result.stdout, result.stderr) == (0, expected + '  ' + remote + '\n', '')
                    destination = kube.evidence / f'download-{repetition + 1}.bin'
                    gateway['cli']('sandbox', 'download', name, source.name, str(destination))
                    assert destination.is_file() and destination.read_bytes() == payload
                    record.update(transfer_bytes=len(payload), transfer_sha256=expected, download_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), outcome='passed')
                finally:
                    try:
                        if sandbox is not None:
                            assert sdk.call('get', name, workspace=WORKSPACE).id == sandbox.id, 'Native identity replaced; refusing delete'
                            deletion = sdk.call('delete', name, workspace=WORKSPACE)
                            assert deletion.sandbox_id == sandbox.id and deletion.outcome in (DeletionOutcome.COMPLETED, DeletionOutcome.ACCEPTED)
                            sdk.call('wait_deleted', name, workspace=WORKSPACE, expected_sandbox_id=sandbox.id, timeout_seconds=90)
                            assert sdk.call('list_all', workspace=WORKSPACE) == [], 'Replacement/name or original still present'
                            for resource, resource_name, uid in resources:
                                wait_resource_absent(kube, resource, resource_name, uid)
                            record['native_deletion_confirmed'] = True
                            for resource, identity in record.get('workspace_storage', {}).items():
                                wait_resource_absent(kube, resource, identity['name'], identity['uid'], namespace=None if resource == 'pv' else 'openshell')
                            record['cleanup_confirmed'] = len(resources) == 3 and bool(record.get('workspace_storage'))
                    except Exception as error:
                        record['cleanup_error'] = {'type': type(error).__name__, 'detail': str(error)}
                        raise
                    finally:
                        record['elapsed_seconds'] = time.monotonic() - started
                        (kube.evidence / 'lifecycle.json').write_text(json.dumps(summary, indent=2))
            assert all(r['outcome'] == 'passed' and r['cleanup_confirmed'] for r in summary['repetitions']) and len(summary['repetitions']) == 3
            summary['outcome'] = 'passed'
        finally:
            summary['observed_sdk_calls'] = sdk.counter
            (kube.evidence / 'lifecycle.json').write_text(json.dumps(summary, indent=2))
