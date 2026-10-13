"""SPEC-0070 pinned CLI policy adapter against a scripted stand-in binary: a revision counts only when observed
loaded on the original sandbox."""
import hashlib
import json
import sys
from uuid import uuid4

import pytest

from corsair.adapters.openshell_policy import CliPolicy
from corsair.ports.sandbox import PolicyError, SandboxHandle

HANDLE = SandboxHandle('sandbox-id', 'cs-0123', 'corsair', 'owner', 'creation')
STAND_IN = '''#!{python}
import json, sys
args = sys.argv[5:]
state = json.load(open({state!r}))
if args[:2] == ['policy', 'set']:
    sys.exit(state.get('set_exit', 0))
if args[:2] == ['sandbox', 'get']:
    print(json.dumps({{'id': state['id'], 'policy_source': 'sandbox',
                      'configuration_admission': {{'state': 'accepted', 'policy_hash': 'h1'}}}}))
elif '--rev' in args:
    print(json.dumps({{'status': state['status'], 'hash': 'h1'}}))
else:
    print(json.dumps({{'version': 3, 'hash': 'h1'}}))
'''


@pytest.fixture
def policy(tmp_path):
    def build(pin=None, **state):
        (tmp_path / 'state.json').write_text(json.dumps({'id': 'sandbox-id', 'status': 'loaded'} | state))
        binary = tmp_path / 'openshell'
        binary.write_text(STAND_IN.format(python=sys.executable, state=str(tmp_path / 'state.json')))
        binary.chmod(0o700)
        receipts = tmp_path / f'receipts-{uuid4().hex}'
        receipts.mkdir(mode=0o700)
        return CliPolicy(binary, pin or hashlib.sha256(binary.read_bytes()).hexdigest(), gateway='corsair', env={},
                         timeout_seconds=30, receipts=receipts)
    return build


def test_a_loaded_revision_on_the_original_sandbox_is_recorded(policy):
    receipt = policy().apply(HANDLE, {'network_policies': {}}, 'source_fetch', uuid4())
    assert (receipt.loaded, receipt.delivery, receipt.native_version, receipt.native_hash) == (True, 'acknowledged', 3, 'h1')


@pytest.mark.parametrize('state, delivery', [
    ({'set_exit': 2}, 'unknown'),            # set failed: whether the gateway stored it is unknown
    ({'status': 'pending'}, 'acknowledged'),  # stored but not loaded never counts
    ({'id': 'replacement'}, 'acknowledged'),  # another sandbox under the same name
])
def test_anything_but_an_observed_load_fails(policy, state, delivery):
    with pytest.raises(PolicyError) as failed:
        policy(**state).apply(HANDLE, {'network_policies': {}}, 'source_fetch', uuid4())
    assert (failed.value.receipt.loaded, failed.value.receipt.delivery) == (False, delivery)


def test_a_binary_that_differs_from_its_pin_is_never_run(policy):
    with pytest.raises(PolicyError) as failed:
        policy(pin='0' * 64).apply(HANDLE, {'network_policies': {}}, 'source_fetch', uuid4())
    assert failed.value.receipt.delivery == 'not_dispatched'
