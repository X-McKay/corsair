"""Snapshot reads verify the artifact once per call and serve only those verified bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from corsair.adapters.scm.local import (
    StoredSourceReader,
    iter_snapshot_files,
    read_source,
    snapshot_source,
)
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ArtifactRef, Source
from corsair.settings import Settings


class _CountingStore(ArtifactStore):
    def __init__(self, root: Path):
        super().__init__(root)
        self.gets = 0

    def get(self, ref: ArtifactRef) -> bytes:
        self.gets += 1
        return super().get(ref)


def _admitted(tmp_path: Path, files: int) -> tuple[_CountingStore, ArtifactRef, dict[str, bytes]]:
    project = tmp_path / "project"
    expected: dict[str, bytes] = {}
    for index in range(files):
        relative = f"pkg{index % 3}/module_{index:02d}.py"
        content = f"VALUE = {index}\n".encode()
        (project / relative).parent.mkdir(parents=True, exist_ok=True)
        (project / relative).write_bytes(content)
        expected[relative] = content
    store = _CountingStore(tmp_path / "artifacts")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(store.root))
    return store, snapshot_source(Source(path="project"), settings, store), expected


def test_listing_fetches_and_verifies_the_snapshot_once(tmp_path: Path) -> None:
    store, ref, expected = _admitted(tmp_path, 12)
    store.gets = 0

    listed = dict(StoredSourceReader(store).iter_files(ref))

    assert listed == expected
    assert store.gets == 1


def test_read_fetches_and_verifies_the_snapshot_once(tmp_path: Path) -> None:
    store, ref, expected = _admitted(tmp_path, 4)
    store.gets = 0

    text = read_source(ref, "pkg1/module_01.py", store, 1024)

    assert text == expected["pkg1/module_01.py"].decode()
    assert store.gets == 1


def test_tampered_snapshot_blob_is_refused_by_every_read(tmp_path: Path) -> None:
    store, ref, _ = _admitted(tmp_path, 4)
    blob = store.blobs / ref.sha256
    content = bytearray(blob.read_bytes())
    content[600] ^= 0x01
    blob.chmod(0o644)
    blob.write_bytes(bytes(content))

    with pytest.raises(ValueError, match="digest"):
        list(iter_snapshot_files(ref, store))
    with pytest.raises(ValueError, match="digest"):
        read_source(ref, "pkg0/module_00.py", store, 1024)
