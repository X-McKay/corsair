"""Pre-execution native source composition; no product transfer adapter."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.git_source import Executable, GitSource, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.receipts import ReceiptDirectory
from tests.qualification.gateway import gateway
from tests.qualification.test_adapter_lifecycle import adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, execute
from tests.qualification.support import ROOT

SOURCES = ['tests/qualification/test_source_upload.py', 'src/corsair/adapters/git_source.py',
           'src/corsair/adapters/local_artifacts.py', 'src/corsair/ports/artifacts.py',
           'src/corsair/adapters/receipts.py', 'tests/qualification/test_adapter_lifecycle.py',
           'tests/qualification/test_recovery.py', 'tests/qualification/test_lifecycle.py',
           'tests/qualification/test_policy.py', 'tests/qualification/gateway.py',
           'tests/qualification/support.py', 'deploy/runtime-lock.yaml',
           'policies/openshell/identity.yaml', 'Makefile', 'pyproject.toml', 'uv.lock']

# Trusted operator verifier only: never execute a source file or import it.
# The exact fixture contract is intentionally smaller than the source envelope.
VERIFY = '''import hashlib,json,os,stat
root={root!r};expected={expected!r}
assert os.path.realpath(root)==root
def identity(p,owned=True):
 s=os.lstat(p)
 if owned:assert s.st_uid==os.geteuid()
 return dict(device=s.st_dev,inode=s.st_ino,mode=stat.S_IMODE(s.st_mode),uid=s.st_uid)
parent=identity(os.path.dirname(root),False);assert parent=={parent!r}
assert stat.S_ISDIR(os.lstat(root).st_mode) and identity(root)['mode']==448
files={{}};directories={{'.':identity(root)}};total=0
for current,dirs,names in os.walk(root,followlinks=False):
 for name in dirs:
  p=os.path.join(current,name);s=os.lstat(p)
  assert stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==448
  directories[os.path.relpath(p,root)]=identity(p)
  assert len(directories)<=2
 for name in names:
  p=os.path.join(current,name);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(fd,'rb') as f:
   s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
   assert s.st_uid==os.geteuid() and s.st_size<=1048576
   data=f.read(1048577);assert len(data)==s.st_size and len(data)<=1048576
  rel=os.path.relpath(p,root);assert len(rel.encode())<=1024
  total+=len(data);assert len(files)<5 and total<=4194304
  files[rel]=dict(mode=stat.S_IMODE(s.st_mode),size=len(data),sha256=hashlib.sha256(data).hexdigest())
assert files==expected and set(directories)=={{'.','nested'}}
print(json.dumps(dict(files=files,directories=directories,parent=parent,total_bytes=total),sort_keys=True))
'''


def local_tree(root, expected):
    """Freeze every local entry and ancestor; no concurrent host writer admitted."""
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        s = path.lstat()
        rel = '.' if path == root else path.relative_to(root).as_posix()
        assert s.st_uid == os.geteuid() and not path.is_symlink()
        entry = dict(device=s.st_dev, inode=s.st_ino, mode=stat.S_IMODE(s.st_mode),
                     size=s.st_size, mtime_ns=s.st_mtime_ns,uid=s.st_uid,
                     type='file' if stat.S_ISREG(s.st_mode) else 'directory',nlink=s.st_nlink)
        if stat.S_ISREG(s.st_mode):
            assert s.st_nlink == 1
            data = path.read_bytes()
            entry['sha256'] = hashlib.sha256(data).hexdigest()
            assert {k:entry[k] for k in ('mode','size','sha256')} == expected[rel]
        else:
            assert stat.S_ISDIR(s.st_mode) and entry['mode'] == 0o700
            assert rel in ('.', 'nested')
        result[rel] = entry
    assert set(result) == {'.', 'nested', *expected}
    return result


@pytest.mark.source_upload
def test_captured_source_native_upload_before_execution(kube, adapter_gateway):
    native = adapter_gateway
    (kube.evidence/'source-upload-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},indent=2))
    kube.evidence.chmod(0o700)
    operation = uuid4()
    tree = kube.evidence/operation.hex
    repo = kube.evidence/'source.git'
    for directory in (tree, repo, kube.evidence/'objects', kube.evidence/'source-receipts', kube.evidence/'upload-receipts'):
        directory.mkdir(mode=0o700)
    (tree/'nested').mkdir(mode=0o700)
    env = {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1'}
    git = lambda *args: kube.native(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','protocol.allow=never','--git-dir',str(repo),*args],env=env).stdout.strip()
    summary = dict(outcome='failed', operation=str(operation), cli_invocations=0,
                   application_retries=0, native_internal_attempts='unknown',
                   upload_delivery='not_dispatched', upload_completion='unknown', repository_execution='unrun')
    fixture = {'.gitattributes':('100644',b'nested/binary filter=forbidden export-subst\n'),
               'nested/binary':('100644',bytes(range(256))*4096),
               "nested/space ' quote.txt":('100644',b'\x00\xffliteral $Format:%H$\r\n'),
               'nested/\u03b4.txt':('100644',b''),
               '-leading-executable':('100755',b'#!/bin/sh\nexit 73\n')}
    try:
        git('init','--bare','--quiet')
        for index,(path,(mode,data)) in enumerate(fixture.items()):
            raw = kube.evidence/('blob-'+str(index)); raw.write_bytes(data);raw.chmod(0o400)
            blob = git('hash-object','-w',str(raw))
            git('update-index','--add','--cacheinfo',mode,blob,path)
        tree_hash = git('write-tree')
        commit_file = kube.evidence/'commit.raw'
        commit_file.write_bytes(('tree '+tree_hash+'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nsource upload fixture\n').encode())
        commit = git('hash-object','-t','commit','-w',str(commit_file))
        marker = kube.evidence/'MUST-NOT-RUN'
        hook = repo/'hooks'/'post-checkout';hook.write_text('#!/bin/sh\ntouch '+str(marker)+'\n');hook.chmod(0o700)
        git('config','filter.forbidden.smudge','touch '+str(marker))
        pin = lambda path: Executable(path,hashlib.sha256(path.read_bytes()).hexdigest())
        with LocalArtifacts(kube.evidence/'objects',max_bytes=4*1024*1024) as store, GitSource(
                pin(Path('/usr/bin/git')),pin(Path('/usr/bin/prlimit')),
                store=store,limits=SourceLimits(),receipts=kube.evidence/'source-receipts') as source:
            snapshot = source.capture(repo,commit,operation)
            summary['snapshot'] = asdict(snapshot)
            manifest = (json.dumps(dict(version=1,commit=snapshot.commit,tree=snapshot.tree,files=[asdict(f) for f in snapshot.files]),sort_keys=True,separators=(',',':'))+'\n').encode()
            assert store.get(snapshot.manifest) == manifest
            assert {(f.path,f.mode) for f in snapshot.files} == {(p,m) for p,(m,_) in fixture.items()}
            expected = {}
            def object_identities():
                return {p.name:dict(device=p.lstat().st_dev,inode=p.lstat().st_ino,size=p.lstat().st_size,
                        mtime_ns=p.lstat().st_mtime_ns,uid=p.lstat().st_uid,mode=stat.S_IMODE(p.lstat().st_mode),
                        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (kube.evidence/'objects').iterdir()}
            object_root = (kube.evidence/'objects').lstat()
            objects_before = summary['authoritative_objects'] = object_identities()
            for file in snapshot.files:
                data = store.get(file.artifact)
                assert data == fixture[file.path][1]
                path = tree/file.path
                with path.open('xb') as stream:
                    stream.write(data);stream.flush();os.fchmod(stream.fileno(),0o500 if file.mode=='100755' else 0o400);os.fsync(stream.fileno())
                expected[file.path] = dict(mode=0o500 if file.mode=='100755' else 0o400,size=file.artifact.size,sha256=file.artifact.sha256)
            assert objects_before == object_identities()
        assert not marker.exists()
        original = local_tree(tree,expected);summary.update(host_tree=original,expected=expected)
        def host_parent():
            info = kube.evidence.lstat()
            assert stat.S_ISDIR(info.st_mode) and kube.evidence.resolve()==kube.evidence
            assert info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700
            return dict(device=info.st_dev,inode=info.st_ino,uid=info.st_uid,mode=stat.S_IMODE(info.st_mode))
        original_parent = summary['host_parent'] = host_parent()
        remote = '/tmp/'+operation.hex
        tls = TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
        with SandboxClient(native['endpoint'],tls=tls,timeout=60) as client, closing(ReceiptDirectory(kube.evidence/'upload-receipts')) as journal:
            sdk = SdkReceipts(client,kube.evidence)
            sandbox = summary['sandbox'] = {}
            try:
                with owned(kube,native,sdk,sandbox,'512Mi') as (name,pair):
                    before = execute(sdk,name,f"import os,stat,json;assert not os.path.lexists({remote!r});s=os.lstat('/tmp');assert stat.S_ISDIR(s.st_mode) and os.path.realpath('/tmp')=='/tmp';print(json.dumps(dict(device=s.st_dev,inode=s.st_ino,mode=stat.S_IMODE(s.st_mode),uid=s.st_uid)))")
                    assert before.exit_code==0 and before.stderr==''
                    parent = json.loads(before.stdout)
                    assert sdk.call('get',name,workspace='default').id==sandbox['sandbox_id']
                    journal.write(operation,'intent',dict(summary,remote=remote,parent=parent))
                    summary.update(upload_delivery='unknown',cli_invocations=1,remote=remote)
                    result = native['cli']('sandbox','upload','--no-git-ignore',name,str(tree),'/tmp',check=False)
                    summary['cli_exit'] = result.returncode
                    assert result.returncode==0, 'Unknown/failed upload is never replayed'
                    summary['upload_delivery'] = 'acknowledged'
                    assert local_tree(tree,expected)==original and host_parent()==original_parent and not marker.exists()
                    assert sdk.call('get',name,workspace='default').id==sandbox['sandbox_id']
                    verifier = VERIFY.format(root=remote,expected=expected,parent=parent)
                    observations = []
                    for _ in range(2):
                        observed = execute(sdk,name,verifier)
                        assert observed.exit_code==0 and observed.stderr=='' and len(observed.stdout.encode())<=4096
                        observations.append(json.loads(observed.stdout))
                    assert observations[0]==observations[1]
                    current_root = (kube.evidence/'objects').lstat()
                    assert (current_root.st_dev,current_root.st_ino)==(object_root.st_dev,object_root.st_ino)
                    with LocalArtifacts(kube.evidence/'objects',max_bytes=4*1024*1024) as reread:
                        assert reread.get(snapshot.manifest)==manifest
                        for file in snapshot.files:
                            assert reread.get(file.artifact)==fixture[file.path][1]
                    assert object_identities()==objects_before
                    summary['authoritative_objects_unchanged'] = True
                    summary.update(upload_completion='verified',admitted_tree=observations[0],independent_reread=observations[1])
                    # Actual verifier rejection before any repository consumer runs.
                    changed = execute(sdk,name,f"import os;p={remote!r}+'/nested/binary';os.chmod(p,0o600);f=open(p,'r+b');f.write(b'changed');f.close();os.chmod(p,0o400)")
                    assert changed.exit_code==0 and changed.stderr==''
                    refused = execute(sdk,name,verifier)
                    assert refused.exit_code!=0 and 'AssertionError' in refused.stderr
                    summary['corrupt_tree_refused'] = dict(exit=refused.exit_code,stderr=refused.stderr)
                    extra = execute(sdk,name,f"import os;os.symlink('/etc/passwd',{remote!r}+'/unexpected-link')")
                    assert extra.exit_code==0 and extra.stderr==''
                    refused = execute(sdk,name,verifier)
                    assert refused.exit_code!=0 and 'Too many levels of symbolic links' in refused.stderr
                    summary['unexpected_symlink_refused'] = dict(exit=refused.exit_code,stderr=refused.stderr)
                assert sandbox['cleanup_confirmed'] and sandbox['container_tasks_absent']
                summary['outcome'] = 'passed'
            finally:
                summary['sdk_method_calls'] = sdk.counter
                journal.write(operation,'result',summary)
    except BaseException as error:
        summary.update(outcome='failed',error_type=type(error).__name__,error_detail=str(error))
        raise
    finally:
        (kube.evidence/'source-upload.json').write_text(json.dumps(summary,indent=2))
