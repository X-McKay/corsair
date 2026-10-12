"""Offline SDK/artifact/receipt guards; these are not live qualification."""
import inspect
import json
import tomllib
from types import SimpleNamespace

from openshell import SandboxClient, TlsConfig
from openshell._proto import openshell_pb2
import pytest

from tests.qualification.support import ROOT, LOCK
from tests.qualification.test_lifecycle import inert_spec, SdkReceipts


def test_sdk_pin_matches_native_lock_and_spec_is_inert():
    locked = tomllib.loads((ROOT / 'uv.lock').read_text())
    sdk = next(p for p in locked['package'] if p['name'] == 'openshell')
    assert sdk['version'] == LOCK['openshell']['version'].removeprefix('v')
    assert sdk['source']['url'] == LOCK['openshell']['sdk']['url']
    assert sdk['wheels'][0]['hash'] == 'sha256:' + LOCK['openshell']['sdk']['sha256']
    spec = inert_spec()
    assert spec.template.image == LOCK['openshell']['images']['workload']
    assert spec.policy.landlock.compatibility == 'hard_requirement'
    assert not spec.providers and not spec.environment and not spec.policy.network_policies
    assert spec.policy.filesystem.include_workdir and not spec.tty
    assert list(spec.command) == ['/bin/sleep', '600']
    assert spec.restart_policy == openshell_pb2.SANDBOX_RESTART_POLICY_NEVER
    assert 'expected_sandbox_id' in inspect.signature(SandboxClient.wait_deleted).parameters
    with pytest.raises(ValueError, match='set together'):
        TlsConfig(cert_path=ROOT / 'missing')


def test_sdk_failure_receipt_retains_unknown_delivery_without_retry(tmp_path):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('fixture completion unknown')
    receipts = SdkReceipts(SimpleNamespace(create=fail), tmp_path)
    with pytest.raises(TimeoutError):
        receipts.call('create', workspace='default', name='fixture', spec=inert_spec())
    receipt = json.loads((tmp_path / 'sdk-0001.json').read_text())
    assert receipt['completion'] == 'unknown' and 'result' not in receipt and calls == [1]
    assert receipt['error_type'] == 'TimeoutError'
    assert not any(k in receipt for k in ('env', 'tls', 'key', 'certificate'))
