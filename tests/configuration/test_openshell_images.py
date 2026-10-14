"""Offline guards for tools/openshell_images.py: the node digest it records is the content it verified, and it never
signals a process it did not start. No claim about a live node or gateway."""
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import openshell_images as tool


@pytest.mark.parametrize(('tag', 'expected'), [
    ('corsair-java:c7e6b24f0068035d', ('docker.io/library/corsair-java', 'c7e6b24f0068035d')),
    ('corsair-python', ('docker.io/library/corsair-python', 'latest')),
    ('team/image:1', ('docker.io/team/image', '1')),
    ('registry.local:5000/image:2', ('registry.local:5000/image', '2')),
])
def test_local_tags_normalize_to_the_containerd_name(tag, expected):
    assert tool.reference(tag) == expected


def test_digest_references_are_not_local_tags():
    with pytest.raises(ValueError):
        tool.reference('corsair-java@sha256:' + '0' * 64)


def test_every_matrix_image_is_a_local_tag():
    images = tool.matrix_images()
    assert images and len(images) == len(set(images))
    for image in images:
        tool.reference(image)


class FakeNode:
    """Answers the native docker/kind/ctr calls `load` makes for one local image."""

    def __init__(self, tag, content, listed_digest=None, local_id=None):
        self.repository, self.version = tool.reference(tag)
        self.content = content
        self.digest = listed_digest or 'sha256:' + hashlib.sha256(content.encode()).hexdigest()
        self.local_id = local_id or json.loads(content)['config']['digest']
        self.tagged = []
        self.calls = []

    def native(self, argv, check=True, timeout=120, env=None):
        argv = list(map(str, argv))
        self.calls.append(argv)
        out = ''
        if 'inspect' in argv:
            out = self.local_id + '\n'
        elif argv[-2:] == ['images', 'list']:
            rows = ['REF TYPE DIGEST SIZE PLATFORMS LABELS', f'{self.repository}:{self.version} manifest {self.digest} 1 linux/amd64 -']
            rows += [f'{name} manifest {self.digest} 1 linux/amd64 -' for name in self.tagged]
            out = '\n'.join(rows) + '\n'
        elif 'content' in argv:
            out = self.content
        elif argv[-3:-2] == ['tag']:
            self.tagged.append(argv[-1])
        return SimpleNamespace(returncode=0, stdout=out, stderr='')


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, 'IMAGES', tmp_path / 'images.json')
    monkeypatch.setattr(tool, 'require_gateway', lambda kube: ({'metadata': {'uid': 'node'}}, {}))
    monkeypatch.setattr(tool, 'verify', lambda *args: None)
    monkeypatch.setattr(tool, 'matrix_images', lambda: ['corsair-java:abc'])
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    return evidence


def test_load_records_the_verified_manifest_digest(isolated):
    node = FakeNode('corsair-java:abc', json.dumps({'config': {'digest': 'sha256:' + 'c' * 64}}))
    mapping = tool.load(node, isolated)
    assert mapping == {'corsair-java:abc': 'docker.io/library/corsair-java@' + node.digest}
    assert json.loads(tool.IMAGES.read_text()) == mapping == json.loads((isolated / 'images.json').read_text())
    assert node.tagged == ['docker.io/library/corsair-java@' + node.digest]


def test_load_refuses_node_content_that_does_not_hash_to_its_digest(isolated):
    node = FakeNode('corsair-java:abc', json.dumps({'config': {'digest': 'sha256:' + 'c' * 64}}),
                    listed_digest='sha256:' + 'd' * 64)
    with pytest.raises(RuntimeError, match='does not hash'):
        tool.load(node, isolated)
    assert not tool.IMAGES.exists() and not node.tagged


def test_load_refuses_a_node_image_that_is_not_the_local_image(isolated):
    node = FakeNode('corsair-java:abc', json.dumps({'config': {'digest': 'sha256:' + 'c' * 64}}),
                    local_id='sha256:' + 'e' * 64)
    with pytest.raises(RuntimeError, match='differs from the local Docker image'):
        tool.load(node, isolated)
    assert not tool.IMAGES.exists()


def test_forward_stop_never_signals_a_process_running_another_command(tmp_path, monkeypatch):
    other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        record = tmp_path / 'port-forward.json'
        record.write_text(json.dumps({'pid': other.pid, 'argv': ['kubectl', 'port-forward']}))
        monkeypatch.setattr(tool, 'FORWARD', record)
        with pytest.raises(RuntimeError, match='refusing to signal'):
            tool.stop_forward(tmp_path)
        assert other.poll() is None and record.exists()
        assert json.loads((tmp_path / 'forward-stop.json').read_text())['confirmed'] is False
    finally:
        other.kill()
        other.wait()


def test_forward_stop_terminates_the_recorded_process(tmp_path, monkeypatch):
    argv = [sys.executable, '-c', 'import time; time.sleep(30)']
    owned = subprocess.Popen(argv)
    try:
        record = tmp_path / 'port-forward.json'
        record.write_text(json.dumps({'pid': owned.pid, 'argv': argv}))
        monkeypatch.setattr(tool, 'FORWARD', record)
        # A child stays a zombie until reaped; reap it in the background so /proc reflects the exit.
        monkeypatch.setattr(tool, 'process_argv', lambda pid: None if owned.poll() is not None else argv)
        assert tool.stop_forward(tmp_path)['confirmed'] is True
        assert not record.exists() and owned.returncode == -15
    finally:
        if owned.poll() is None:
            owned.kill()
            owned.wait()
    assert os.path.exists(tmp_path / 'forward-stop.json')
