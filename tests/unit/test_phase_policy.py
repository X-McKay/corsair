"""SPEC-0025/0026 phase policy documents; offline shape only, never a loaded revision."""
import copy
from pathlib import Path

import pytest
import yaml

from corsair.nodes.phase_policy import (PHASES, REGISTRY_ALLOWLIST, build_and_test_policy, check_phase_order,
                                        dependency_policy, source_fetch_policy)
from corsair.nodes.source_fetch import FetchRecipe, FetchTarget

BASE = yaml.safe_load((Path(__file__).parents[2]/'policies/openshell/identity.yaml').read_text())
RECIPE = FetchRecipe('/bin/sh', '/usr/bin/git', '/usr/lib/git-core/git-remote-https', '/sandbox/src', 4096,
                     frozenset({'github.com', 'dev.azure.com'}))
TARGET = FetchTarget('https://dev.azure.com/org/project/_git/repo', 'a'*40)


def grants(policy):
    return [(b['path'], e['host'], e['port'], e['protocol'], e['enforcement'], tuple((r['allow']['method'], r['allow']['path']) for r in e['rules']))
            for p in policy['network_policies'].values() for b in p['binaries'] for e in p['endpoints']]


def unchanged_outside_network(policy):
    return {k: v for k, v in policy.items() if k != 'network_policies'} == {k: v for k, v in BASE.items() if k != 'network_policies'}


def test_source_fetch_grants_one_host_and_port_for_git_transport_only():
    before = copy.deepcopy(BASE)
    policy = source_fetch_policy(BASE, RECIPE, TARGET)
    assert grants(policy) == [('/usr/lib/git-core/git-remote-https', 'dev.azure.com', 443, 'rest', 'enforce',
                               (('GET', '/**'), ('POST', '/**/git-upload-pack')))]
    assert unchanged_outside_network(policy) and BASE == before
    with pytest.raises(ValueError):
        source_fetch_policy(BASE, RECIPE, FetchTarget('https://gitlab.com/a/b', 'a'*40))


def test_narrowed_build_revision_grants_nothing_and_base_must_be_closed():
    assert build_and_test_policy(BASE)['network_policies'] == {} and unchanged_outside_network(build_and_test_policy(BASE))
    opened = source_fetch_policy(BASE, RECIPE, TARGET)
    for base in (opened, {k: v for k, v in BASE.items() if k != 'network_policies'}):
        with pytest.raises(ValueError, match='empty network_policies'): build_and_test_policy(base)
        with pytest.raises(ValueError): source_fetch_policy(base, RECIPE, TARGET)


@pytest.mark.parametrize('ecosystem', ['python', 'java', 'javascript'])
def test_dependency_phase_grants_only_listed_registries_get_only(ecosystem):
    binaries = ('/usr/bin/resolver', '/usr/bin/python3')
    policy = dependency_policy(BASE, ecosystem, binaries, private_source=False)
    expected = [(b, h, 443, 'rest', 'enforce', (('GET', '/**'),)) for b in binaries for h in REGISTRY_ALLOWLIST[ecosystem]]
    assert grants(policy) == expected and unchanged_outside_network(policy)


@pytest.mark.parametrize('ecosystem,binaries,private,reason', [
    ('python', ('/usr/bin/pip',), True, 'private source'), ('ruby', ('/usr/bin/gem',), False, 'coverage'),
    ('perl', ('/usr/bin/cpanm',), False, 'coverage'), ('go', ('/usr/bin/go',), False, 'Unknown'),
    ('python', ('pip',), False, 'absolute'), ('python', (), False, 'Distinct'), ('python', ['/usr/bin/pip'], False, 'Distinct'),
    ('python', ('/usr/bin/pip', '/usr/bin/pip'), False, 'Distinct'), ('python', ('/usr/bin/pip',), None, 'private source')])
def test_dependency_phase_refusals(ecosystem, binaries, private, reason):
    with pytest.raises(ValueError, match=reason): dependency_policy(BASE, ecosystem, binaries, private_source=private)


@pytest.mark.parametrize('revisions', [PHASES[:1], PHASES[:2], PHASES, list(PHASES)])
def test_phase_order_admits_full_run_and_aborted_prefix(revisions):
    check_phase_order(revisions)


@pytest.mark.parametrize('revisions', [(), PHASES[1:], PHASES[::-1], PHASES+PHASES[-1:], ('source_fetch', 'source_fetch'),
                                       ('source_fetch', 'build_and_test'), 'source_fetch'])
def test_phase_order_refuses_reorder_repeat_or_skip(revisions):
    with pytest.raises(ValueError): check_phase_order(revisions)
