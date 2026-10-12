"""SPEC-0025/0026 ordered sandbox network phases as OpenShell policy documents (plain data, offline).

Each revision is loaded natively and confirmed by a denial event by the caller; nothing here loads,
observes or qualifies a policy.
"""
from collections.abc import Mapping, Sequence
import copy
from types import MappingProxyType

from corsair.nodes.dependency_inventory import GENERATED_PATHS
from corsair.nodes.source_fetch import FetchRecipe, FetchTarget, absolute

PHASES = ('source_fetch', 'dependency_setup', 'build_and_test')
# Operator-owned SPEC-0026 table; resolver binary paths come from the admitted image.
REGISTRY_ALLOWLIST = MappingProxyType({
    'python': ('pypi.org', 'files.pythonhosted.org'),
    'java': ('repo.maven.apache.org', 'repo1.maven.org'),
    'javascript': ('registry.npmjs.org',),
    'ruby': ('rubygems.org', 'index.rubygems.org'),
    'perl': ('cpan.metacpan.org', 'fastapi.metacpan.org'),
})


def _revision(base: Mapping, network: dict) -> dict:
    if not isinstance(base, Mapping) or 'network_policies' not in base or base['network_policies'] != {}:
        raise ValueError('Base policy with empty network_policies required')
    policy = copy.deepcopy(dict(base))
    policy['network_policies'] = network
    return policy


def _endpoint(host, rules):
    return {'host': host, 'port': 443, 'protocol': 'rest', 'enforcement': 'enforce',
            'rules': [{'allow': {'method': m, 'path': p}} for m, p in rules]}


def source_fetch_policy(base: Mapping, recipe: FetchRecipe, target: FetchTarget) -> dict:
    """One host, port 443, git smart-HTTP fetch only, for git's HTTPS transport helper."""
    if target.host not in recipe.allowed_hosts: raise ValueError('Repository host not operator-allowed')
    return _revision(base, {'corsair-source-fetch': {
        'name': 'corsair-source-fetch', 'binaries': [{'path': recipe.transport}],
        'endpoints': [_endpoint(target.host, (('GET', '/**'), ('POST', '/**/git-upload-pack')))]}})


def dependency_policy(base: Mapping, ecosystem: str, binaries: tuple[str, ...], *, private_source: bool) -> dict:
    if private_source is not False: raise ValueError('No registry egress for private source (SPEC-0026)')
    if ecosystem not in REGISTRY_ALLOWLIST: raise ValueError('Unknown ecosystem')
    if ecosystem not in GENERATED_PATHS: raise ValueError('Ecosystem inventory coverage not yet defined')
    if type(binaries) is not tuple or not binaries or len(set(binaries)) != len(binaries):
        raise ValueError('Distinct resolver binary paths required')
    for path in binaries: absolute(path)
    name = 'corsair-dependency-' + ecosystem
    return _revision(base, {name: {'name': name, 'binaries': [{'path': p} for p in binaries],
                                   'endpoints': [_endpoint(h, (('GET', '/**'),)) for h in REGISTRY_ALLOWLIST[ecosystem]]}})


def build_and_test_policy(base: Mapping) -> dict:
    return _revision(base, {})


def check_phase_order(revisions: Sequence[str]) -> None:
    """A prefix is an aborted run; a reorder, repeat or skip is refused."""
    if isinstance(revisions, str) or not 1 <= len(revisions) <= len(PHASES) or tuple(revisions) != PHASES[:len(revisions)]:
        raise ValueError('Policy revisions must follow ' + ' -> '.join(PHASES))
