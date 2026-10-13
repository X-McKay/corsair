"""SPEC-0037 offline contract: exact-commit acquisition, verification, measurement and failure layers.

The network fetch is replaced by a pinned wrapper that serves a local origin for one fixture URL, so everything
after transport (pinning, shallowness, digest, fsck, tree stats, receipts, GitSource admission) runs on real Git.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from corsair.adapters.git_acquire import (AcquireLimits, AcquisitionError, GitAcquisition, HostTransport, tree_stats)
from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.nodes.source_fetch import CredentialBinding, FetchTarget

GIT, PRLIMIT = '/usr/bin/git', '/usr/bin/prlimit'
URL = 'https://github.com/fixture/repo'
pytestmark = pytest.mark.skipif(not os.path.exists(PRLIMIT), reason='prlimit not installed')


def pin(path):
    with open(path, 'rb') as stream: return Executable(Path(path), hashlib.file_digest(stream, 'sha256').hexdigest())


def git(*args, cwd):
    return subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                               'GIT_AUTHOR_NAME': 'a', 'GIT_AUTHOR_EMAIL': 'a@b', 'GIT_COMMITTER_NAME': 'a',
                               'GIT_COMMITTER_EMAIL': 'a@b'}).stdout.strip()


@pytest.fixture
def origin(tmp_path):
    work = tmp_path/'origin'; work.mkdir()
    git('init', '-q', cwd=work)
    (work/'a.txt').write_text('one\n'); git('add', '.', cwd=work); git('commit', '-qm', 'base', cwd=work)
    base = git('rev-parse', 'HEAD', cwd=work)
    (work/'run.sh').write_text('#!/bin/sh\n'); (work/'run.sh').chmod(0o755)
    (work/'link').symlink_to('a.txt')
    git('add', '.', cwd=work)
    git('update-index', '--add', '--cacheinfo', f'160000,{base},vendor/sub', cwd=work)  # gitlink, no checkout
    git('commit', '-qm', 'fix', cwd=work)
    return work, base, git('rev-parse', 'HEAD', cwd=work)


def fake_git(tmp_path, origin, *, fetch=None):
    """Real Git, except a fetch of URL comes from the local origin, or runs `fetch` (shell) instead."""
    script = tmp_path/'git'
    action = fetch or f'set -- $(printf "%s\\n" "$@" | sed "s#^{URL}\\$#file://{origin}#"); ' \
                      f'exec {GIT} -c protocol.file.allow=always "$@"'
    script.write_text(f'#!/bin/sh\nfor a; do [ "$a" = fetch ] && {{ {action}; }}; done\nexec {GIT} "$@"\n')
    script.chmod(0o755)
    return pin(script)


def private(path):
    path.mkdir(mode=0o700)
    return path


def acquisition(tmp_path, git_exec, **limits):
    return GitAcquisition(git_exec, pin(PRLIMIT), transport=HostTransport(frozenset({'github.com'})),
                          limits=AcquireLimits(**limits), receipts=private(tmp_path/'receipts'))


def receipts(tmp_path, operation):
    return {suffix: json.loads((tmp_path/'receipts'/f'{operation}.{suffix}.json').read_text())
            for suffix in ('intent', 'result')}


def test_complete_acquisition_is_verified_measured_and_admitted_by_git_source(tmp_path, origin):
    work, base, fix = origin
    operation = uuid4()
    with acquisition(tmp_path, fake_git(tmp_path, work)) as acquire:
        source = acquire.acquire(FetchTarget(URL, fix), tmp_path/'repo', operation)
    assert (source.commit, source.parents, source.shallow) == (fix, (base,), False)
    assert (source.tree.regular_files, source.tree.executables, source.tree.symlinks, source.tree.submodules) == (2, 1, 1, 1)
    assert source.tree.regular_bytes == len('one\n#!/bin/sh\n') and source.first_parent.regular_files == 1
    assert source.target() == FetchTarget(URL, fix) and source.target(base) == FetchTarget(URL, base)
    with pytest.raises(ValueError): source.target('f'*40)
    assert os.stat(tmp_path/'repo').st_mode & 0o777 == 0o700
    written = receipts(tmp_path, operation)
    assert written['intent']['outcome'] == 'unknown' and written['result']['outcome'] == 'completed'
    fetch_call = next(call for call in written['result']['native_calls'] if call['args'][0] == 'fetch')
    assert fetch_call['network'] and fetch_call['args'][-1] == f'{fix}:refs/corsair/pinned'
    # The parent has no symlink or gitlink, so the unchanged GitSource admits it from this repository.
    with LocalArtifacts(private(tmp_path/'objects'), max_bytes=1024) as store, \
            GitSource(pin(GIT), pin(PRLIMIT), store=store, limits=SourceLimits(), receipts=private(tmp_path/'capture')) as capture:
        assert capture.capture(Path(source.repository), base, uuid4()).commit == base


def test_depth_gives_a_shallow_measure_only_repository(tmp_path, origin):
    work, base, fix = origin
    with acquisition(tmp_path, fake_git(tmp_path, work), depth=1) as acquire:
        source = acquire.acquire(FetchTarget(URL, fix), tmp_path/'repo', uuid4())
    assert source.shallow and source.parents == (base,) and source.first_parent is None
    with pytest.raises(ValueError): source.target(base)


@pytest.mark.parametrize('stderr, layer', [
    ('fatal: unable to access: CONNECT tunnel failed, response 403', 'host_network'),
    ('fatal: remote error: upload-pack: not our ref ' + 'a'*40, 'source_unavailable'),
    ('fatal: early EOF', 'transport'),
])
def test_fetch_failures_keep_native_detail_and_layer(tmp_path, origin, stderr, layer):
    operation = uuid4()
    with acquisition(tmp_path, fake_git(tmp_path, origin[0], fetch=f"echo '{stderr}' >&2; exit 128")) as acquire:
        with pytest.raises(AcquisitionError) as raised:
            acquire.acquire(FetchTarget(URL, origin[2]), tmp_path/'repo', operation)
    assert raised.value.layer == layer
    result = receipts(tmp_path, operation)['result']
    assert result['outcome'] == 'failed' and result['layer'] == layer and stderr in result['native_calls'][-1]['stderr']


def test_wall_budget_kills_the_fetch_and_reports_budget(tmp_path, origin):
    with acquisition(tmp_path, fake_git(tmp_path, origin[0], fetch='sleep 30'), wall_seconds=2) as acquire:
        with pytest.raises(AcquisitionError) as raised:
            acquire.acquire(FetchTarget(URL, origin[2]), tmp_path/'repo', uuid4())
    assert raised.value.layer == 'budget'


def test_served_commit_must_be_the_requested_one(tmp_path, origin):
    work, base, fix = origin
    # A server that answers with another commit under the pinned ref is refused, not admitted.
    fetch = (f'set -- $(printf "%s\\n" "$@" | sed -e "s#^{URL}\\$#file://{work}#" -e "s#^{fix}:#{base}:#"); '
             f'exec {GIT} -c protocol.file.allow=always "$@"')
    with acquisition(tmp_path, fake_git(tmp_path, work, fetch=fetch)) as acquire:
        with pytest.raises(AcquisitionError) as raised:
            acquire.acquire(FetchTarget(URL, fix), tmp_path/'repo', uuid4())
    assert raised.value.layer == 'source_admission'


def test_repository_byte_budget_is_enforced(tmp_path, origin):
    with acquisition(tmp_path, fake_git(tmp_path, origin[0]), repository_bytes=1024) as acquire:
        with pytest.raises(AcquisitionError) as raised:
            acquire.acquire(FetchTarget(URL, origin[2]), tmp_path/'repo', uuid4())
    assert raised.value.layer == 'budget'


def test_configuration_refusals_dispatch_nothing(tmp_path, origin):
    with acquisition(tmp_path, fake_git(tmp_path, origin[0])) as acquire:
        other = FetchTarget('https://gitlab.com/fixture/repo', origin[2])
        private_target = FetchTarget(URL, origin[2], CredentialBinding('gh', 'GH_TOKEN', 'github.com'))
        for target in (other, private_target):
            with pytest.raises(AcquisitionError) as raised:
                acquire.acquire(target, tmp_path/'repo', uuid4())
            assert raised.value.layer == 'configuration' and raised.value.receipt['delivery'] == 'not_dispatched'
        (tmp_path/'used').mkdir()
        with pytest.raises(AcquisitionError) as raised:  # a destination is never reused
            acquire.acquire(FetchTarget(URL, origin[2]), tmp_path/'used', uuid4())
    assert not (tmp_path/'repo').exists() and raised.value.layer == 'configuration'
    for bad in (dict(wall_seconds=0), dict(depth=0), dict(repository_bytes=17*1024**3)):
        with pytest.raises(ValueError): AcquireLimits(**bad)
    for bad in (dict(allowed_hosts=frozenset()), dict(allowed_hosts=frozenset({'github.com'}), proxy='http://u:p@h:1')):
        with pytest.raises(ValueError): HostTransport(**bad)


def test_tree_stats_counts_noncanonical_paths_and_refuses_unknown_entries():
    blob = 'b'*40
    listing = f'100644 blob {blob}      3\tok\x00100644 blob {blob}      2\tbad\\name\x00'.encode()
    stats = tree_stats('c'*40, 'e'*40, listing)
    assert (stats.regular_files, stats.regular_bytes, stats.noncanonical_paths) == (2, 5, 1)
    with pytest.raises(ValueError): tree_stats('c'*40, 'e'*40, f'040000 tree {blob} -\tdir\x00'.encode())
    with pytest.raises(ValueError): tree_stats('c'*40, 'e'*40, b'100644 blob x 1\tno-terminator')



def test_format_only_fsck_errors_refuse_unless_the_operator_downgrades_them(tmp_path, origin):
    work, base, _ = origin
    tree = git('rev-parse', 'HEAD^{tree}', cwd=work)
    # Historical commits with a malformed time zone exist in real repositories; the hash still identifies them.
    body = f'tree {tree}\nparent {base}\nauthor a <a@b> 0 +99999\ncommitter a <a@b> 0 +0000\n\nold\n'
    odd = subprocess.run([GIT, 'hash-object', '-t', 'commit', '--literally', '-w', '--stdin'], cwd=work, check=True,
                         input=body, capture_output=True, text=True).stdout.strip()
    git('update-ref', 'refs/heads/odd', odd, cwd=work)
    with acquisition(tmp_path, fake_git(tmp_path, work)) as acquire:
        with pytest.raises(AcquisitionError) as raised:
            acquire.acquire(FetchTarget(URL, odd), tmp_path/'refused', uuid4())
    assert raised.value.layer == 'source_admission'
    assert raised.value.receipt['native_calls'][-1]['fsck_messages'] == ['badTimezone']
    (tmp_path/'receipts').rename(tmp_path/'receipts-1')
    with acquisition(tmp_path, fake_git(tmp_path, work), fsck_warn=frozenset({'badTimezone'})) as acquire:
        source = acquire.acquire(FetchTarget(URL, odd), tmp_path/'repo', uuid4())
    assert source.commit == odd and source.fsck_warnings == ('badTimezone',)
    with pytest.raises(ValueError): AcquireLimits(fsck_warn=frozenset({'missingTree'}))
