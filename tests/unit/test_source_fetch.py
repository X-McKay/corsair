"""SPEC-0025 offline contract: fixed recipe, strict receipt, exact host admission; local Git only."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest

from corsair.adapters.git_source import Executable, GitSource, SourceLimits, git_hash
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.nodes.source_fetch import (FETCH_SCRIPT, INVENTORY_SCRIPT, MATERIALIZE_SCRIPT, CredentialBinding,
                                        FetchRecipe, FetchTarget, SourceFetchRefused, admit_fetch, fetch_command,
                                        fetch_source, parse_fetch_receipt)
from corsair.ports.artifacts import ArtifactRef, SourceFile, SourceSnapshot
from corsair.ports.execution import ExecutionError, ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle

COMMIT, TREE = 'c'*40, 'e'*40
URL = 'https://github.com/fixture/repo.git'
RECIPE = FetchRecipe('/bin/sh', '/usr/bin/git', '/usr/lib/git-core/git-remote-https', '/sandbox/src', 64,
                     frozenset({'github.com', 'dev.azure.com'}))
TARGET = FetchTarget(URL, COMMIT)
HANDLE = SandboxHandle('id', 'name', 'default', 'owner', 'creation')
FILES = (('README', '100644', b'hello\n'), ('bin/run', '100755', b'#!/bin/sh\n'), ('src/a/b.txt', '100644', b'b\r\n'))


def snapshot(files=FILES, commit=COMMIT, tree=TREE):
    ref = lambda data: ArtifactRef(hashlib.sha256(data).hexdigest(), len(data))
    return SourceSnapshot(commit, tree, tuple(SourceFile(p, m, git_hash('blob', d), ref(d)) for p, m, d in files), ref(b'manifest'))


def entries(files=FILES):
    lines = {}
    for path, mode, data in files:
        lines[path] = f'f {mode[3:]} {len(data)} {hashlib.sha256(data).hexdigest()}'
        for n in range(1, path.count('/')+1): lines['/'.join(path.split('/')[:n])] = 'd 755 - -'
    return [(path.encode().hex(), line) for path, line in lines.items()]


def stdout(rows=None, head=COMMIT, tree=TREE):
    rows = sorted(entries() if rows is None else rows)
    body = ''.join(f'entry {line} {hexpath}\n' for hexpath, line in rows)
    return f'corsair-source-fetch v1\nhead {head}\ntree {tree}\n{body}end {len(rows)}\n'.encode()


def receipt(out=None, **changes):
    values = dict(operation='op', handle=HANDLE, started_at='t', elapsed_seconds=1.5, delivery='acknowledged',
                  completion='terminal_observed', reason='terminal', stdout=stdout() if out is None else out, native_exit=0)
    return ExecutionReceipt(**values | changes)


def test_recipe_is_a_constant_and_data_only_travels_as_arguments():
    credential = CredentialBinding('ado-read', 'ADO_PLACEHOLDER', 'dev.azure.com')
    other = FetchTarget('https://dev.azure.com/org/project/_git/repo', 'a'*40, credential)
    first, second = fetch_command(RECIPE, TARGET), fetch_command(RECIPE, other)
    assert first[:5] == second[:5] == ('/bin/sh', '-euc', FETCH_SCRIPT, 'corsair-source-fetch', '/bin/sh')
    assert first[5:] == ('/usr/bin/git', '/sandbox/src', URL, COMMIT, '', '')
    assert second[7:] == (other.url, 'a'*40, 'ADO_PLACEHOLDER', '')
    assert fetch_command(replace(RECIPE, skip_nonregular=True), TARGET)[-1] == '1'
    assert URL not in FETCH_SCRIPT and 'github' not in FETCH_SCRIPT and 'protocol.allow=never' in FETCH_SCRIPT
    with pytest.raises(ValueError): fetch_command(replace(RECIPE, allowed_hosts=frozenset({'dev.azure.com'})), TARGET)


@pytest.mark.parametrize('url', ['https://github.com/a/b;id', 'https://github.com/a/$(id)', 'https://github.com/a/`id`',
                                 'https://github.com/a b', "https://github.com/a'b", 'http://github.com/a/b',
                                 'ssh://github.com/a/b', 'file:///tmp/repo', 'https://user:pw@github.com/a/b',
                                 'https://github.com:444/a/b', 'https://github.com/a/b?x=1', 'https://github.com/a/b#f',
                                 'https://github.com/a/../b', 'https://GitHub.com/a/b', 'https://github.com', '-uhttps://github.com/a'])
def test_unsafe_or_noncanonical_urls_refused_at_construction(url):
    with pytest.raises(ValueError): FetchTarget(url, COMMIT)


@pytest.mark.parametrize('commit', ['c'*39, 'C'*40, 'HEAD', 'g'*40, 'c'*40+'\n', '--upload-pack=x'])
def test_non_exact_commits_refused(commit):
    with pytest.raises(ValueError): FetchTarget(URL, commit)


@pytest.mark.parametrize('change', [dict(git='git'), dict(workdir='/'), dict(workdir='/sandbox/../etc'), dict(transport='/usr/lib/git core'),
                                    dict(max_inventory_entries=0), dict(allowed_hosts={'github.com'}), dict(allowed_hosts=frozenset())])
def test_recipe_is_strictly_operator_shaped(change):
    with pytest.raises(ValueError): replace(RECIPE, **change)


def test_credential_binds_exactly_the_repository_host():
    assert FetchTarget(URL, COMMIT, CredentialBinding('gh-app', 'GH_PLACEHOLDER', 'github.com')).credential.host == 'github.com'
    for host in ('dev.azure.com', 'api.github.com'):
        with pytest.raises(ValueError, match='exactly the repository host'):
            FetchTarget(URL, COMMIT, CredentialBinding('gh-app', 'GH_PLACEHOLDER', host))
    with pytest.raises(ValueError): CredentialBinding('gh-app', 'lower; id', 'github.com')


def test_matching_receipt_is_admitted_with_native_timing():
    admission = admit_fetch(receipt(), snapshot(), RECIPE, TARGET)
    assert (admission.commit, admission.tree, admission.file_count, admission.total_bytes) == (COMMIT, TREE, 3, 19)
    assert (admission.elapsed_seconds, admission.operation) == (1.5, 'op')


def drop(lines, index): return lines[:index]+lines[index+1:]


@pytest.mark.parametrize('mutate', [
    lambda s: b'', lambda s: s[:-1], lambda s: s + b'extra\n', lambda s: s.replace(b' v1', b' v2'),
    lambda s: b'\n'.join(drop(s.split(b'\n'), 1)), lambda s: b'\n'.join(drop(s.split(b'\n'), 3)),
    lambda s: s.replace(b'end 6', b'end 7'), lambda s: s.replace(b'end 6', b'end 06'),
    lambda s: s.replace(b'head '+COMMIT.encode(), b'head '+COMMIT.upper().encode()),
    lambda s: s.replace(b'entry f 644', b'entry f 644 ', 1), lambda s: s.replace(b'entry f 644', b'entry x 644', 1),
    lambda s: s.replace(b' - -', b' 0 -', 1), lambda s: s.replace(b'README'.hex().encode(), b'2e2e2f78'),
    lambda s: s.replace(b'README'.hex().encode(), b'52454144'+b'4D45'), lambda s: s.replace(b'README'.hex().encode(), b'ff'),
    lambda s: b'\n'.join(sorted(s.split(b'\n')[3:-2], reverse=True)).join([b'corsair-source-fetch v1\nhead '+COMMIT.encode()+b'\ntree '+TREE.encode()+b'\n', b'\nend 6\n']),
], ids=['empty', 'unterminated', 'extra', 'version', 'missing-head', 'missing-entry', 'count', 'count-form', 'head-case',
        'spacing', 'kind', 'dir-size', 'dotdot', 'hex-case', 'utf8', 'order'])
def test_receipt_parser_refusals(mutate):
    with pytest.raises(ValueError): parse_fetch_receipt(mutate(stdout()), 64)
    with pytest.raises(SourceFetchRefused) as error: admit_fetch(receipt(mutate(stdout())), snapshot(), RECIPE, TARGET)
    assert error.value.layer == 'source_admission' and error.value.discard_sandbox


def test_duplicate_and_oversize_inventories_refused():
    rows = sorted(entries())
    with pytest.raises(ValueError, match='sorted or duplicated'): parse_fetch_receipt(stdout(rows+rows[:1]), 64)
    with pytest.raises(ValueError, match='over bound'): parse_fetch_receipt(stdout(), 5)
    assert len(parse_fetch_receipt(stdout(), 6).entries) == 6


def row(path, line): return (path.encode().hex(), line)


@pytest.mark.parametrize('rows,head,tree,reason', [
    (None, 'd'*40, TREE, 'commit or tree'), (None, COMMIT, 'd'*40, 'commit or tree'),
    ([r for r in entries() if r[0] != 'README'.encode().hex()], COMMIT, TREE, 'missing file README'),
    (entries()+[row('NEW', 'f 644 0 '+hashlib.sha256(b'').hexdigest())], COMMIT, TREE, 'extra file NEW'),
    (entries(FILES[:2]+(('src/a/b.txt', '100644', b'b\n'),)), COMMIT, TREE, 'bytes differ: src/a/b.txt'),
    (entries(FILES[:1]+(('bin/run', '100644', b'#!/bin/sh\n'),)+FILES[2:]), COMMIT, TREE, 'mode, size or bytes differ: bin/run'),
    ([r if r[0] != 'README'.encode().hex() else row('README', 'l 777 - -') for r in entries()], COMMIT, TREE, 'non-regular entry README'),
    (entries()+[row('fifo', 'o 644 - -')], COMMIT, TREE, 'non-regular entry fifo'),
    (entries()+[row('empty', 'd 755 - -')], COMMIT, TREE, 'extra directory empty'),
    ([r for r in entries() if r[0] != 'src'.encode().hex()], COMMIT, TREE, 'missing directory src'),
], ids=['commit', 'tree', 'missing', 'extra', 'modified', 'mode', 'symlink', 'other', 'empty-dir', 'missing-dir'])
def test_host_comparison_refusals(rows, head, tree, reason):
    with pytest.raises(SourceFetchRefused, match=reason) as error:
        admit_fetch(receipt(stdout(rows, head, tree)), snapshot(), RECIPE, TARGET)
    assert error.value.layer == 'source_admission'


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_receipt_containing_secret_refused_before_any_other_outcome(stream):
    secret = b'ghs_realtoken'
    leaked = {stream: (stdout() if stream == 'stdout' else b'') + b'auth ' + secret}
    for status in (dict(), dict(native_exit=128), dict(delivery='unknown')):
        with pytest.raises(SourceFetchRefused) as error:
            admit_fetch(receipt(**leaked | status), snapshot(), RECIPE, TARGET, secrets=(b'other', secret))
        assert error.value.layer == 'credential' and secret not in str(error.value).encode()
    with pytest.raises(ValueError): admit_fetch(receipt(), snapshot(), RECIPE, TARGET, secrets=(b'',))


@pytest.mark.parametrize('status,layer', [(128, 'dependency'), (1, 'dependency'), (65, 'source_admission'), (66, 'credential'), (None, 'dependency')])
def test_nonzero_exit_is_attributed_not_admitted(status, layer):
    with pytest.raises(SourceFetchRefused) as error: admit_fetch(receipt(native_exit=status), snapshot(), RECIPE, TARGET)
    assert error.value.layer == layer


class Execution:
    def __init__(self, result): self.result, self.calls = result, []

    def execute(self, handle, command, operation):
        self.calls.append((handle, command, operation))
        if isinstance(self.result, ExecutionError): raise self.result
        return replace(self.result, operation=str(operation))


@pytest.mark.parametrize('status', [dict(delivery='unknown', completion='unknown'), dict(completion='unknown'),
                                    dict(delivery='not_dispatched')])
def test_unknown_outcome_refused_once_without_retry(status):
    execution, operation = Execution(receipt(**status)), uuid4()
    with pytest.raises(SourceFetchRefused) as error:
        fetch_source(execution, HANDLE, snapshot(), RECIPE, TARGET, operation)
    assert error.value.layer == 'sandbox' and 'no retry' in error.value.reason and error.value.discard_sandbox
    assert execution.calls == [(HANDLE, fetch_command(RECIPE, TARGET), operation)]


@pytest.mark.parametrize('layer,expected', [('native_execution', 'native_execution'), (None, 'sandbox')])
def test_execution_error_is_mapped_once(layer, expected):
    failed = receipt(b'', delivery='unknown', completion='unknown', reason='host_timeout', failure_layer=layer, native_exit=None)
    execution = Execution(ExecutionError(failed))
    with pytest.raises(SourceFetchRefused) as error: fetch_source(execution, HANDLE, snapshot(), RECIPE, TARGET, uuid4())
    assert (error.value.layer, error.value.reason, error.value.receipt) == (expected, 'host_timeout', failed)
    assert len(execution.calls) == 1
    leaked = Execution(ExecutionError(replace(failed, stderr=b'token')))
    with pytest.raises(SourceFetchRefused) as error: fetch_source(leaked, HANDLE, snapshot(), RECIPE, TARGET, uuid4(), secrets=(b'token',))
    assert error.value.layer == 'credential'


def test_fetch_source_admits_and_refuses_mismatched_target_before_dispatch():
    execution, operation = Execution(receipt()), uuid4()
    assert fetch_source(execution, HANDLE, snapshot(), RECIPE, TARGET, operation).operation == str(operation)
    with pytest.raises(ValueError): fetch_source(execution, HANDLE, snapshot(commit='a'*40), RECIPE, TARGET, uuid4())
    assert len(execution.calls) == 1


# Local end-to-end run of the fixed script parts with the real local git; not live qualification.
GIT, PRLIMIT = shutil.which('git'), shutil.which('prlimit')
ENV = {'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}


def git(repo, *args, input=None, env=()):
    return subprocess.run([GIT, '-c', 'core.hooksPath=/dev/null', '-C', str(repo), *args], input=input, check=True,
                          capture_output=True, env=ENV | dict(env)).stdout


def script(text, workdir, url='', commit='', name='', skip=''):
    return subprocess.run(['/bin/sh', '-euc', text, 'corsair-source-fetch', '/bin/sh', GIT, str(workdir), url, commit, name, skip],
                          capture_output=True, env=ENV)


def pin(path): return Executable(Path(path), hashlib.sha256(Path(path).read_bytes()).hexdigest())


@pytest.fixture
def fixture_repo(tmp_path):
    if not GIT: pytest.skip('git not installed')
    repo = tmp_path/'repo'; repo.mkdir(mode=0o700); git(repo, 'init', '--bare', '-q')
    files = {'.gitattributes': ('100644', b'* text eol=crlf\nident.txt ident\n'), 'ident.txt': ('100644', b'$Id$\nline\n'),
             'bin/run': ('100755', b'#!/bin/sh\necho ok\n'), 'src/deep/nested.txt': ('100644', b'a\nb\n')}
    index = {'GIT_INDEX_FILE': str(tmp_path/'index')}
    for path, (mode, data) in files.items():
        blob = git(repo, 'hash-object', '-w', '--stdin', input=data).strip().decode()
        git(repo, 'update-index', '--add', '--cacheinfo', f'{mode},{blob},{path}', env=index)
    tree = git(repo, 'write-tree', env=index).strip()
    raw = b'tree '+tree+b'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nfixture\n'
    commit = git(repo, 'hash-object', '-t', 'commit', '-w', '--stdin', input=raw).strip().decode()
    git(repo, 'update-ref', 'refs/heads/main', commit)
    return repo, commit, files


def test_fetch_script_refuses_non_https_and_nonempty_workdir(fixture_repo, tmp_path):
    repo, commit, _ = fixture_repo
    work = tmp_path/'refused'
    result = script(FETCH_SCRIPT, work, 'file://'+str(repo), commit)
    assert result.returncode not in (0, 65) and result.stdout == b'' and not (work/'ident.txt').exists()
    (work/'stray').touch()
    result = script(FETCH_SCRIPT, work, URL, commit)
    assert (result.returncode, result.stdout) == (65, b'') and b'workdir not empty' in result.stderr


def test_materialized_bytes_match_capture_without_checkout_transformations(fixture_repo, tmp_path):
    repo, commit, files = fixture_repo
    if not PRLIMIT: pytest.skip('prlimit not installed; GitSource capture needs it')
    root = tmp_path/'capture'; root.mkdir(mode=0o700); (root/'objects').mkdir(mode=0o700); (root/'receipts').mkdir(mode=0o700)
    with LocalArtifacts(root/'objects', max_bytes=1024*1024) as store, GitSource(pin(GIT), pin(PRLIMIT), store=store,
                                                                                  limits=SourceLimits(), receipts=root/'receipts') as source:
        captured = source.capture(repo, commit, uuid4())
    work = tmp_path/'work'; work.mkdir(); git(work, 'init', '-q')
    git(work, '-c', 'protocol.file.allow=always', 'fetch', '-q', '--depth=1', '--no-tags', 'file://'+str(repo), commit)
    result = script(MATERIALIZE_SCRIPT, work, commit=commit)
    assert result.returncode == 0, result.stderr
    recipe = replace(RECIPE, workdir=str(work))
    target = FetchTarget(URL, commit)
    admission = admit_fetch(receipt(result.stdout), captured, recipe, target)
    assert (admission.commit, admission.file_count) == (commit, 4)
    for path, (mode, data) in files.items():
        assert (work/path).read_bytes() == data and oct((work/path).stat().st_mode & 0o777)[2:] == mode[3:]
    clone = tmp_path/'clone'
    subprocess.run([GIT, '-c', 'protocol.file.allow=always', 'clone', '-q', '-b', 'main', 'file://'+str(repo), str(clone)], check=True, env=ENV)
    assert (clone/'ident.txt').read_bytes() != files['ident.txt'][1], 'fixture must exercise checkout transformations'

    def mutated(name, change):
        copy = tmp_path/name; shutil.copytree(work, copy, symlinks=True); change(copy)
        out = script(INVENTORY_SCRIPT, copy, commit=commit)
        assert out.returncode == 0, out.stderr
        return receipt(out.stdout)
    cases = {'modified': lambda w: (w/'ident.txt').write_bytes(b'$Id$\r\nline\r\n'), 'added': lambda w: (w/'extra').touch(),
             'deleted': lambda w: (w/'src/deep/nested.txt').unlink(), 'mode': lambda w: (w/'bin/run').chmod(0o644),
             'empty-dir': lambda w: (w/'src/empty').mkdir(), 'symlink': lambda w: (w/'link').symlink_to('/etc/passwd'),
             'replaced-by-link': lambda w: ((w/'ident.txt').unlink(), (w/'ident.txt').symlink_to('/etc/hostname'))}
    for name, change in cases.items():
        with pytest.raises(SourceFetchRefused) as error: admit_fetch(mutated(name, change), captured, recipe, target)
        assert error.value.layer == 'source_admission', name
    assert admit_fetch(mutated('unchanged', lambda w: None), captured, recipe, target).file_count == 4


def nonregular_commit(repo, entry):
    blob = git(repo, 'hash-object', '-w', '--stdin', input=b'/etc/passwd').strip()
    plain = b'100644 blob ' + blob + b'\tplain\0'
    subtree = git(repo, 'mktree', '-z', input=b''.join(sorted([plain, entry.replace(b'{blob}', blob)],
                                                               key=lambda e: e.split(b'\t')[1]))).strip()
    tree = git(repo, 'mktree', '-z', input=b'040000 tree ' + subtree + b'\tdir\0').strip()
    raw = b'tree '+tree+b'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nfixture\n'
    commit = git(repo, 'hash-object', '-t', 'commit', '-w', '--stdin', input=raw).strip().decode()
    git(repo, 'update-ref', 'refs/heads/nonregular', commit)
    return commit


@pytest.mark.parametrize('entry,mode', [(b'120000 blob {blob}\tlink\0', '120000'),
                                        (b'160000 commit ' + b'a'*40 + b'\tmodule\0', '160000')])
def test_skipped_entries_match_a_capture_that_skipped_them(fixture_repo, tmp_path, entry, mode):
    repo, _, _ = fixture_repo
    if not PRLIMIT: pytest.skip('prlimit not installed; GitSource capture needs it')
    commit = nonregular_commit(repo, entry)
    root = tmp_path/'capture'; root.mkdir(mode=0o700); (root/'objects').mkdir(mode=0o700); (root/'receipts').mkdir(mode=0o700)
    with LocalArtifacts(root/'objects', max_bytes=1024*1024) as store, GitSource(
            pin(GIT), pin(PRLIMIT), store=store, limits=SourceLimits(), receipts=root/'receipts', skip_nonregular=True) as source:
        captured = source.capture(repo, commit, uuid4())
    assert [(e.path, e.mode) for e in captured.skipped] == [('dir/link' if mode == '120000' else 'dir/module', mode)]
    work = tmp_path/'work'; work.mkdir(); git(work, 'init', '-q')
    git(work, '-c', 'protocol.file.allow=always', 'fetch', '-q', '--depth=1', 'file://'+str(repo), commit)
    result = script(MATERIALIZE_SCRIPT, work, commit=commit, skip='1')
    assert result.returncode == 0, result.stderr
    assert sorted(os.listdir(work/'dir')) == ['plain'] and b'\nskip '+mode.encode() in result.stdout
    recipe = replace(RECIPE, workdir=str(work), skip_nonregular=True)
    target = FetchTarget(URL, commit)
    assert admit_fetch(receipt(result.stdout), captured, recipe, target).file_count == 1
    with pytest.raises(ValueError, match='recipe must skip'): admit_fetch(receipt(result.stdout), captured, RECIPE, target)
    other = replace(captured, skipped=(replace(captured.skipped[0], object='b'*40),))
    with pytest.raises(SourceFetchRefused, match='skipped entries differ'): admit_fetch(receipt(result.stdout), other, recipe, target)
    with pytest.raises(SourceFetchRefused, match='skipped entries differ'):
        admit_fetch(receipt(result.stdout), replace(captured, skipped=()), recipe, target)
    (work/'dir/link').symlink_to('/etc/passwd')  # a skipped path that appears in the workdir anyway is refused
    planted = script(INVENTORY_SCRIPT, work, commit=commit, skip='1')
    with pytest.raises(SourceFetchRefused, match='non-regular entry'): admit_fetch(receipt(planted.stdout), captured, recipe, target)
    with pytest.raises(ValueError, match='Malformed skip'): parse_fetch_receipt(result.stdout.replace(b'skip '+mode.encode(), b'skip 100644'), 64)


@pytest.mark.parametrize('entry', [b'120000 blob {blob}\tlink\0', b'160000 commit ' + b'a'*40 + b'\tmodule\0'])
def test_materialization_refuses_symlink_and_submodule_entries(fixture_repo, tmp_path, entry):
    repo, _, _ = fixture_repo
    blob = git(repo, 'hash-object', '-w', '--stdin', input=b'/etc/passwd').strip()
    plain = b'100644 blob ' + blob + b'\tplain\0'
    tree = git(repo, 'mktree', '-z', input=b''.join(sorted([plain, entry.replace(b'{blob}', blob)], key=lambda e: e.split(b'\t')[1]))).strip()
    raw = b'tree '+tree+b'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nfixture\n'
    commit = git(repo, 'hash-object', '-t', 'commit', '-w', '--stdin', input=raw).strip().decode()
    git(repo, 'update-ref', 'refs/heads/other', commit)
    work = tmp_path/'work'; work.mkdir(); git(work, 'init', '-q')
    git(work, '-c', 'protocol.file.allow=always', 'fetch', '-q', '--depth=1', 'file://'+str(repo), commit)
    result = script(MATERIALIZE_SCRIPT, work, commit=commit)
    assert (result.returncode, result.stdout) == (65, b'') and os.listdir(work) == ['.git']
