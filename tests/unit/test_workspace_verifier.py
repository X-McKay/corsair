"""SPEC-0070: the static workspace verifier reports the same document as the Python reference, plus its own digest.

CI has no Go toolchain, so this runs where one is installed and is skipped otherwise; the adapter's unit tests use
the Python reference as the binary's stand-in."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from corsair.adapters.openshell_workspace import VERIFY

SOURCE = Path(__file__).resolve().parents[2] / 'tools' / 'workspace-verify'
GO = shutil.which('go')


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    if GO is None:
        pytest.skip('no Go toolchain on this host')
    out = tmp_path_factory.mktemp('verifier') / 'verify'
    subprocess.run([GO, 'build', '-trimpath', '-ldflags=-buildid=', '-o', str(out), '.'], cwd=SOURCE, check=True,
                   env=os.environ | {'CGO_ENABLED': '0', 'GOFLAGS': '-mod=mod'}, timeout=300)
    return out


def tree(root: Path):
    (root / 'pkg' / 'deep').mkdir(parents=True)
    (root / 'pkg' / 'app.py').write_bytes(b'def run():\n    return 1\n')
    (root / 'pkg' / 'deep' / 'big.bin').write_bytes(os.urandom(5000))
    (root / 'tool.sh').write_bytes(b'#!/bin/sh\n')
    (root / 'tool.sh').chmod(0o500)
    (root / 'link').symlink_to('tool.sh')
    os.mkfifo(root / 'pipe')


@pytest.mark.parametrize('limit, cap', [(64, 1 << 20), (3, 1 << 20), (64, 100)])
def test_the_static_verifier_matches_the_python_reference(binary, tmp_path, limit, cap):
    root = tmp_path / 'workspace'
    root.mkdir(mode=0o700)
    tree(root)
    argv = (str(root), str(limit), str(cap))
    reference = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', VERIFY, *argv], capture_output=True,
                               check=True, timeout=30)
    static = subprocess.run([str(binary), *argv], capture_output=True, check=True, timeout=30, env={})
    report = json.loads(static.stdout)
    assert report.pop('verifier_sha256') == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert report == json.loads(reference.stdout)


def test_an_absent_root_reports_only_that(binary, tmp_path):
    report = json.loads(subprocess.run([str(binary), str(tmp_path / 'absent'), '8', '8'], capture_output=True,
                                       check=True, timeout=30).stdout)
    assert set(report) == {'exists', 'euid', 'verifier_sha256'} and report['exists'] is False
