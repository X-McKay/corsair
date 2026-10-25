from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from corsair.contracts import Case, Finding, PythonRecipe, RunManifest, Source
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings
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
