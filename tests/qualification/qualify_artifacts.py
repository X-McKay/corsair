"""Explicit actual-host qualification; never substitutes for OpenShell admission."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from corsair.adapters.git_source import Executable, GitSource, SourceCaptureError, SourceLimits
from corsair.adapters.local_artifacts import LocalArtifacts, ArtifactStorageError
from corsair.ports.artifacts import ArtifactRef

ROOT=Path(__file__).resolve().parents[2]
SOURCES=['src/corsair/ports/artifacts.py','src/corsair/adapters/local_artifacts.py','src/corsair/adapters/git_source.py',
         'src/corsair/adapters/receipts.py','tests/unit/test_artifacts.py','tests/qualification/qualify_artifacts.py',
         'Makefile','pyproject.toml','uv.lock']


def private(path):
    path.mkdir(mode=0o700)
    return path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--configuration',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True)
    args=parser.parse_args(); evidence=args.evidence_dir.resolve()
    if ROOT/'.runs' not in evidence.parents or not evidence.is_dir() or any(evidence.iterdir()):
        raise ValueError('New empty ignored evidence directory required')
    config=json.loads(args.configuration.read_text()); frozen=json.loads(args.source_manifest.read_text())
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}
    if any(frozen.get(p)!=digest for p,digest in hashes.items()): raise ValueError('Live source differs from frozen manifest')
    git=Executable(Path(config['git']['path']),config['git']['sha256']);prlimit=Executable(Path(config['prlimit']['path']),config['prlimit']['sha256'])
    git.verify();prlimit.verify()
    limits=SourceLimits(**config['limits']); started=time.monotonic()
    report=dict(outcome='failed',source_hashes=hashes,configuration=config,host=dict(kernel=os.uname().release,machine=os.uname().machine),
                fixture_native_calls=[],operations=[],cleanup='unconfirmed',artifact_retention='private evidence; intentionally retained',
                storage_power_loss_concurrency_sandbox_integration='unrun')
    fixture=private(evidence/'fixture');identity=fixture.stat();repo=private(fixture/'source.git')
    store_root=private(evidence/'objects');receipts=private(evidence/'receipts')
    def native(argv,*,input=None,env=None):
        before=time.monotonic()
        process=subprocess.Popen(argv,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        try:
            out,err=process.communicate(input=input,timeout=20)
        except BaseException:
            process.kill();out,err=process.communicate();raise
        finally:
            report['fixture_native_calls'].append(dict(argv=argv,pid=process.pid,exit=process.returncode,reaped=process.returncode is not None,elapsed_seconds=time.monotonic()-before))
        if process.returncode!=0: raise RuntimeError(f'Fixture native exit {process.returncode}: {err!r}')
        return out
    def command(*parts,input=None):
        return native([str(git.path),'-c','core.hooksPath=/dev/null','-C',str(repo),*parts],input=input,
                      env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
    def blob(data):return command('hash-object','-w','--stdin',input=data).strip()
    def tree(entries):return command('mktree','-z',input=b''.join(entries)).strip()
    def commit(tree_id):
        raw=b'tree '+tree_id+b'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nqualification\n'
        return command('hash-object','-t','commit','-w','--stdin',input=raw).strip().decode()
    try:
        report['git_version']=native([str(git.path),'--version']).decode().strip()
        report['prlimit_version']=native([str(prlimit.path),'--version']).decode().strip()
        report['filesystem']=native(['/usr/bin/stat','-f','--format=%T',str(store_root)]).decode().strip()
        command('init','--bare','--quiet')
        binary=b'\x00\xffexact-source\r\n$Format:%H$\n'
        nested=tree([b'100755 blob '+blob(binary)+b'\tpayload\0'])
        attrs=b'data/payload filter=qualification export-subst\n'
        original=commit(tree([b'040000 tree '+nested+b'\tdata\0',b'100644 blob '+blob(attrs)+b'\t.gitattributes\0']))
        symlink=commit(tree([b'120000 blob '+blob(b'/etc/passwd')+b'\tlink\0']))
        oversized=commit(tree([b'100644 blob '+blob(b'X'*(limits.max_file_bytes+1))+b'\toversized\0']))
        marker=fixture/'MUST-NOT-RUN'
        hook=repo/'hooks/post-checkout';hook.write_text('#!/bin/sh\ntouch '+str(marker)+'\n');hook.chmod(0o700)
        command('config','filter.qualification.smudge','touch '+str(marker))
        (repo/'dirty-worktree-file').write_bytes(b'not a committed blob')
        with LocalArtifacts(store_root,max_bytes=4*1024*1024) as store, GitSource(git,prlimit,store=store,limits=limits,receipts=receipts) as source:
            snapshots=[]
            for label,revision in [('capture',original),('repeat',original),('symlink_refusal',symlink),('byte_refusal',oversized)]:
                op=uuid4();report['operations'].append(dict(label=label,operation=str(op),commit=revision))
                if label.endswith('refusal'):
                    try:source.capture(repo,revision,op)
                    except SourceCaptureError as error:
                        assert error.receipt['outcome']=='failed' and error.receipt['layer']=='source_admission'
                        assert not error.receipt['admitted_artifacts']
                    else:raise AssertionError('Unsafe source admitted')
                else:
                    snapshot=source.capture(repo,revision,op);snapshots.append(snapshot)
                    assert [(f.path,f.mode) for f in snapshot.files]==[('.gitattributes','100644'),('data/payload','100755')]
                    assert store.get(snapshot.files[1].artifact)==binary
                    if label=='capture': identities={p.name:p.stat().st_ino for p in store_root.iterdir()}
                    else:assert identities=={p.name:p.stat().st_ino for p in store_root.iterdir()}
            assert snapshots[0]==snapshots[1] and not marker.exists()
            report['snapshot']=asdict(snapshots[0]);report['object_inodes']=identities
            # Corruption refusal is actual storage validation, not a disk-fault test.
            corrupted=store.put(b'CORRUPT-ME');path=store_root/corrupted.sha256;original_inode=path.stat().st_ino
            path.chmod(0o600);path.write_bytes(b'BAD-BYTES!');path.chmod(0o400)
            try:store.get(corrupted)
            except ArtifactStorageError as error:report['corruption_refusal']=dict(detail=str(error),publication=error.publication)
            else:raise AssertionError('Corrupted artifact accepted')
            try:store.put(b'CORRUPT-ME')
            except ArtifactStorageError as error:assert error.temporary_cleanup=='confirmed'
            else:raise AssertionError('Poisoned identity overwritten')
            assert path.stat().st_ino==original_inode
            path.unlink();os.fsync(store._fd)
            report['corruption_cleanup']=dict(inode=original_inode,confirmed=not path.exists())
        snapshot_path=evidence/'snapshot.json';snapshot_path.write_text(json.dumps(report['snapshot'],indent=2))
        reader='''import hashlib,json,sys
from pathlib import Path
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.artifacts import ArtifactRef
s=json.loads(Path(sys.argv[2]).read_text())
with LocalArtifacts(Path(sys.argv[1]),max_bytes=4*1024*1024) as store:
 manifest=json.loads(store.get(ArtifactRef(**s['manifest'])))
 assert manifest['files']==s['files'] and manifest['commit']==s['commit']
 for f in s['files']:assert hashlib.sha256(store.get(ArtifactRef(**f['artifact']))).hexdigest()==f['artifact']['sha256']
print(json.dumps({'objects_verified':len(s['files'])+1,'manifest':s['manifest']}))
'''
        report['fresh_reader']=json.loads(native([sys.executable,'-c',reader,str(store_root),str(snapshot_path)],
                env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(ROOT/'src')}))
        probe='''import json,resource
limits={'as':resource.getrlimit(resource.RLIMIT_AS),'cpu':resource.getrlimit(resource.RLIMIT_CPU)}
try:bytearray(1024*1024*1024)
except MemoryError:limits['excess_allocation']='refused'
else:raise RuntimeError('Hard host memory cap absent')
print(json.dumps(limits))
'''
        report['native_resource_probe']=json.loads(native([str(prlimit.path),f'--as={limits.memory_bytes}:{limits.memory_bytes}',
                f'--cpu={limits.cpu_seconds}:{limits.cpu_seconds}','--',sys.executable,'-c',probe],env={'PATH':'/usr/bin:/bin'}))
        assert report['native_resource_probe']['as']==[limits.memory_bytes]*2
        assert report['native_resource_probe']['cpu']==[limits.cpu_seconds]*2
        assert not list(store_root.glob('*.partial'))
        for operation in report['operations']:
            receipt=json.loads((receipts/(operation['operation']+'.result.json')).read_text())
            assert all(c['reaped'] for c in receipt['native_calls'])
            operation.update(outcome=receipt['outcome'],elapsed_seconds=receipt['elapsed_seconds'],native_calls=len(receipt['native_calls']))
        report['no_hook_marker']=True;report['outcome']='passed'
    except BaseException as error:
        report['error']=dict(type=type(error).__name__,detail=str(error));raise
    finally:
        try:
            current=fixture.stat()
            if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino):raise RuntimeError('Fixture root identity changed; cleanup refused')
            report['fixture_identity']=dict(device=identity.st_dev,inode=identity.st_ino)
            shutil.rmtree(fixture)
            report['cleanup']='confirmed' if not fixture.exists() else 'unconfirmed'
        finally:
            report['elapsed_seconds']=time.monotonic()-started
            (evidence/'qualification.json').write_text(json.dumps(report,indent=2))
    print('Actual host artifact/source qualification passed; fixture cleanup '+report['cleanup'])


if __name__=='__main__':main()
