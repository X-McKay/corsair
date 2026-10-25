from __future__ import annotations

import io
import os
import tarfile
import threading
from pathlib import Path

import pytest

from corsair.contracts import Case, Finding, PythonRecipe, RunManifest, Source
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings
from corsair.tools.security import sources
from corsair.tools.security.sources import (
    SourceAdmissionError,
    prepare_case,
    read_source,
    snapshot_source,
)


def _manifest() -> RunManifest:
    return RunManifest(
        package_version="0.1",
        request_digest="1" * 64,
        config_digest="2" * 64,
        producer_prompt_digest="3" * 64,
        auditor_prompt_digest="4" * 64,
        image_id="sha256:test",
        models={"producer": "test", "auditor": "test"},
    )


def _case(source: Source) -> Case:
    return Case(
        case_id="source-case",
        finding=Finding(title="read", description="test", file="reader.py", line=4),
        source=source,
        recipe=PythonRecipe(
            module_file="reader.py",
            function="read_file",
            payload_parameter="path",
            fixed_kwargs={"root": "/fixtures/allowed"},
        ),
    )


def _source_tree(root: Path, content: str | None = None) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "reader.py").write_text(
        content
        or (
            "from pathlib import Path\n\n"
            "def read_file(root, path):\n"
            "    return (Path(root) / path).read_text()\n"
        ),
        encoding="utf-8",
    )
    return project


def _settings(root: Path) -> Settings:
    return Settings(source_root=str(root), artifact_root=str(root / "artifacts"))


def test_snapshot_is_deterministic_and_expected_digest_is_enforced(tmp_path: Path) -> None:
    project = _source_tree(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    settings = _settings(tmp_path)

    first = snapshot_source(Source(path="project"), settings, store)
    second = snapshot_source(Source(path="project", expected_digest=first.sha256), settings, store)
    absolute = snapshot_source(Source(path=str(project.absolute())), settings, store)

    assert first == second
    assert absolute == first
    with pytest.raises(SourceAdmissionError, match="expected_digest"):
        snapshot_source(Source(path="project", expected_digest="0" * 64), settings, store)


def test_source_admission_rejects_escape_symlink_and_oracle(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    settings = _settings(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(SourceAdmissionError, match="relative POSIX path"):
        snapshot_source(Source(path="../outside"), settings, store)

    (tmp_path / "project" / "oracle.json").write_text('{"answer": true}', encoding="utf-8")
    with pytest.raises(SourceAdmissionError, match="sensitive/evaluation"):
        snapshot_source(Source(path="project"), settings, store)
    (tmp_path / "project" / "oracle.json").unlink()

    (tmp_path / "outside.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "project" / "linked.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(SourceAdmissionError, match="symbolic"):
        snapshot_source(Source(path="project"), settings, store)


def test_snapshot_rejects_controlled_directory_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synchronize the swap at admission/traversal rather than relying on timing."""
    project = _source_tree(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "reader.py").write_text("outside_private_source = True\n", encoding="utf-8")
    parked = tmp_path / "project-before-swap"
    store = ArtifactStore(tmp_path / "artifacts")

    swap_requested = threading.Event()
    swap_finished = threading.Event()
    replacement_errors: list[BaseException] = []

    def replace_directory() -> None:
        if not swap_requested.wait(timeout=2):
            return
        try:
            project.rename(parked)
            project.symlink_to(outside, target_is_directory=True)
        except BaseException as exc:
            # The main assertion reports any setup failure deterministically.
            replacement_errors.append(exc)
        finally:
            swap_finished.set()

    replacement = threading.Thread(target=replace_directory)
    original_open = os.open
    original_walk = os.walk

    def controlled_open(path, flags, mode=0o777, *, dir_fd=None):
        # New admission opens this source component relative to its pinned root fd.
        if path == "project" and dir_fd is not None:
            swap_requested.set()
            if not swap_finished.wait(timeout=2):
                raise RuntimeError("directory replacement did not complete")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    def controlled_walk(top, *args, **kwargs):
        # The former pathname implementation entered os.walk only after its lstat checks.
        if Path(top) == project:
            swap_requested.set()
            if not swap_finished.wait(timeout=2):
                raise RuntimeError("directory replacement did not complete")
        yield from original_walk(top, *args, **kwargs)

    replacement.start()
    monkeypatch.setattr(os, "open", controlled_open)
    monkeypatch.setattr(os, "walk", controlled_walk)
    try:
        with pytest.raises(SourceAdmissionError, match="source changed"):
            snapshot_source(Source(path="project"), _settings(tmp_path), store)
    finally:
        replacement.join(timeout=2)

    assert not replacement.is_alive()
    assert swap_finished.is_set()
    assert not replacement_errors
    assert not list(store.blobs.iterdir())


def test_source_admission_fails_closed_without_fd_no_follow_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source_tree(tmp_path)
    monkeypatch.setattr(sources, "_SECURE_SOURCE_SUPPORTED", False)

    with pytest.raises(SourceAdmissionError, match="Linux fd-based no-follow"):
        snapshot_source(
            Source(path="project"), _settings(tmp_path), ArtifactStore(tmp_path / "artifacts")
        )


def test_read_source_rejects_unsafe_artifact_member(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo("../outside.py")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    ref = store.put(payload.getvalue(), "application/x-tar")

    with pytest.raises(SourceAdmissionError, match="unsafe member"):
        read_source(ref, "outside.py", store, 100)


def test_prepare_case_uses_pinned_content_and_hides_local_source_root(tmp_path: Path) -> None:
    _source_tree(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    prepared = prepare_case(_case(Source(path="project")), _settings(tmp_path), store, _manifest())

    assert prepared.source_excerpt.startswith("1: from pathlib")
    assert str(tmp_path) not in prepared.source_excerpt
    assert "path" not in prepared.source.model_fields_set
    assert "read_file" in read_source(prepared.source, "reader.py", store, 10000)


@pytest.mark.parametrize(
    "filename", ["producer-oracle.json", "auditor_oracle.json", "Ground-Truth.yaml"]
)
def test_prefixed_oracles_never_enter_source_snapshots(tmp_path, filename):
    project = _source_tree(tmp_path)
    (project / filename).write_text('{"expected": "private evaluator label"}')
    with pytest.raises(SourceAdmissionError, match="sensitive/evaluation"):
        snapshot_source(
            Source(path="project"), _settings(tmp_path), ArtifactStore(tmp_path / "store")
        )
