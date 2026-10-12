"""Fixed captured staging copy -> native execution -> immutable bounded output.

Infrastructure fixture only: no issue tests, patch application, fix verdict,
untrusted downloads, arbitrary source support or transient-mutation guarantee.
"""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.git_source import Executable, GitSource, SourceLimits, SourceCaptureError
from corsair.adapters.local_artifacts import LocalArtifacts, ArtifactStorageError
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution, serialized
from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.execution import ExecutionError, ExecutionLimits
from tests.qualification.gateway import gateway
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT
from tests.qualification.test_adapter_lifecycle import ObservedClient, AdapterHarness, adapter_gateway
from tests.qualification.test_execution_artifacts import READER, SOURCES as EXECUTION_SOURCES
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, execute, recovery_spec, PYTHON
from tests.qualification.test_source_upload import VERIFY, local_tree, SOURCES as UPLOAD_SOURCES

MAIN = b'''import hashlib,json,os,platform,sys
from pathlib import Path
assert sys.version_info[:2] == (3,12)
data=Path('input.json').read_bytes()
payload=json.loads(data)
assert payload['values'] == [1,2,3]
print(json.dumps(dict(value=sum(payload['values']),input_sha256=hashlib.sha256(data).hexdigest(),python=platform.python_version()),sort_keys=True))
os.write(2,b'source-execution-control\\n')
'''
INPUT = b'{"values":[1,2,3]}\n'
STDERR = b'source-execution-control\n'
SOURCES = sorted(set(EXECUTION_SOURCES + UPLOAD_SOURCES + [
    'tests/qualification/test_source_execution.py', 'tests/qualification/test_execution_artifacts.py',
    'tests/qualification/prepare_toolchains.py']))


def fixture_bytes(image, limits):
    """Reviewed fixed fixture, empty test-patch set and no external dependencies."""
    recipe = dict(command=[PYTHON, '-B', 'main.py'], workdir='nested', image=image,
                  python='3.12', dependencies={'stdlib': ['hashlib', 'json', 'os', 'pathlib', 'platform', 'sys'], 'external': []},
                  approved_test_patch_paths=[], test_patch=None, writable_outputs=[],
                  bytecode=False, limits=asdict(limits), input_sha256=hashlib.sha256(INPUT).hexdigest(),
                  main_sha256=hashlib.sha256(MAIN).hexdigest(),
                  policy_sha256=hashlib.sha256((ROOT/'policies/openshell/identity.yaml').read_bytes()).hexdigest())
    return {'.gitattributes': b'* -text\n', 'README.txt': b'Operator-owned source binding qualification fixture; no issue validation.\n',
            'nested/main.py': MAIN, 'nested/input.json': INPUT,
            'nested/recipe.json': (json.dumps(recipe, sort_keys=True, separators=(',', ':'))+'\n').encode()}


@pytest.mark.source_execution
def test_fixed_captured_staging_source_execution_output_binding(kube, adapter_gateway):
    native = adapter_gateway
    summary = dict(outcome='failed', scope='fixed infrastructure source/recipe binding only',
                   application_retries=0, native_internal_attempts='unknown', execution_attempts=0,
                   cli_invocations=0, upload_delivery='not_dispatched', upload_completion='unknown',
                   approved_test_patch_paths=[], test_patch=None, issue_test_discovery='unrun',
                   security_comparison='unrun', sandbox={}, storage_publication='not_started',
                   integrity_limit='Exact observations do not detect every transient modification.')
    operation, owner = uuid4(), uuid4()
    limits = ExecutionLimits(4096, 2, 20, 512*1024*1024)
    tree, repo = kube.evidence/operation.hex, kube.evidence/'source.git'
    source_objects, output_objects = kube.evidence/'source-objects', kube.evidence/'output-objects'
    receipts, source_receipts, composition = (kube.evidence/name for name in ('host-receipts', 'source-receipts', 'composition-receipts'))
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}
    git = lambda *args: kube.native(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never', '--git-dir', str(repo), *args], env=env).stdout.strip()
    def identities(root):
        return {p.name: dict(device=p.lstat().st_dev, inode=p.lstat().st_ino, size=p.lstat().st_size,
                            mtime_ns=p.lstat().st_mtime_ns, uid=p.lstat().st_uid, mode=stat.S_IMODE(p.lstat().st_mode),
                            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.iterdir()}
    def host_parent():
        s = kube.evidence.lstat()
        assert stat.S_ISDIR(s.st_mode) and kube.evidence.resolve() == kube.evidence
        assert s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o700
        return dict(device=s.st_dev, inode=s.st_ino, uid=s.st_uid, mode=stat.S_IMODE(s.st_mode))
    refs, source_refs = [], []
    try:
        (kube.evidence/'source-execution-hashes.json').write_text(json.dumps({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
        kube.evidence.chmod(0o700)
        for directory in (tree, repo, source_objects, output_objects, receipts, source_receipts, composition):
            directory.mkdir(mode=0o700)
        (tree/'nested').mkdir(mode=0o700)
        image = image_receipt('python')
        fixture = fixture_bytes(image['image'], limits)
        git('init', '--bare', '--quiet')
        for index, (path, data) in enumerate(fixture.items()):
            raw = kube.evidence/('blob-'+str(index)); raw.write_bytes(data); raw.chmod(0o400)
            git('update-index', '--add', '--cacheinfo', '100644', git('hash-object', '-w', str(raw)), path)
        commit_file = kube.evidence/'commit.raw'
        commit_file.write_bytes(('tree '+git('write-tree')+'\nauthor Fixture <fixture@invalid> 1 +0000\ncommitter Fixture <fixture@invalid> 1 +0000\n\nsource execution fixture\n').encode())
        commit = git('hash-object', '-t', 'commit', '-w', str(commit_file))
        pin = lambda path: Executable(path, hashlib.sha256(path.read_bytes()).hexdigest())
        with LocalArtifacts(source_objects, max_bytes=4*1024*1024) as store, GitSource(pin(Path('/usr/bin/git')), pin(Path('/usr/bin/prlimit')), store=store, limits=SourceLimits(), receipts=source_receipts) as source:
            snapshot = source.capture(repo, commit, operation)
            summary['snapshot'] = asdict(snapshot)
            manifest = (json.dumps(dict(version=1, commit=snapshot.commit, tree=snapshot.tree, files=[asdict(f) for f in snapshot.files]), sort_keys=True, separators=(',', ':'))+'\n').encode()
            assert store.get(snapshot.manifest) == manifest
            assert {(f.path, f.mode) for f in snapshot.files} == {(p, '100644') for p in fixture}
            expected = {}
            source_refs.append(asdict(snapshot.manifest))
            for file in snapshot.files:
                data = store.get(file.artifact); assert data == fixture[file.path]
                source_refs.append(asdict(file.artifact))
                with (tree/file.path).open('xb') as stream:
                    stream.write(data); stream.flush(); os.fchmod(stream.fileno(), 0o400); os.fsync(stream.fileno())
                expected[file.path] = dict(mode=0o400, size=len(data), sha256=file.artifact.sha256)
        original = summary['host_tree'] = local_tree(tree, expected)
        parent_before = summary['host_parent'] = host_parent()
        source_root = source_objects.stat(); source_identity = [source_root.st_dev, source_root.st_ino]
        source_before = summary['authoritative_sources'] = identities(source_objects)
        output_root = output_objects.stat(); output_identity = [output_root.st_dev, output_root.st_ino]
        remote = '/tmp/'+operation.hex
        tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
        connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
        with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client, closing(ReceiptDirectory(composition)) as journal:
            observed = ObservedClient(SdkReceipts(client, kube.evidence))
            with OpenShellLifecycle(observed, spec=recovery_spec(image['image'], '512Mi'), workspace='default', owner=owner, receipts=receipts) as lifecycle, OpenShellExecution(connection, workspace='default', owner=owner, workdir=remote+'/nested', limits=limits, receipts=receipts) as adapter, LocalArtifacts(output_objects, max_bytes=4096) as outputs:
                driver = AdapterHarness(lifecycle, observed); driver.creation = uuid4()
                try:
                    with owned(kube, native, driver, summary['sandbox'], '512Mi', name='cs-'+driver.creation.hex[:16]) as (name, pair):
                        before = execute(driver, name, f"import os,stat,json;assert not os.path.lexists({remote!r});s=os.lstat('/tmp');assert stat.S_ISDIR(s.st_mode) and os.path.realpath('/tmp')=='/tmp';print(json.dumps(dict(device=s.st_dev,inode=s.st_ino,mode=stat.S_IMODE(s.st_mode),uid=s.st_uid)))")
                        assert before.exit_code == 0 and before.stderr == ''
                        parent = json.loads(before.stdout)
                        journal.write(operation, 'intent', dict(snapshot=asdict(snapshot), expected=expected, remote=remote, parent=parent, sandbox_id=driver.handle.id))
                        summary.update(upload_delivery='unknown', cli_invocations=1)
                        upload = native['cli']('sandbox', 'upload', '--no-git-ignore', name, str(tree), '/tmp', check=False)
                        summary['cli_exit'] = upload.returncode
                        assert upload.returncode == 0, 'Unknown/failed upload is never replayed'
                        summary['upload_delivery'] = 'acknowledged'
                        assert local_tree(tree, expected) == original and host_parent() == parent_before
                        assert driver.call('get', name, workspace='default').id == driver.handle.id
                        verifier = VERIFY.format(root=remote, expected=expected, parent=parent)
                        def verify():
                            result = execute(driver, name, verifier)
                            assert result.exit_code == 0 and result.stderr == '' and len(result.stdout.encode()) <= 4096
                            return json.loads(result.stdout)
                        first = verify(); assert verify() == first
                        summary.update(upload_completion='verified', admitted_tree=first)
                        runtime = execute(driver, name, "import hashlib,json,platform,sys;from pathlib import Path;print(json.dumps(dict(python=platform.python_version(),executable=sys.executable,sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()),sort_keys=True))")
                        assert runtime.exit_code == 0 and runtime.stderr == ''
                        runtime_identity = json.loads(runtime.stdout)
                        assert runtime_identity['python'].startswith('3.12.') and runtime_identity['executable'] == PYTHON
                        command = (PYTHON, '-B', 'main.py')
                        binding = dict(snapshot=asdict(snapshot), source_refs=source_refs, recipe_sha256=expected['nested/recipe.json']['sha256'],
                                       runtime=runtime_identity, image=image, policy_sha256=hashlib.sha256((ROOT/'policies/openshell/identity.yaml').read_bytes()).hexdigest(),
                                       effective_policy=summary['sandbox']['policy_observations'][-1]['full'],
                                       command=command, command_sha256=hashlib.sha256(b'\x00'.join(a.encode() for a in command)).hexdigest(),
                                       workdir=remote+'/nested', limits=asdict(limits), sandbox_id=driver.handle.id,
                                       approved_test_patch_paths=[], test_patch=None, expected=expected)
                        binding_bytes = (json.dumps(binding, sort_keys=True, separators=(',', ':'))+'\n').encode()
                        assert identities(source_objects) == source_before
                        with LocalArtifacts(source_objects, max_bytes=4*1024*1024) as store:
                            bound = store.put(binding_bytes); source_refs.append(asdict(bound)); assert store.get(bound) == binding_bytes
                        assert all(identities(source_objects)[key] == value for key, value in source_before.items())
                        source_before = summary['authoritative_sources'] = identities(source_objects)
                        summary.update(binding_reference=asdict(bound), runtime=runtime_identity)
                        execution = uuid4(); summary['execution_operation'] = str(execution)
                        journal.write(execution, 'intent', dict(binding_reference=asdict(bound), source_observation=verify()))
                        summary['execution_attempts'] = 1
                        result = adapter.execute(driver.handle, command, execution)
                        summary['execution'] = serialized(result)
                        intent = json.loads((receipts/f'{execution}.intent.json').read_text())
                        assert intent['command_sha256'] == binding['command_sha256'] and intent['workdir'] == binding['workdir']
                        assert intent['limits'] == binding['limits'] and intent['handle']['id'] == binding['sandbox_id']
                        assert json.loads((receipts/f'{execution}.result.json').read_text()) == json.loads(json.dumps(serialized(result)))
                        expected_stdout = (json.dumps(dict(value=6, input_sha256=hashlib.sha256(INPUT).hexdigest(), python=runtime_identity['python']), sort_keys=True)+'\n').encode()
                        assert result.delivery == 'acknowledged' and result.completion == 'terminal_observed' and result.native_exit == 0 and result.worker_cleanup == 'confirmed'
                        assert (result.stdout, result.stderr) == (expected_stdout, STDERR)
                        assert len(result.stdout)+len(result.stderr) <= limits.output_bytes
                        summary['post_execution_tree'] = verify(); assert summary['post_execution_tree'] == first
                        assert local_tree(tree, expected) == original and host_parent() == parent_before
                        assert identities(source_objects) == source_before
                        summary['storage_publication'] = 'in_progress'
                        for data in (result.stdout, result.stderr):
                            ref = outputs.put(data, expected_sha256=hashlib.sha256(data).hexdigest()); refs.append(asdict(ref))
                            summary['output_references'] = list(refs)
                            assert outputs.get(ref) == data and stat.S_IMODE((output_objects/ref.sha256).stat().st_mode) == 0o400
                        summary['storage_publication'] = 'admitted'
                        journal.write(execution, 'result', dict(binding_reference=asdict(bound), execution=serialized(result),
                                                              output_references=refs, post_execution_tree=summary['post_execution_tree'],
                                                              source_binding='admitted'))
                        intents = sorted(p.name for p in receipts.glob('*.intent.json'))
                        changed = execute(driver, name, f"import os;p={remote!r}+'/nested/main.py';os.chmod(p,0o600);f=open(p,'r+b');f.write(b'#changed');f.close();os.chmod(p,0o400)")
                        assert changed.exit_code == 0 and changed.stderr == ''
                        refused = execute(driver, name, verifier)
                        assert refused.exit_code != 0 and 'AssertionError' in refused.stderr
                        assert sorted(p.name for p in receipts.glob('*.intent.json')) == intents and summary['execution_attempts'] == 1
                        summary['changed_source_refused_before_second_dispatch'] = dict(exit=refused.exit_code, stderr=refused.stderr, execution_attempts=1, execution_intents=[str(execution)], observed_fixture_mutation='operator diagnostic after completed unchanged-source execution')
                    assert summary['sandbox']['cleanup_confirmed'] and summary['sandbox']['container_tasks_absent']
                finally:
                    summary['sdk_method_calls'] = observed.sdk.counter
                    summary['lifecycle_operations'] = driver.operations
        for label, root, identity, references in (('source', source_objects, source_identity, source_refs), ('output', output_objects, output_identity, refs)):
            reader_code = READER.replace('max_bytes=4096', 'max_bytes=4194304') if label == 'source' else READER
            reader = kube.native([sys.executable, '-c', reader_code, str(ROOT/'src'), str(root), json.dumps(identity), json.dumps(references)], timeout=20)
            fresh = json.loads(reader.stdout)
            assert fresh == dict(root_identity=identity, references=references)
            summary[label+'_fresh_reader_after_cleanup'] = fresh
        assert identities(source_objects) == source_before
        summary['authoritative_sources_unchanged'] = True
        summary['outcome'] = 'passed'
    except ExecutionError as error:
        summary.update(execution=serialized(error.receipt), error_type=type(error).__name__, error_detail=str(error))
        raise
    except SourceCaptureError as error:
        summary.update(source_failure=error.receipt, error_type=type(error).__name__, error_detail=str(error))
        raise
    except ArtifactStorageError as error:
        summary['artifact_failure'] = dict(error_type=type(error).__name__, detail=str(error),
                                          reference=asdict(error.reference) if error.reference else None,
                                          publication=error.publication, temporary_cleanup=error.temporary_cleanup,
                                          temporary_name=error.temporary_name, temporary_identity=error.temporary_identity)
        raise
    except BaseException as error:
        summary.update(outcome='failed', error_type=type(error).__name__, error_detail=str(error))
        raise
    finally:
        try:
            if composition.exists():
                with closing(ReceiptDirectory(composition)) as journal:
                    journal.write(operation, 'result', summary)
            else:
                summary['result_storage_error'] = 'Composition receipt directory was not initialized'
        except BaseException as error:
            summary.update(outcome='failed', result_storage_error=f'{type(error).__name__}: {error}')
            raise
        finally:
            (kube.evidence/'source-execution.json').write_text(json.dumps(summary, indent=2))
