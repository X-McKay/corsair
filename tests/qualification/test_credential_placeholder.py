"""Live OpenShell 0.1.3 provider credential placeholder check for SPEC-0025 private-repository fetch.

Registers one provider holding a random, obviously fake credential through the native gRPC API,
attaches it at sandbox creation, and records what the workload sees. The workload scan receives only
a public prefix and a digest, never the credential. Egress substitution is not checked here: the
pinned proto exposes `NetworkEndpoint.credential_binding`, but its substitution semantics are not
documented in the pinned SDK, so that step stays unqualified.
"""
import hashlib
import importlib.metadata
import json
import secrets
import time
import uuid

from google.protobuf.json_format import MessageToDict
import grpc
from openshell import DeletionOutcome, SandboxClient, TlsConfig
from openshell._proto import datamodel_pb2, openshell_pb2
import pytest

from tests.qualification.credential_scan import SCAN
from tests.qualification.gateway import inspect_identity, wait_resource_absent, workspace_storage
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import LOCK, ROOT
from tests.qualification.test_adapter_lifecycle import adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import PYTHON, recovery_spec
from tests.qualification.test_test_workspace import sandboxes_absent

WORKSPACE = 'default'
KEY = 'CORSAIR_QUAL_FAKE_TOKEN'
PREFIX = 'corsair-fake-credential-'
ROOTS = ('/sandbox', '/tmp', '/.openshell')
SOURCES = ['tests/qualification/test_credential_placeholder.py', 'tests/qualification/credential_scan.py',
           'tests/qualification/gateway.py', 'tests/qualification/support.py', 'tests/qualification/test_recovery.py',
           'docs/development/specs/SPEC-0025-sandbox-source-fetch.md', 'policies/openshell/identity.yaml',
           'deploy/runtime-lock.yaml', 'pyproject.toml', 'uv.lock']


class Rpc:
    """Receipts for native provider RPCs; the fake credential is replaced by its digest before writing."""
    def __init__(self, client, evidence, dummy):
        self.stub, self.evidence, self.dummy, self.counter = client._stub, evidence, dummy, 0
        self.marker = '[fake-credential sha256:' + hashlib.sha256(dummy.encode()).hexdigest() + ']'

    def __call__(self, method, request, timeout=60):
        self.counter += 1
        receipt = {'method': method, 'request': MessageToDict(request, preserving_proto_field_name=True), 'completion': 'unknown'}
        started = time.monotonic()
        try:
            response = getattr(self.stub, method)(request, timeout=timeout)
            receipt.update(completion='acknowledged', response=MessageToDict(response, preserving_proto_field_name=True))
            receipt['response_contains_fake_credential'] = self.dummy in json.dumps(receipt['response'])
            return response
        except grpc.RpcError as error:
            receipt.update(error_type=type(error).__name__, grpc_code=error.code().name, grpc_details=error.details())
            raise
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - started
            text = json.dumps(receipt, indent=2).replace(self.dummy, self.marker)
            (self.evidence / f'provider-rpc-{self.counter:04d}.json').write_text(text)


def provider_names(rpc):
    names, token = [], ''
    while True:
        page = rpc('ListProviders', openshell_pb2.ListProvidersRequest(
            workspace_scope=datamodel_pb2.WorkspaceSelector(workspace=WORKSPACE), page_size=100, page_token=token))
        names += [p.metadata.name for p in page.providers]
        if not (token := page.next_page_token):
            return names


@pytest.mark.credential_placeholder
def test_provider_credential_reaches_workload_only_as_placeholder(kube, adapter_gateway):
    native = adapter_gateway
    kube.evidence.chmod(0o700)
    (kube.evidence / 'credential-placeholder-hashes.json').write_text(json.dumps(
        {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
    dummy = PREFIX + secrets.token_hex(16)
    digest = hashlib.sha256(dummy.encode()).hexdigest()
    suffix = uuid.uuid4().hex[:10]
    provider, name = 'qual-fake-' + suffix, 'cred-' + suffix
    summary = {'outcome': 'failed', 'scope': 'SPEC-0025 provider placeholder delivery; egress substitution unrun',
               'credential': {'key': KEY, 'sha256': digest, 'length': len(dummy), 'prefix': PREFIX, 'kind': 'random fake'},
               'provider': {'name': provider, 'create_delivery': 'unrun', 'cleanup': 'unrun'},
               'sandbox': {'name': name, 'create_delivery': 'unrun', 'cleanup': 'unrun'},
               'egress_substitution': 'unrun', 'internal_rpc_retry_counts': 'unknown',
               'packages': {'openshell': importlib.metadata.version('openshell')}}
    assert summary['packages']['openshell'] == LOCK['openshell']['version'].removeprefix('v')
    mtls = native['mtls']
    tls = TlsConfig(ca_path=mtls / 'ca.crt', cert_path=mtls / 'tls.crt', key_path=mtls / 'tls.key')
    scope = datamodel_pb2.WorkspaceSelector(workspace=WORKSPACE)
    errors = []
    with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client:
        sdk, rpc = SdkReceipts(client, kube.evidence), Rpc(client, kube.evidence, dummy)
        sandbox, provider_id, resources, record = None, None, [], summary['sandbox']
        try:
            image = summary['image'] = image_receipt('python')
            assert sdk.call('list_all', workspace=WORKSPACE) == [] and provider not in provider_names(rpc)
            summary['provider']['create_delivery'] = 'unknown'
            created = rpc('CreateProvider', openshell_pb2.CreateProviderRequest(
                workspace_scope=scope, request_id=str(uuid.uuid4()), provider=datamodel_pb2.Provider(
                    metadata=datamodel_pb2.ObjectMeta(name=provider), type='generic', credentials={KEY: dummy})))
            provider_id = created.provider.metadata.id
            summary['provider'].update(create_delivery='acknowledged', id=provider_id)
            fetched = rpc('GetProvider', openshell_pb2.GetProviderRequest(workspace_scope=scope, name=provider)).provider
            assert fetched.metadata.id == provider_id and provider in provider_names(rpc)
            summary['provider']['get_returns_fake_credential'] = dummy in str(fetched)
            spec = recovery_spec(image['image'], '512Mi')
            spec.providers.append(provider)
            record['create_delivery'] = 'unknown'
            sandbox = sdk.call('create', workspace=WORKSPACE, name=name, spec=spec)
            record.update(create_delivery='acknowledged', id=sandbox.id)
            assert sdk.call('wait_ready', name, workspace=WORKSPACE).id == sandbox.id
            actual = json.loads(native['cli']('sandbox', 'get', name, '-o', 'json').stdout)
            assert actual['id'] == sandbox.id
            pair = inspect_identity(kube, actual, record, expected_image=image['image'])
            cr = kube.get('sandboxes', '-n', 'openshell')['items'][0]
            resources = [('sandbox', cr['metadata']['name'], cr['metadata']['uid'])] + [
                ('pod', p['metadata']['name'], p['metadata']['uid']) for p in pair.values()]
            record.update(resources=resources, workspace_storage=workspace_storage(kube, pair, cr['metadata']['uid']))
            attached = rpc('ListSandboxProviders', openshell_pb2.ListSandboxProvidersRequest(workspace_scope=scope, sandbox=name))
            assert [p.metadata.name for p in attached.providers] == [provider], 'Provider not attached at creation'
            result = sdk.call('exec', name, [PYTHON, '-I', '-c', SCAN, PREFIX, str(len(dummy)), digest, KEY, *ROOTS],
                              workspace=WORKSPACE, workdir='/tmp', no_login_shell=True, timeout_seconds=120)
            echoed = dummy in result.stdout + result.stderr
            assert result.exit_code == 0 and not echoed, 'Workload scan failed or echoed the credential; see SDK receipt'
            seen = summary['workload'] = json.loads(result.stdout)
            env = seen['env']
            summary['placeholder_form'] = env.get('value') if env['present'] and not env['is_dummy'] else None
            assert env['present'], 'Provider credential not delivered to the exec environment; placeholder form unknown'
            assert not env['is_dummy'], 'Workload environment holds the raw credential'
            assert not any(p.get('matches') or p.get('env', {}).get('is_dummy') for p in seen['processes'].values()), \
                'Raw credential found in a process environment'
            assert not any(r['matches'] for r in seen['roots'].values()), 'Raw credential found in a workload file'
            summary['unknown_scopes'] = {
                'processes': sorted(p for p, v in seen['processes'].items() if v['state'] == 'unknown'),
                'roots': {r: v['state'] for r, v in seen['roots'].items() if v['state'] != 'scanned'}}
            summary['outcome'] = 'passed'
        except BaseException as error:
            summary.update(outcome='failed', error_type=type(error).__name__, error_detail=str(error).replace(dummy, rpc.marker))
            raise
        finally:
            try:
                if sandbox is None and record['create_delivery'] == 'unknown':
                    record['cleanup'] = 'unconfirmed: create delivery unknown; inspect gateway and cluster'
                if sandbox is not None:
                    record['cleanup'] = 'unconfirmed'
                    assert sdk.call('get', name, workspace=WORKSPACE).id == sandbox.id, 'Replacement: refusing delete'
                    deletion = sdk.call('delete', name, workspace=WORKSPACE)
                    assert deletion.sandbox_id == sandbox.id and deletion.outcome in (DeletionOutcome.COMPLETED, DeletionOutcome.ACCEPTED)
                    sdk.call('wait_deleted', name, workspace=WORKSPACE, expected_sandbox_id=sandbox.id, timeout_seconds=90)
                    assert sdk.call('list_all', workspace=WORKSPACE) == []
                    for resource, resource_name, uid in resources:
                        wait_resource_absent(kube, resource, resource_name, uid)
                    for resource, identity in record.get('workspace_storage', {}).items():
                        wait_resource_absent(kube, resource, identity['name'], identity['uid'], namespace=None if resource == 'pv' else 'openshell')
                    sandboxes_absent(kube, [name], record)
                    record['cleanup'] = 'confirmed' if len(resources) == 3 and record.get('workspace_storage') else 'unconfirmed'
            except Exception as error:
                errors.append(error)
                record['cleanup_error'] = {'type': type(error).__name__, 'detail': str(error)}
            try:
                if summary['provider']['create_delivery'] != 'unrun':
                    # Delivery may be unknown: the name is unique to this run, so a provider by that name is ours.
                    summary['provider']['cleanup'] = 'unconfirmed'
                    if provider in provider_names(rpc):
                        current = rpc('GetProvider', openshell_pb2.GetProviderRequest(workspace_scope=scope, name=provider)).provider
                        assert provider_id in (None, current.metadata.id), 'Provider identity replaced; refusing delete'
                        deleted = rpc('DeleteProvider', openshell_pb2.DeleteProviderRequest(
                            workspace_scope=scope, name=provider, request_id=str(uuid.uuid4())))
                        summary['provider']['deletion_outcome'] = openshell_pb2.DeletionOutcome.Name(deleted.outcome)
                    assert provider not in provider_names(rpc), 'Provider still listed after deletion'
                    summary['provider']['cleanup'] = 'confirmed (native list; gateway storage not inspected)'
            except Exception as error:
                errors.append(error)
                summary['provider']['cleanup_error'] = {'type': type(error).__name__, 'detail': str(error)}
            summary['observed_calls'] = {'sdk': sdk.counter, 'provider_rpc': rpc.counter}
            body_passed = summary['outcome'] == 'passed'
            leaked = summary['evidence_contains_fake_credential'] = sorted(
                str(p) for p in kube.evidence.rglob('*') if p.is_file() and dummy.encode() in p.read_bytes())
            if errors or leaked:
                summary['outcome'] = 'failed'
            (kube.evidence / 'credential-placeholder.json').write_text(
                json.dumps(summary, indent=2, default=str).replace(dummy, rpc.marker))
            if body_passed:
                assert not leaked, f'Fake credential written to evidence: {leaked}'
                if errors:
                    raise errors[0]
