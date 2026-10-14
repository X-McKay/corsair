import os
from pathlib import Path
import subprocess

import pytest

from corsair.v2.contracts import SourceRequest
from corsair.v2.source import SourceError, SourceService
from corsair.v2.storage import Store


GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
                          env=GIT_ENV, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True).stdout.strip()


def test_directory_capture_skips_sensitive_and_symlink_entries_and_supports_reads(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "app.py").write_text("first\nsecond\n", encoding="utf-8")
    (source / ".env").write_text("TOKEN=not-captured", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / ".venv" / "secret").write_text("not-captured", encoding="utf-8")
    (source / "link-file").symlink_to("app.py")
    (source / "link-directory").symlink_to(source, target_is_directory=True)
    source_link = tmp_path / "input-link"
    source_link.symlink_to(source, target_is_directory=True)
    os.mkfifo(source / "pipe")
    with Store(tmp_path / "store") as store:
        service = SourceService(store)
        with pytest.raises(SourceError, match="real directory"):
            service.capture(SourceRequest(path=str(source_link)))
        snapshot = service.capture(SourceRequest(path=str(source)))
        assert service.list_paths(snapshot) == ["app.py"]
        assert service.read_text(snapshot, "app.py", 2) == "second\n"
        assert set(snapshot.skipped) == {"sensitive:.env", "excluded:.venv", "symlink:link-file",
                                         "symlink:link-directory", "nonregular:pipe"}
        with pytest.raises(SourceError, match="not UTF-8"):
            binary = source / "binary"
            binary.write_bytes(b"\xff")
            bad = service.capture(SourceRequest(path=str(source)))
            service.read_text(bad, "binary")


def test_directory_bounds_and_safe_materialization_overlay_confinement(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "a.txt").write_text("old\n", encoding="utf-8")
    (source / "bin").mkdir()
    executable = source / "bin" / "run"
    executable.write_bytes(b"#!/bin/sh\n")
    executable.chmod(0o755)
    with Store(tmp_path / "store") as store:
        service = SourceService(store)
        with pytest.raises(SourceError, match="byte bound"):
            service.capture_directory(source, max_file_bytes=2)
        snapshot = service.capture(SourceRequest(path=str(source)))
        target = tmp_path / "materialized"
        assert service.materialize(snapshot, target, {"a.txt": b"new\n", "tests/test_new.py": b"assert True\n"}) == target
        assert (target / "a.txt").read_bytes() == b"new\n"
        assert (target / "bin" / "run").stat().st_mode & 0o111
        assert not any(path.is_symlink() for path in target.rglob("*"))
        with pytest.raises(SourceError, match="fresh"):
            service.materialize(snapshot, target)
        rejected = tmp_path / "rejected"
        with pytest.raises(ValueError):
            service.materialize(snapshot, rejected, {"../escape": b"no"})
        assert not rejected.exists() and not (tmp_path / "escape").exists()


def test_tampered_artifact_is_rejected_and_diff_summarizes_binary(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(); two.mkdir()
    (one / "text").write_text("old\n", encoding="utf-8")
    (two / "text").write_text("new\n", encoding="utf-8")
    (one / "binary").write_bytes(b"\x00old")
    (two / "binary").write_bytes(b"\x00new")
    with Store(tmp_path / "store") as store:
        service = SourceService(store)
        baseline = service.capture(SourceRequest(path=str(one)))
        candidate = service.capture(SourceRequest(path=str(two)))
        rendered = service.diff(baseline, candidate)
        assert "-old" in rendered and "+new" in rendered and "Binary or oversized difference: binary" in rendered
        artifact = store.artifacts_root / baseline.files[0].artifact.sha256
        artifact.chmod(0o600)
        artifact.write_bytes(b"changed")
        artifact.chmod(0o400)
        with pytest.raises(Exception, match="Artifact"):
            service.read_text(baseline, baseline.files[0].path)


def test_pinned_local_git_capture_uses_tree_identity_without_changing_checkout(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git(checkout, "init", "-q")
    (checkout / "tracked.txt").write_text("committed\n", encoding="utf-8")
    (checkout / ".env").write_text("TOKEN=not-captured", encoding="utf-8")
    git(checkout, "add", "tracked.txt", ".env")
    git(checkout, "commit", "-qm", "fixture")
    commit, tree = git(checkout, "rev-parse", "HEAD"), git(checkout, "rev-parse", "HEAD^{tree}")
    (checkout / "tracked.txt").write_text("uncommitted\n", encoding="utf-8")
    before = git(checkout, "status", "--porcelain")
    hook = checkout / ".git" / "hooks" / "post-checkout"
    marker = tmp_path / "hook-ran"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)
    with Store(tmp_path / "store") as store:
        service = SourceService(store)
        snapshot = service.capture(SourceRequest(path=str(checkout), commit=commit))
        assert (snapshot.commit, snapshot.tree) == (commit, tree)
        assert service.read_text(snapshot, "tracked.txt") == "committed\n"
        assert service.list_paths(snapshot, "*.txt") == ["tracked.txt"]
        assert snapshot.skipped == ("sensitive:.env",)
    assert git(checkout, "status", "--porcelain") == before
    assert not marker.exists()


def test_pinned_sha256_git_repository_is_captured_when_native_git_supports_it(tmp_path):
    checkout = tmp_path / "sha256-checkout"
    created = subprocess.run(["/usr/bin/git", "init", "--object-format=sha256", "-q", str(checkout)], env=GIT_ENV,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if created.returncode:
        pytest.skip("native Git does not support SHA-256 repositories")
    (checkout / "tracked.txt").write_text("sha256-object-format\n", encoding="utf-8")
    git(checkout, "add", "tracked.txt")
    git(checkout, "commit", "-qm", "fixture")
    commit, tree = git(checkout, "rev-parse", "HEAD"), git(checkout, "rev-parse", "HEAD^{tree}")
    assert len(commit) == len(tree) == 64
    with Store(tmp_path / "store") as store:
        snapshot = SourceService(store).capture(SourceRequest(path=str(checkout), commit=commit))
        assert (snapshot.commit, snapshot.tree) == (commit, tree)
        assert SourceService(store).read_text(snapshot, "tracked.txt") == "sha256-object-format\n"


def test_candidate_path_and_commit_selection_and_git_sensitive_defaults(tmp_path):
    baseline, candidate = tmp_path / "baseline", tmp_path / "candidate"
    baseline.mkdir(); candidate.mkdir()
    (baseline / "file").write_bytes(b"base")
    (candidate / "file").write_bytes(b"candidate")
    with Store(tmp_path / "store") as store:
        service = SourceService(store)
        request = SourceRequest(path=str(baseline), candidate_path=str(candidate))
        assert service.read_text(service.capture(request, "candidate"), "file") == "candidate"
