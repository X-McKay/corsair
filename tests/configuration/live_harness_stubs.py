"""pytest plugin for the offline smoke run of every live gate (loaded with -p and --noconftest; never in a live run).

The owned-cluster client, the network fixture and the native gateway are stubs that stop a test at its first native
call or first gateway use, raising `NativeReached` or `GatewayReached`. The gate checks of earlier evidence
(`require_network`, `require_admission`) pass without reading anything. What runs before that stop is the harness's own
Python: option reading, evidence directories, fixture wiring and gateway scope. Prepared image receipts are stubs too. Results go to the file CORSAIR_SMOKE_RESULTS names.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

import pytest

STATE = {}


class NativeReached(Exception):
    """The harness reached its first native command; nothing after it runs offline."""


class GatewayReached(Exception):
    """The harness reached its first use of an installed gateway."""


class StubKube:
    def __init__(self, evidence):
        self.evidence, self.argv, self.counter = evidence, ['kubectl-stub'], 0

    def run(self, *args, **kwargs):
        raise NativeReached('kubectl ' + ' '.join(map(str, args)))

    def native(self, argv, *args, **kwargs):
        raise NativeReached(' '.join(map(str, argv)))

    def get(self, *args, **kwargs):
        raise NativeReached('kubectl get ' + ' '.join(map(str, args)))


class StubGateway(dict):
    def __init__(self, install):
        super().__init__()
        self.install = install

    def __getitem__(self, key):
        assert self.install['active'], 'Gateway used after its teardown uninstalled it'
        raise GatewayReached(key)

    get = __getitem__


@contextmanager
def stub_native_gateway(kube):
    install = {'test': STATE['current'], 'active': True}
    STATE['installs'].append(install)
    try:
        yield StubGateway(install)
    finally:
        install['active'] = False


def passes(*args, **kwargs):
    return None


class StubReceipt(dict):
    """A prepared image's receipt; on RIG0 it comes from the preparation cache."""

    def __missing__(self, key):
        return 'stub-' + key


def stub_image_receipt(*args, **kwargs):
    return StubReceipt()


def pytest_sessionstart(session):
    STATE.clear()
    STATE.update(current=None, installs=[], outcomes={}, markers={})


@pytest.fixture(scope='session')
def kube(tmp_path_factory):
    evidence = tmp_path_factory.mktemp('evidence')
    evidence.chmod(0o700)
    return StubKube(evidence)


@pytest.fixture
def network(kube):
    raise NativeReached('network fixture setup')


def pytest_collection_modifyitems(items):
    # Replace the native gateway and the evidence checks wherever a live module imported them by name.
    for name, module in list(sys.modules.items()):
        if name.startswith('tests.qualification.') and module is not None:
            for attribute, stub in (('native_gateway', stub_native_gateway), ('require_network', passes), ('require_admission', passes),
                                    ('image_receipt', stub_image_receipt)):
                if hasattr(module, attribute):
                    setattr(module, attribute, stub)
    for item in items:
        STATE['markers'][item.nodeid] = sorted({m.name for m in item.iter_markers()} - {'parametrize', 'usefixtures'})


def pytest_runtest_setup(item):
    STATE['current'] = item.nodeid


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if call.excinfo is None:
        outcome = 'passed' if report.passed else report.outcome
    elif call.excinfo.errisinstance((NativeReached, GatewayReached)):
        outcome = 'stopped:' + call.excinfo.type.__name__
    else:
        outcome = f'{call.when}:{call.excinfo.type.__name__}: {call.excinfo.value}'[:600]
    previous = STATE['outcomes'].get(item.nodeid)
    if previous is None or previous in ('passed', 'skipped') or previous.startswith('stopped:'):
        if not (call.when == 'teardown' and call.excinfo is None):
            STATE['outcomes'][item.nodeid] = outcome


def pytest_sessionfinish(session):
    Path(os.environ['CORSAIR_SMOKE_RESULTS']).write_text(json.dumps({'installs': [i['test'] for i in STATE['installs']], 'outcomes': STATE['outcomes'],
                                   'markers': STATE['markers']}, indent=2))
