"""One documented trusted native upload; no application adapter or downloads."""
from contextlib import closing
import hashlib
import json
import os
import stat
from uuid import uuid4

import pytest
from openshell import SandboxClient, TlsConfig

from corsair.adapters.receipts import ReceiptDirectory
from tests.qualification.gateway import gateway
from tests.qualification.test_adapter_lifecycle import adapter_gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, execute
from tests.qualification.support import ROOT

SOURCES = ['tests/qualification/test_native_upload.py', 'tests/qualification/test_adapter_lifecycle.py',
           'tests/qualification/test_lifecycle.py', 'tests/qualification/test_recovery.py',
           'tests/qualification/test_policy.py', 'tests/qualification/gateway.py',
           'tests/qualification/support.py', 'src/corsair/adapters/receipts.py',
           'deploy/runtime-lock.yaml', 'policies/openshell/identity.yaml', 'pyproject.toml', 'uv.lock']


def source_identity(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o400
        return {'device': info.st_dev, 'inode': info.st_ino, 'size': info.st_size,
                'mtime_ns': info.st_mtime_ns, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def file_observation(sdk, name, remote):
    result = execute(sdk, name, f'''import hashlib,json,os,stat
p={remote!r}
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
 s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
 data=f.read(1048577);assert len(data)<=1048576
print(json.dumps(dict(device=s.st_dev,inode=s.st_ino,size=s.st_size,mode=stat.S_IMODE(s.st_mode),sha256=hashlib.sha256(data).hexdigest())))''')
    assert result.exit_code == 0 and result.stderr == ''
    return json.loads(result.stdout)


@pytest.mark.native_upload
def test_documented_native_single_file_upload(kube, adapter_gateway):
    native = adapter_gateway
    (kube.evidence/'upload-source-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, indent=2))
    operation = uuid4()
    source = kube.evidence/(operation.hex+'.bin')
    payload = bytes(range(256))*4096
    with source.open('xb') as stream:
        stream.write(payload)
    source.chmod(0o400)
    original = source_identity(source)
    assert original['size'] == 1048576
    remote = '/tmp/'+operation.hex+'.bin'
    receipts = kube.evidence/'upload-receipts';receipts.mkdir(mode=0o700)
    summary = {'outcome':'failed', 'operation':str(operation), 'source':original, 'remote':remote,
               'cli_invocations':0, 'native_internal_attempts':'unknown', 'application_retries':0,
               'upload_delivery':'not_dispatched', 'upload_completion':'unknown'}
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client, closing(ReceiptDirectory(receipts)) as journal:
        sdk = SdkReceipts(client, kube.evidence)
        try:
            with owned(kube, native, sdk, summary, '512Mi') as (name, pair):
                before = execute(sdk, name, f'''import json,os,stat
p={remote!r};assert not os.path.lexists(p)
s=os.lstat('/tmp');assert stat.S_ISDIR(s.st_mode) and os.path.realpath('/tmp')=='/tmp'
print(json.dumps(dict(device=s.st_dev,inode=s.st_ino)))''')
                assert before.exit_code == 0 and before.stderr == ''
                parent = json.loads(before.stdout)
                assert sdk.call('get', name, workspace='default').id == summary['sandbox_id']
                journal.write(operation, 'intent', dict(summary, name=name, sandbox_id=summary['sandbox_id'], parent=parent))
                summary.update(upload_delivery='unknown', cli_invocations=1)
                result = native['cli']('sandbox', 'upload', '--no-git-ignore', name, str(source), remote, check=False)
                summary['cli_exit'] = result.returncode
                if result.returncode != 0:
                    raise AssertionError('Native upload did not succeed; do not replay unknown writes')
                summary['upload_delivery'] = 'acknowledged'
                assert source_identity(source) == original
                assert sdk.call('get', name, workspace='default').id == summary['sandbox_id']
                first = file_observation(sdk, name, remote)
                assert first['size'] == original['size'] and first['sha256'] == original['sha256']
                second = file_observation(sdk, name, remote)
                assert second == first
                after = execute(sdk, name, "import os,json;s=os.lstat('/tmp');print(json.dumps(dict(device=s.st_dev,inode=s.st_ino)))")
                assert after.exit_code == 0 and after.stderr == '' and json.loads(after.stdout) == parent
                summary.update(upload_completion='verified', admitted_file=first, independent_reread=second)
                # Deliberate fixture corruption must not remain admissible by digest.
                changed = execute(sdk, name, f"import os;os.chmod({remote!r},0o600);f=open({remote!r},'r+b');f.write(b'changed');f.close()")
                assert changed.exit_code == 0 and changed.stderr == ''
                changed_file = file_observation(sdk, name, remote)
                assert changed_file['sha256'] != original['sha256']
                summary['changed_bytes_refused'] = changed_file
            assert summary['cleanup_confirmed'] and summary['container_tasks_absent']
            summary['outcome'] = 'passed'
        finally:
            summary['sdk_method_calls'] = sdk.counter
            journal.write(operation, 'result', summary)
            (kube.evidence/'native-upload.json').write_text(json.dumps(summary, indent=2))
