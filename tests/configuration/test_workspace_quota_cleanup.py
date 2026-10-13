"""The live quota gate's cleanup never records a failed or uncertain namespace query as a confirmed deletion."""
import json
from types import SimpleNamespace

import pytest

from tests.qualification.test_workspace_quota import delete_owned_namespace

NS, UID = 'corsair-quota-0000abcd', 'uid-1'
PRESENT = SimpleNamespace(returncode=0, stdout=json.dumps({'metadata': {'uid': UID}}))
ABSENT = SimpleNamespace(returncode=0, stdout='')
FAILED = SimpleNamespace(returncode=1, stdout='', stderr='API connection refused')


class Kube:
    def __init__(self, *gets):
        self.gets, self.deleted = list(gets), False

    def run(self, verb, *args, check=True, timeout=120):
        if verb == 'delete':
            self.deleted = True
            return SimpleNamespace(returncode=0, stdout='')
        result = self.gets.pop(0)
        if isinstance(result, Exception): raise result
        return result


def test_confirmed_only_when_both_queries_succeed_and_the_namespace_is_gone():
    kube = Kube(PRESENT, ABSENT)
    assert delete_owned_namespace(kube, NS, UID) == {'namespace_deleted': True} and kube.deleted


@pytest.mark.parametrize('gets', [(FAILED,), (PRESENT, FAILED), (ABSENT, FAILED), (TimeoutError('timed out'),),
                                  (PRESENT, TimeoutError('timed out'))])
def test_failed_or_uncertain_queries_are_unknown_not_deleted(gets):
    cleanup = delete_owned_namespace(Kube(*gets), NS, UID)
    assert cleanup['namespace_deleted'] is False and 'unknown' in cleanup
    if FAILED in gets: assert cleanup['query_stderr'] == 'API connection refused'


def test_replacement_and_unowned_namespaces_are_never_deleted():
    replaced = Kube(SimpleNamespace(returncode=0, stdout=json.dumps({'metadata': {'uid': 'other'}})))
    assert 'refused' in delete_owned_namespace(replaced, NS, UID) and not replaced.deleted
    unowned = Kube()
    assert 'refused' in delete_owned_namespace(unowned, NS, None) and not unowned.deleted
