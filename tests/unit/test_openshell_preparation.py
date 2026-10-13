"""SPEC-0070 OpenShell preparation for the environment stage, against host doubles for the source workspace and
policy ports: step order, refusals that discard, release and sweep confirmed only on observed deletes."""
from dataclasses import replace
import hashlib
from uuid import uuid4, uuid5

import pytest

from corsair.adapters.openshell_preparation import OpenShellPreparation
from corsair.adapters.openshell_workspace import WorkspaceError
from corsair.agents.environment.contracts import Toolchain
from corsair.composition.direct import PreparationRefused
from corsair.nodes.source_fetch import WorkspaceBudget
from corsair.ports.sandbox import PolicyError, PolicyReceipt, SandboxHandle
from tests.unit.test_source_fetch import FILES, snapshot

IMAGE = 'docker.io/library/corsair-python@sha256:' + 'a' * 64
TOOLCHAIN = Toolchain(toolchain_id='cpython-3.12-pytest', image=IMAGE, language='python', runtime='CPython 3.12',
                      tools=('pytest 9.0.3',))
BASE = {'version': 1, 'network_policies': {}}
BUDGET = WorkspaceBudget(workspace_bytes=1 << 30, reserve_bytes=1 << 30, node_path='/var/lib')
HANDLE = SandboxHandle(id='sandbox-id', name='cs-0123', workspace='corsair', owner='owner', creation_operation='op')


class Workspaces:
    """Host double for `OpenShellTestWorkspace`: one record per native step; `fail` maps a step to its error."""
    def __init__(self, log, fail=None):
        self.log, self.fail, self.images = log, dict(fail or {}), []

    def __call__(self, image):
        self.images.append(image)
        return self

    def prepare_source(self, operation):
        self.log.append(('place', operation))
        if 'place' in self.fail:
            raise self.fail['place']
        return HANDLE

    def release_source(self, handle, operation):
        self.log.append(('release', handle.id, operation))
        if 'release' in self.fail:
            raise self.fail['release']
        return 'confirmed'


class Policies:
    def __init__(self, log, fail=False):
        self.log, self.fail, self.applied = log, fail, []

    def apply(self, handle, policy, phase, operation):
        self.log.append(('policy', phase, operation))
        self.applied.append(policy)
        receipt = PolicyReceipt(str(operation), handle, phase, 'sha', 'acknowledged', not self.fail, 0.1)
        if self.fail:
            raise PolicyError(replace(receipt, error_detail='not loaded'))
        return receipt


class Store:
    """The operator's artifact store over the fixture capture, by digest."""
    def __init__(self):
        self.objects = {hashlib.sha256(data).hexdigest(): data for _, _, data in FILES}

    def get(self, reference):
        return self.objects[reference.sha256]


@pytest.fixture
def make(tmp_path):
    def build(*, fail=None, policy_fail=False, private=False, free=1 << 40, resolvers=None):
        log = []
        receipts = tmp_path / f'receipts-{uuid4().hex}'
        receipts.mkdir(mode=0o700)
        workspaces, policies = Workspaces(log, fail), Policies(log, policy_fail)
        adapter = OpenShellPreparation(
            workspaces, object(), policies, store=Store(), snapshot=snapshot(), private_source=private, base_policy=BASE,
            resolvers={'python': ('/usr/local/bin/python3.12',)} if resolvers is None else resolvers,
            budget=BUDGET, scratch_location='/sandbox/scratch', receipts=receipts, free_bytes=lambda budget: free)
        return adapter, log, workspaces, policies
    return build


def test_prepare_places_the_source_then_loads_the_setup_policy_on_the_toolchain_image(make):
    adapter, log, workspaces, policies = make()
    operation = uuid4()
    prepared = adapter.prepare(TOOLCHAIN, operation)
    assert workspaces.images == [IMAGE] and (prepared.handle, prepared.scratch_location) == (HANDLE, '/sandbox/scratch')
    assert log == [('place', uuid5(operation, 'source')),
                   ('policy', 'dependency_setup', uuid5(operation, 'dependency-policy'))]
    assert list(policies.applied[0]['network_policies']) == ['corsair-dependency-python']
    assert adapter.release(prepared, operation) == 'confirmed'
    assert log[-1] == ('release', 'sandbox-id', operation)
    assert adapter.sweep() == {}


@pytest.mark.parametrize('error, layer, cleanup', [
    (WorkspaceError('admission', 'remote workspace differs', 'confirmed'), 'admission', 'confirmed'),
    (WorkspaceError('staging', 'disk full', 'not_required'), 'staging', 'not_required'),
    (WorkspaceError('upload', 'timed out', 'unconfirmed'), 'upload', 'unconfirmed'),
    (RuntimeError('gateway closed'), 'sandbox', 'unconfirmed'),
])
def test_a_refused_placement_keeps_the_workspaces_layer_and_cleanup(make, error, layer, cleanup):
    adapter, log, _, _ = make(fail={'place': error})
    operation = uuid4()
    with pytest.raises(PreparationRefused) as refused:
        adapter.prepare(TOOLCHAIN, operation)
    assert (refused.value.layer, refused.value.cleanup) == (layer, cleanup)
    # Without a handle the sweep deletes nothing: it reports what may remain, by the journaled intent.
    expected = {str(operation): 'unconfirmed'} if cleanup == 'unconfirmed' else {}
    assert adapter.sweep() == expected and [step[0] for step in log] == ['place']


def test_a_setup_policy_that_does_not_load_discards_the_sandbox(make):
    adapter, log, _, _ = make(policy_fail=True)
    operation = uuid4()
    with pytest.raises(PreparationRefused) as refused:
        adapter.prepare(TOOLCHAIN, operation)
    assert (refused.value.layer, refused.value.cleanup) == ('policy', 'confirmed')
    assert log[-1] == ('release', 'sandbox-id', uuid5(operation, 'discard'))


def test_a_sandbox_discarded_after_a_policy_failure_is_not_deleted_again(make):
    """Review of dfd4a29: the discard is journaled as released, so the sweep leaves it alone."""
    adapter, log, _, _ = make(policy_fail=True)
    with pytest.raises(PreparationRefused):
        adapter.prepare(TOOLCHAIN, uuid4())
    assert adapter.sweep() == {} and [step[0] for step in log].count('release') == 1


def test_the_intent_is_journaled_before_any_sandbox_is_created(make, tmp_path):
    """Review of dfd4a29: a worker lost between create and the handle's journal entry still leaves a trace."""
    adapter, log, workspaces, _ = make()
    operation, seen = uuid4(), []

    def lost(source_operation):
        seen.extend(p.name for p in adapter._receipts.iterdir())
        raise SystemExit('worker lost')
    workspaces.prepare_source = lost
    with pytest.raises(SystemExit):
        adapter.prepare(TOOLCHAIN, operation)
    assert seen == [f'{operation}.intent.json']
    assert adapter.sweep() == {str(operation): 'unconfirmed'} and log == []


def test_an_unconfirmed_discard_is_left_for_sweep(make):
    adapter, log, workspaces, _ = make(policy_fail=True, fail={'release': RuntimeError('gateway closed')})
    operation = uuid4()
    with pytest.raises(PreparationRefused) as refused:
        adapter.prepare(TOOLCHAIN, operation)
    assert refused.value.cleanup == 'unconfirmed'
    assert adapter.sweep() == {str(operation): 'unconfirmed'}
    workspaces.fail.clear()
    # Each pass deletes under a fresh operation, so a later pass can confirm what an earlier one could not.
    assert adapter.sweep() == {str(operation): 'confirmed'}
    deletes = [step[2] for step in log if step[0] == 'release']
    assert len(deletes) == len(set(deletes)) == 3
    assert adapter.sweep() == {}


@pytest.mark.parametrize('options, layer', [
    (dict(private=True), 'policy'),       # SPEC-0026: no registry egress for private source
    (dict(resolvers={}), 'policy'),
    (dict(free=1 << 20), 'host'),
])
def test_refusals_before_any_sandbox_need_no_cleanup(make, options, layer):
    adapter, log, workspaces, _ = make(**options)
    with pytest.raises(PreparationRefused) as refused:
        adapter.prepare(TOOLCHAIN, uuid4())
    assert (refused.value.layer, refused.value.cleanup) == (layer, 'not_required')
    assert log == [] and workspaces.images == []


def test_a_worker_lost_after_placement_leaves_a_sandbox_sweep_removes(make):
    adapter, log, _, _ = make()
    operation = uuid4()
    adapter.prepare(TOOLCHAIN, operation)  # Never released: the worker is gone.
    assert adapter.sweep() == {str(operation): 'confirmed'}
    assert log[-1][:2] == ('release', 'sandbox-id')
    assert adapter.sweep() == {}


def test_releasing_an_unknown_sandbox_is_unconfirmed(make):
    adapter, _, _, _ = make()
    other, _, _, _ = make()
    prepared = other.prepare(TOOLCHAIN, uuid4())
    assert adapter.release(prepared, uuid4()) == 'unconfirmed'


def test_the_baseline_file_is_read_from_the_capture_not_the_sandbox(make):
    adapter, log, _, _ = make()
    sandbox = adapter.prepare(TOOLCHAIN, uuid4())
    entries = len(log)
    assert sandbox.read_source('src/a/b.txt') == b'b\r\n' and sandbox.read_source('missing.py') is None
    assert len(log) == entries  # No sandbox step ran to answer it.
