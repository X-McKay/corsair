"""Fixed untrusted file -> native raw stdout -> immutable output qualification.

No archive, metadata transport, production API, replay or atomic snapshot claim.
"""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

import pytest
from google.protobuf.json_format import MessageToDict
from openshell import SandboxClient, TlsConfig

from corsair.adapters.local_artifacts import ArtifactStorageError, LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.ports.sandbox import LifecycleLimits
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution, serialized
from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.execution import ExecutionError, ExecutionLimits
from tests.qualification.gateway import gateway
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.test_adapter_lifecycle import ObservedClient, AdapterHarness, adapter_gateway
from tests.qualification.test_execution_artifacts import READER, SOURCES as OUTPUT_SOURCES
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, recovery_spec, PYTHON

HOSTILE = "-report ' $(id); \u03b4.bin"
POSITIVE = {'empty': b'', 'binary': bytes(range(256))*4,
            'exact-cap': bytes(range(256))*16, HOSTILE: b'\x00\xffliteral report\r\n'}
SOURCES = sorted(set(OUTPUT_SOURCES + ['tests/qualification/test_untrusted_file.py',
    'tests/qualification/test_execution_artifacts.py', 'tests/qualification/prepare_toolchains.py',
    'deploy/qualification/toolchains/python/Dockerfile', 'Makefile']))

# Trusted fixed recipe. O_PATH inspects special objects before opening for I/O.
# No threads, subprocesses or descriptor reuse occur while the original fd lives.
READ_FILE = '''import os,stat,sys
fds=[]
def require(value):
 if not value:raise ValueError('file admission refused')
def anchor(s):return (s.st_dev,s.st_ino,s.st_uid,stat.S_IMODE(s.st_mode))
def stamp(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def keep(fd):fds.append(fd);return fd
try:
 require((sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode)==(1,1,1))
 require('' not in sys.path and root not in sys.path)
 top=keep(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW))
 tmp=keep(os.open('tmp',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=top))
 require(anchor(os.fstat(tmp))==parent)
 directory=keep(os.open(root.rsplit('/',1)[1],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=tmp))
 require(anchor(os.fstat(directory))==identity and identity[2]==os.geteuid() and identity[3]==448)
 path=keep(os.open(name,os.O_PATH|os.O_NOFOLLOW,dir_fd=directory))
 before=os.fstat(path)
 require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.geteuid())
 require(0<=before.st_size<=4096 and stamp(before)==entry)
 # This intentional procfd magiclink refers to the still-open admitted inode.
 stream=keep(os.open('/proc/self/fd/'+str(path),os.O_RDONLY|os.O_NONBLOCK))
 require(stamp(os.fstat(stream))==entry)
 data=b''
 while len(data)<=4096:
  chunk=os.read(stream,4097-len(data))
  if not chunk:break
  data+=chunk
 require(len(data)<=4096 and len(data)==before.st_size)
 require(stamp(os.fstat(stream))==entry and stamp(os.fstat(path))==entry)
 require(stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==entry)
 require(anchor(os.stat(root.rsplit('/',1)[1],dir_fd=tmp,follow_symlinks=False))==identity)
 require(anchor(os.stat('tmp',dir_fd=top,follow_symlinks=False))==parent)
 offset=0
 while offset<len(data):offset+=os.write(1,data[offset:])
except ValueError:sys.exit(65)
except OSError as error:
 os.write(2,('file-open:'+str(error.errno)+'\\n').encode());sys.exit(66)
finally:
 for fd in reversed(fds):os.close(fd)
'''


def collector_command(root, name, identity, parent, entry):
    """Only this fixed /tmp UUID root and one literal basename are selectable."""
    if (type(root) is not str or not re.fullmatch('/tmp/[0-9a-f]{32}', root)
            or type(name) is not str or not name or name in ('.', '..') or '/' in name
            or '\x00' in name or len(name.encode()) > 255):
        raise ValueError('Fixed UUID root and literal basename required before dispatch')
    bindings = f'root={root!r};name={name!r};identity={tuple(identity)!r};parent={tuple(parent)!r};entry={tuple(entry)!r}\n'
    return (PYTHON, '-I', '-S', '-B', '-c', bindings+READ_FILE)


PRODUCE = '''import hashlib,json,os,platform,stat,sys
from pathlib import Path
assert (sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode)==(1,1,1)
allowed={'OPENSHELL_SANDBOX','HOME','USER','PATH','TERM','SHELL','PWD','OLDPWD','SHLVL','_','LC_CTYPE','NODE_EXTRA_CA_CERTS','DENO_CERT','SSL_CERT_FILE','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','GIT_SSL_CAINFO'}
assert set(os.environ)<=allowed, sorted(set(os.environ)-allowed)
def anchor(s):return [s.st_dev,s.st_ino,s.st_uid,stat.S_IMODE(s.st_mode)]
def stamp(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
os.mkdir(root,0o700)
files={'empty':b'','binary':bytes(range(256))*4,'exact-cap':bytes(range(256))*16,hostile:b'\\x00\\xffliteral report\\r\\n','oversize':b'X'*4097,'hard-original':b'hard','replaced-entry':b'original'}
for name,data in files.items():Path(root,name).write_bytes(data)
with open(root+'/sparse','wb') as stream:stream.truncate(1024*1024*1024)
os.mkdir(root+'/directory',0o700);os.mkfifo(root+'/fifo',0o600)
os.symlink('/dev/null',root+'/symlink');os.link(root+'/hard-original',root+'/hardlink')
for name in ('os.py','stat.py','json.py','sitecustomize.py'):
 Path(root,name).write_text("raise RuntimeError('CWD IMPORT TRAP')\\n")
os.symlink(root,alias)
os.mkdir(replaced,0o700);Path(replaced,'empty').write_bytes(b'')
record=dict(parent=anchor(os.lstat('/tmp')),root=anchor(os.lstat(root)),
 entries={name:stamp(os.lstat(root+'/'+name)) for name in (*files,'sparse','directory','fifo','symlink','hardlink')},
 replaced_root=anchor(os.lstat(replaced)),replaced_entry=stamp(os.lstat(replaced+'/empty')))
os.rename(root+'/replaced-entry',root+'/replaced-entry.old');Path(root,'replaced-entry').write_bytes(b'replacement')
os.rename(replaced,retired);os.mkdir(replaced,0o700);Path(replaced,'empty').write_bytes(b'')
record['runtime']=dict(python=platform.python_version(),executable=sys.executable,sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),uid=os.geteuid(),environment_names=sorted(os.environ),flags=[sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode])
print(json.dumps(record,sort_keys=True))
'''


RUNTIME = """import hashlib,json,os,platform,sys
from pathlib import Path
allowed={'OPENSHELL_SANDBOX','HOME','USER','PATH','TERM','SHELL','PWD','OLDPWD','SHLVL','_','LC_CTYPE','NODE_EXTRA_CA_CERTS','DENO_CERT','SSL_CERT_FILE','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','GIT_SSL_CAINFO'}
assert set(os.environ)<=allowed, sorted(set(os.environ)-allowed)
assert (sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode)==(1,1,1) and '' not in sys.path
assert json.__file__.startswith('/usr/local/lib/python3.12/') and hashlib.__file__.startswith('/usr/local/lib/python3.12/')
print(json.dumps(dict(python=platform.python_version(),executable=sys.executable,sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),uid=os.geteuid(),environment_names=sorted(os.environ),flags=[sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode],modules={'json':json.__file__,'hashlib':hashlib.__file__}),sort_keys=True))
"""

def producer_code(root, alias, replaced, retired):
    return f'root={root!r};alias={alias!r};replaced={replaced!r};retired={retired!r};hostile={HOSTILE!r}\n'+PRODUCE


@pytest.mark.untrusted_file
def test_fixed_generated_file_bounded_output_admission(kube, adapter_gateway):
    native = adapter_gateway
    operation, owner = uuid4(), uuid4()
    limits = ExecutionLimits(4096, 2, 20, 512*1024*1024)
    roots = ['/tmp/'+uuid4().hex for _ in range(4)]
    remote, alias, replaced, retired = roots
    summary = dict(outcome='failed', scope='fixed opaque file bytes only; no atomic snapshot',
                   application_retries=0, execution_attempts=0, native_internal_attempts='unknown',
                   cases=[], host_selection_refusals=[], sandbox={}, output_references=[])
    receipts, objects, composition, corrupt = (kube.evidence/name for name in ('host-receipts', 'output-objects', 'composition-receipts', 'corruption-fixture'))
    refs = []
    try:
        kube.evidence.chmod(0o700)
        for directory in (receipts, objects, composition, corrupt):directory.mkdir(mode=0o700)
        (kube.evidence/'untrusted-file-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
        identity = objects.stat(); output_identity = [identity.st_dev, identity.st_ino]
        image = image_receipt('python'); spec = recovery_spec(image['image'], '512Mi')
        assert not spec.environment and not spec.template.environment and not spec.providers
        summary.update(native_spec=MessageToDict(spec, preserving_proto_field_name=True), image=image, limits=asdict(limits), roots=roots)
        tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
        connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
        with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client, closing(ReceiptDirectory(composition)) as journal:
            journal.write(operation, 'intent', dict(scope=summary['scope'], roots=roots, limits=asdict(limits), native_spec=summary['native_spec']))
            observed = ObservedClient(SdkReceipts(client, kube.evidence))
            with OpenShellLifecycle(observed, spec=spec, workspace='default', owner=owner, receipts=receipts, limits=LifecycleLimits(ready_seconds=300, delete_seconds=60)) as lifecycle, OpenShellExecution(connection, workspace='default', owner=owner, workdir=remote, limits=limits, receipts=receipts) as adapter, LocalArtifacts(objects, max_bytes=4096) as store:
                driver = AdapterHarness(lifecycle, observed); driver.creation = uuid4()
                try:
                    with owned(kube, native, driver, summary['sandbox'], '512Mi', name='cs-'+driver.creation.hex[:16]) as (name, pair):
                        produced = driver.call('exec', name, [PYTHON, '-I', '-S', '-B', '-c', producer_code(*roots)], workspace='default', workdir='/tmp', no_login_shell=True, timeout_seconds=20)
                        assert produced.exit_code == 0 and produced.stderr == '' and len(produced.stdout.encode()) <= 4096
                        fixture = summary['fixture'] = json.loads(produced.stdout)
                        assert fixture['runtime']['uid'] == 10001 and fixture['runtime']['executable'] == PYTHON
                        assert fixture['runtime']['python'] == '3.12.15' and fixture['runtime']['flags'] == [1,1,1]
                        assert fixture['runtime']['sha256'] == '4dbf3143240288fb2170257ffaa7bd030cdda5d2703d1f5f30b627042267e2e3'
                        trap = driver.call('exec', name, [PYTHON, '-I', '-S', '-B', '-c', RUNTIME], workspace='default', workdir=remote, no_login_shell=True, timeout_seconds=20)
                        assert trap.exit_code == 0 and trap.stderr == '' and len(trap.stdout.encode()) <= 4096
                        runtime = summary['runtime'] = json.loads(trap.stdout)
                        assert {key:runtime[key] for key in fixture['runtime']} == fixture['runtime']
                        summary['cwd_module_trap_refused'] = True
                        unchanged = sorted(p.name for p in receipts.glob('*.intent.json')); calls = observed.sdk.counter
                        for invalid in ('', '.', '..', '../binary', 'nested/binary', '/etc/passwd', 'bad\x00name'):
                            with pytest.raises(ValueError):collector_command(remote, invalid, fixture['root'], fixture['parent'], fixture['entries']['binary'])
                            summary['host_selection_refusals'].append(repr(invalid))
                        assert unchanged == sorted(p.name for p in receipts.glob('*.intent.json')) and calls == observed.sdk.counter
                        rows = [(label, remote, label, fixture['root'], fixture['entries'][label], data, 0, b'') for label,data in POSITIVE.items()]
                        rows += [(label, remote, label, fixture['root'], fixture['entries'][label], None, 65, b'') for label in ('oversize','sparse','directory','fifo','symlink','hardlink','replaced-entry')]
                        wrong = list(fixture['root']); wrong[1] += 1
                        rows += [('wrong-root',remote,'empty',wrong,fixture['entries']['empty'],None,65,b''),
                                 ('root-symlink',alias,'empty',fixture['root'],fixture['entries']['empty'],None,66,b'file-open:20\n'),
                                 ('replaced-root',replaced,'empty',fixture['replaced_root'],fixture['replaced_entry'],None,65,b'')]
                        for label, root, selected, root_stamp, entry, expected, exit_code, stderr in rows:
                            op = uuid4(); command = collector_command(root, selected, root_stamp, fixture['parent'], entry)
                            case = dict(label=label, operation=str(op), outcome='failed', artifact_admitted=False, expected_exit=exit_code,
                                        expected_stdout_sha256=hashlib.sha256(expected).hexdigest() if expected is not None else None, expected_stdout_bytes=len(expected) if expected is not None else 0)
                            summary['cases'].append(case); prior_objects = sorted(p.name for p in objects.iterdir())
                            binding = dict(root=root, basename=selected, root_identity=root_stamp, parent_identity=fixture['parent'], entry=entry,
                                           command_sha256=hashlib.sha256(b'\x00'.join(a.encode() for a in command)).hexdigest(),
                                           workdir=remote, limits=asdict(limits), image=image, runtime=runtime,
                                           sandbox_id=driver.handle.id, policy=summary['sandbox']['policy_observations'][-1]['full'])
                            journal.write(op, 'intent', binding)
                            try:
                                summary['execution_attempts'] += 1
                                result = adapter.execute(driver.handle, command, op); case['execution'] = serialized(result)
                                assert result.delivery == 'acknowledged' and result.completion == 'terminal_observed'
                                assert result.native_exit == exit_code and result.worker_cleanup == 'confirmed' and result.worker_exit == 0
                                assert result.native_calls == ('get','exec_stream') and result.worker_limit_applied and result.worker_maxrss_kib is not None
                                assert result.stderr == stderr and len(result.stdout)+len(result.stderr) <= 4096
                                assert json.loads((receipts/f'{op}.result.json').read_text()) == json.loads(json.dumps(serialized(result)))
                                intent = json.loads((receipts/f'{op}.intent.json').read_text())
                                assert intent['command_sha256'] == binding['command_sha256'] and intent['workdir'] == remote and intent['limits'] == asdict(limits)
                                if expected is not None:
                                    assert result.stdout == expected
                                    ref = store.put(result.stdout, expected_sha256=hashlib.sha256(expected).hexdigest())
                                    assert store.get(ref) == expected and stat.S_IMODE((objects/ref.sha256).stat().st_mode) == 0o400
                                    refs.append(asdict(ref)); summary['output_references'] = list(refs); case.update(artifact_admitted=True, reference=asdict(ref))
                                else:
                                    assert result.stdout == b'' and sorted(p.name for p in objects.iterdir()) == prior_objects
                                case['outcome'] = 'passed'
                            except ExecutionError as error:
                                case['execution'] = serialized(error.receipt); raise
                            finally:journal.write(op, 'result', case)
                        summary['output_references'] = refs
                    assert summary['sandbox']['cleanup_confirmed'] and summary['sandbox']['container_tasks_absent']
                finally:
                    summary['sdk_method_calls'] = observed.sdk.counter; summary['lifecycle_operations'] = driver.operations
        reader = kube.native([sys.executable, '-c', READER, str(ROOT/'src'), str(objects), json.dumps(output_identity), json.dumps(refs)], timeout=20)
        summary['fresh_reader_after_cleanup'] = json.loads(reader.stdout)
        assert summary['fresh_reader_after_cleanup'] == dict(root_identity=output_identity, references=refs)
        with LocalArtifacts(corrupt, max_bytes=4096) as poisoned:
            ref = poisoned.put(POSITIVE['binary']); path = corrupt/ref.sha256; original = path.stat()
            summary['corruption_fixture_identity'] = dict(path=str(path), device=original.st_dev, inode=original.st_ino, uid=original.st_uid)
            path.chmod(0o600); path.write_bytes(b'X'+POSITIVE['binary'][1:]); path.chmod(0o400)
            try:
                with pytest.raises(ArtifactStorageError):poisoned.get(ref)
                with pytest.raises(ArtifactStorageError):poisoned.put(POSITIVE['binary'])
                summary['corrupt_output_refused'] = True
            finally:
                current = path.lstat(); assert (current.st_dev,current.st_ino) == (original.st_dev,original.st_ino), 'Corruption fixture identity changed; refusing cleanup'
                path.unlink(); assert not path.exists(); summary['corruption_fixture_cleanup'] = 'confirmed'
        assert summary['execution_attempts'] == 14 and len(refs) == 4
        summary['outcome'] = 'passed'
    except ExecutionError as error:
        summary.update(error_type=type(error).__name__, execution_failure=serialized(error.receipt)); raise
    except ArtifactStorageError as error:
        summary['artifact_failure'] = dict(error_type=type(error).__name__, detail=str(error), reference=asdict(error.reference) if error.reference else None,
                                          publication=error.publication, temporary_cleanup=error.temporary_cleanup, temporary_name=error.temporary_name, temporary_identity=error.temporary_identity); raise
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error_detail=str(error)); raise
    finally:
        try:
            with closing(ReceiptDirectory(composition)) as journal:journal.write(operation, 'result', summary)
        except BaseException as error:
            summary.update(outcome='failed', result_storage_error=f'{type(error).__name__}: {error}'); raise
        finally:(kube.evidence/'untrusted-file.json').write_text(json.dumps(summary, indent=2))
