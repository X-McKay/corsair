"""The shipped workload credential scan, run locally against temporary roots."""
import hashlib
import json
import os
import subprocess
import sys

from tests.qualification.credential_scan import SCAN

PREFIX = 'corsair-fake-credential-'
DUMMY = PREFIX + '0123456789abcdef0123456789abcdef'
DIGEST = hashlib.sha256(DUMMY.encode()).hexdigest()


def scan(tmp_path, value, *roots):
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'CORSAIR_QUAL_FAKE_TOKEN': value}
    result = subprocess.run([sys.executable, '-I', '-c', SCAN, PREFIX, str(len(DUMMY)), DIGEST,
                             'CORSAIR_QUAL_FAKE_TOKEN', *map(str, roots)], capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 0, result.stderr
    assert DUMMY not in result.stdout
    return json.loads(result.stdout)


def test_placeholder_recorded_and_planted_file_found(tmp_path):
    (tmp_path / 'clean').write_bytes(PREFIX.encode() + b'not-the-credential-but-same-prefix!!')
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'leak').write_bytes(b'x' * 7 + DUMMY.encode() + b'\n')
    (tmp_path / 'link').symlink_to(tmp_path / 'nested' / 'leak')
    seen = scan(tmp_path, 'openshell:resolve:env:CORSAIR_QUAL_FAKE_TOKEN', tmp_path, tmp_path / 'missing')
    assert seen['env'] == {'present': True, 'is_dummy': False, 'value': 'openshell:resolve:env:CORSAIR_QUAL_FAKE_TOKEN'}
    assert seen['placeholders'] == {'CORSAIR_QUAL_FAKE_TOKEN': 'openshell:resolve:env:CORSAIR_QUAL_FAKE_TOKEN'}
    root = seen['roots'][str(tmp_path)]
    assert root['matches'] == [str(tmp_path / 'nested' / 'leak')] and root['files'] == 2
    assert seen['roots'][str(tmp_path / 'missing')]['state'] == 'absent'
    assert not any(p.get('matches') for p in seen['processes'].values())


def test_raw_credential_in_environment_is_withheld_and_detected(tmp_path):
    seen = scan(tmp_path, DUMMY, tmp_path)
    assert seen['env'] == {'present': True, 'is_dummy': True, 'value': None}
    own = [p for p in seen['processes'].values() if p['state'] == 'scanned' and p['env'].get('is_dummy')]
    assert own and all(p['matches'] for p in own)
