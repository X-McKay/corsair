"""Actual local files and native offline Git contracts; no sandbox qualification."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from corsair.adapters.local_artifacts import LocalArtifacts, ArtifactStorageError
from corsair.adapters.git_source import Executable, GitSource, SourceCaptureError, SourceLimits, confined_path
from corsair.ports.artifacts import ArtifactRef


def pin(path):
    path=Path(path)
    return Executable(path,hashlib.sha256(path.read_bytes()).hexdigest())


def private(path):
    path.mkdir(mode=0o700)
    return path


def git(repo,*args,input=None):
    return subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(repo),*args],input=input,
                          capture_output=True,check=True,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}).stdout


def repository(path, entries):
    private(path)
    git(path,'init','--bare','--quiet')
    lines=[]
    for name,mode,data in entries:
        blob=git(path,'hash-object','-w','--stdin',input=data).strip()
        lines.append(mode.encode()+b' blob '+blob+b'\t'+name.encode()+b'\0')
    tree=git(path,'mktree','-z',input=b''.join(lines)).strip()
    raw=b'tree '+tree+b'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nfixture\n'
    commit=git(path,'hash-object','-t','commit','-w','--stdin',input=raw).strip().decode()
    return commit


def capture(root,repo,commit,*,limits=None,op=None,**options):
    with LocalArtifacts(private(root/'objects'),max_bytes=4*1024*1024) as store:
        with GitSource(pin('/usr/bin/git'),pin('/usr/bin/prlimit'),store=store,
                       limits=limits or SourceLimits(),receipts=private(root/'receipts'),**options) as source:
            return source.capture(repo,commit,op or uuid4())


def test_immutable_restart_duplicate_binary_and_expected_digest(tmp_path):
    root=private(tmp_path/'objects');data=b'\x00\xffnative\n'
    with LocalArtifacts(root,max_bytes=32) as store:
        ref=store.put(data);identity=(root/ref.sha256).stat().st_ino
        assert store.put(data)==ref and (root/ref.sha256).stat().st_ino==identity
        with pytest.raises(ValueError):store.put(data,expected_sha256='0'*64)
        assert not list(root.glob('*.partial'))
    with LocalArtifacts(root,max_bytes=32) as reopened:assert reopened.get(ref)==data


@pytest.mark.parametrize('poison',['corruption','symlink','fifo'])
def test_corrupt_or_nonregular_objects_refused_without_overwrite(tmp_path,poison):
    root=private(tmp_path/'objects');data=b'abcd';ref=ArtifactRef(hashlib.sha256(data).hexdigest(),4);path=root/ref.sha256
    if poison=='corruption':path.write_bytes(b'evil');path.chmod(0o400)
    elif poison=='symlink':path.symlink_to(tmp_path/'outside')
    else:os.mkfifo(path,0o400)
    identity=path.lstat().st_ino
    with LocalArtifacts(root,max_bytes=32) as store:
        with pytest.raises(ArtifactStorageError):store.get(ref)
        with pytest.raises(ArtifactStorageError):store.put(data)
    assert path.lstat().st_ino==identity and not list(root.glob('*.partial'))


def test_publication_failure_retains_possible_identity_and_exact_cleanup(tmp_path,monkeypatch):
    root=private(tmp_path/'objects');real=os.fsync;calls=[]
    def fail_directory(fd):
        calls.append(fd)
        if len(calls)==2:raise OSError('directory durability unavailable')
        return real(fd)
    with LocalArtifacts(root,max_bytes=32) as store:
        monkeypatch.setattr(os,'fsync',fail_directory)
        with pytest.raises(ArtifactStorageError) as error:store.put(b'abc')
        receipt=error.value
        assert receipt.publication=='durability_unknown' and receipt.temporary_cleanup=='confirmed'
        assert receipt.temporary_identity and not (root/receipt.temporary_name).exists()
        assert store.get(receipt.reference)==b'abc'


def test_temporary_identity_replacement_refuses_cleanup(tmp_path,monkeypatch):
    root=private(tmp_path/'objects');real=os.link;replacement=[]
    def substitute(name,digest,**kwargs):
        real(name,digest,**kwargs)
        (root/name).unlink();(root/name).write_bytes(b'replaced');replacement.append(root/name)
    with LocalArtifacts(root,max_bytes=32) as store:
        monkeypatch.setattr(os,'link',substitute)
        with pytest.raises(ArtifactStorageError) as error:store.put(b'abc')
        assert error.value.publication=='admitted' and error.value.temporary_cleanup=='unconfirmed'
        assert root/error.value.temporary_name==replacement[0] and error.value.temporary_identity
        assert replacement[0].read_bytes()==b'replaced'


def test_private_root_and_byte_reference_limits(tmp_path):
    root=private(tmp_path/'objects')
    with LocalArtifacts(root,max_bytes=2) as store:
        with pytest.raises(ValueError):store.put(b'abc')
        with pytest.raises(ValueError):store.get(ArtifactRef('0'*64,3))
    root.chmod(0o755)
    with pytest.raises(ValueError):LocalArtifacts(root,max_bytes=2)
    link=tmp_path/'link';link.symlink_to(root,target_is_directory=True)
    with pytest.raises(OSError):LocalArtifacts(link,max_bytes=2)


def test_raw_committed_source_ignores_worktree_filters_hooks_and_replacements(tmp_path):
    repo=tmp_path/'repo';data=b'\xffraw $Format:%H$\r\n'
    commit=repository(repo,[('payload','100755',data),('.gitattributes','100644',b'payload filter=evil export-subst\n')])
    marker=tmp_path/'MUST-NOT-RUN';hook=repo/'hooks/post-checkout';hook.write_text(f'#!/bin/sh\ntouch {marker}\n');hook.chmod(0o755)
    git(repo,'config','filter.evil.smudge',f'touch {marker}')
    git(repo,'config','filter.evil.clean',f'touch {marker}')
    git(repo,'update-ref','HEAD',commit)
    (repo/'payload').write_bytes(b'not committed')
    # Replacement target in this repo points at the same tree with a different message.
    raw=git(repo,'cat-file','commit',commit)+b'changed\n'
    replacement=git(repo,'hash-object','-t','commit','-w','--stdin',input=raw).strip().decode()
    git(repo,'replace',commit,replacement)
    snapshot=capture(tmp_path,repo,commit)
    with LocalArtifacts(tmp_path/'objects',max_bytes=4*1024*1024) as store:
        file=next(f for f in snapshot.files if f.path=='payload')
        assert file.mode=='100755' and store.get(file.artifact)==data
        manifest=json.loads(store.get(snapshot.manifest));assert manifest['commit']==commit
    assert not marker.exists()


@pytest.mark.parametrize('mode,data',[('120000',b'/etc/passwd'),('100644',b'X'*33)])
def test_source_type_and_size_failures_are_retained(tmp_path,mode,data):
    repo=tmp_path/'repo';commit=repository(repo,[('payload',mode,data)]);op=uuid4()
    with pytest.raises(SourceCaptureError) as error:
        capture(tmp_path,repo,commit,limits=replace(SourceLimits(),max_file_bytes=32),op=op)
    receipt=error.value.receipt
    assert receipt['outcome']=='failed' and receipt['layer']=='source_admission'
    assert receipt['admitted_artifacts']==[] and all(c['reaped'] for c in receipt['native_calls'])
    assert json.loads((tmp_path/f'receipts/{op}.result.json').read_text())['outcome']=='failed'


def test_source_operation_reuse_and_post_admission_receipt_loss(tmp_path,monkeypatch):
    repo=tmp_path/'repo';commit=repository(repo,[('payload','100644',b'abc')]);op=uuid4()
    with LocalArtifacts(private(tmp_path/'objects'),max_bytes=4096) as store, GitSource(pin('/usr/bin/git'),pin('/usr/bin/prlimit'),store=store,limits=SourceLimits(),receipts=private(tmp_path/'receipts')) as source:
        original=source._journal.write
        def fail_result(operation,suffix,value):
            if suffix=='result':raise OSError('receipt unavailable')
            return original(operation,suffix,value)
        monkeypatch.setattr(source._journal,'write',fail_result)
        with pytest.raises(SourceCaptureError) as error:source.capture(repo,commit,op)
        receipt=error.value.receipt;assert receipt['outcome']=='completed' and receipt['snapshot'] and receipt['storage_error']
        with pytest.raises(SourceCaptureError) as reused:source.capture(repo,commit,op)
        assert not reused.value.receipt['native_calls'] and reused.value.receipt['delivery']=='not_dispatched'
        ref=receipt['snapshot']['manifest'];assert store.get(ArtifactRef(**ref))


def test_native_fsck_rejects_corrupted_tree_before_artifact_admission(tmp_path):
    import zlib
    repo=tmp_path/'repo';commit=repository(repo,[('payload','100644',b'abc')])
    tree=git(repo,'cat-file','commit',commit).splitlines()[0][5:].decode()
    path=repo/'objects'/tree[:2]/tree[2:]
    raw=zlib.decompress(path.read_bytes());assert b'payload' in raw
    path.chmod(0o600);path.write_bytes(zlib.compress(raw.replace(b'payload',b'changed')))
    with pytest.raises(SourceCaptureError) as error:capture(tmp_path,repo,commit)
    receipt=error.value.receipt
    assert receipt['outcome']=='failed' and receipt['layer']=='native_source' and not receipt['admitted_artifacts']
    assert receipt['native_calls'][-1]['args'][0]=='fsck' and receipt['native_calls'][-1]['stderr_base64']


@pytest.mark.parametrize('case',['count','partial','promisor','unsafe'])
def test_source_admission_and_partial_artifacts_remain_attributable(tmp_path,case):
    entries=[('a','100644',b'a'),('b','100644',b'long')]
    if case=='unsafe':entries=[('.git','100644',b'unsafe')]
    repo=tmp_path/'repo';commit=repository(repo,entries)
    if case=='promisor':git(repo,'config','remote.fixture.promisor','true')
    limits=replace(SourceLimits(),max_files=1) if case=='count' else replace(SourceLimits(),max_file_bytes=2)
    with pytest.raises(SourceCaptureError) as error:capture(tmp_path,repo,commit,limits=limits)
    receipt=error.value.receipt
    assert receipt['outcome']=='failed' and all(c['reaped'] for c in receipt['native_calls'])
    assert len(receipt['admitted_artifacts'])==(1 if case=='partial' else 0)
    assert receipt['snapshot'] is None


@pytest.mark.parametrize('path',['/absolute','a/../b','./a','a//b','a\\b','a\nb','A/.GiT/config'])
def test_path_confinement(path):
    with pytest.raises(ValueError):confined_path(path)


@pytest.mark.parametrize('body,cap,wall',[('print("X"*20000,flush=True)',32,2),('import time;time.sleep(30)',32,1)])
def test_native_pipe_limits_reap_original_child(tmp_path,body,cap,wall):
    fake=tmp_path/'fake-git';fake.write_text('#!/usr/bin/python3\n'+body+'\n');fake.chmod(0o700)
    with LocalArtifacts(private(tmp_path/'objects'),max_bytes=4096) as store, GitSource(pin(fake),pin('/usr/bin/prlimit'),store=store,limits=replace(SourceLimits(),wall_seconds=wall),receipts=private(tmp_path/'receipts')) as source:
        calls=[]
        import time
        with pytest.raises((ValueError,TimeoutError)):
            source._native(tmp_path,['--version'],cap,time.monotonic()+wall,calls)
        assert len(calls)==1 and calls[0]['reaped'] and calls[0]['exit'] is not None and calls[0]['stdout_bytes']<=cap


def test_nonregular_entries_are_refused_unless_skipped_and_listed(tmp_path):
    repo=tmp_path/'repo';commit=repository(repo,[('a','100644',b'a'),('link','120000',b'a')])
    with pytest.raises(SourceCaptureError) as error:capture(private(tmp_path/'strict'),repo,commit)
    assert error.value.receipt['layer']=='source_admission' and not error.value.receipt['skipped']
    op=uuid4();snapshot=capture(private(tmp_path/'skip'),repo,commit,op=op,skip_nonregular=True)
    assert [f.path for f in snapshot.files]==['a']
    with LocalArtifacts(tmp_path/'skip/objects',max_bytes=4096) as store:
        manifest=json.loads(store.get(snapshot.manifest))
    skipped=[dict(path='link',mode='120000',kind='symlink',object=git(repo,'rev-parse',f'{commit}:link').strip().decode())]
    assert manifest['skipped']==skipped
    assert json.loads((tmp_path/f'skip/receipts/{op}.result.json').read_text())['skipped']==skipped
    # A regular-only tree keeps the unchanged manifest shape.
    plain=repository(tmp_path/'plain',[('a','100644',b'a')])
    snapshot=capture(private(tmp_path/'plain-capture'),tmp_path/'plain',plain,skip_nonregular=True)
    with LocalArtifacts(tmp_path/'plain-capture/objects',max_bytes=4096) as store:
        assert 'skipped' not in json.loads(store.get(snapshot.manifest))


def test_format_only_fsck_messages_are_refused_unless_the_operator_ignores_them(tmp_path):
    repo=tmp_path/'repo';good=repository(repo,[('a','100644',b'a')])
    tree=git(repo,'cat-file','commit',good).splitlines()[0][5:]
    raw=b'tree '+tree+b'\nauthor Fixture <fixture@invalid> 1 +99999\ncommitter Fixture <fixture@invalid> 1 +0000\n\nold\n'
    odd=git(repo,'hash-object','-t','commit','--literally','-w','--stdin',input=raw).strip().decode()
    with pytest.raises(SourceCaptureError) as error:capture(private(tmp_path/'strict'),repo,odd)
    assert error.value.receipt['native_calls'][-1]['args'][0]=='fsck'
    op=uuid4();snapshot=capture(private(tmp_path/'ignore'),repo,odd,op=op,fsck_ignore=frozenset({'badTimezone'}))
    assert snapshot.commit==odd
    assert json.loads((tmp_path/f'ignore/receipts/{op}.result.json').read_text())['fsck_ignore']==['badTimezone']
    for bad in (dict(fsck_ignore=frozenset({'missingTree'})),dict(skip_nonregular=1)):
        with pytest.raises(ValueError):capture(private(tmp_path/f'bad{len(bad)}{list(bad)[0]}'),repo,odd,**bad)
