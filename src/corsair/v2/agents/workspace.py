"""Trusted, read-only workspace for captured source bytes.

The local PydanticAI backend is not an isolation boundary: it can otherwise
resolve an absolute host path.  This module confines every backend read to a
managed source-workspace root, while native Harness ``FileSystem`` adds the
narrower ``source`` directory boundary for model-facing file operations.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import WorkspaceRef as NativeWorkspaceRef
from pydantic_ai.tools import RunContext
from pydantic_ai.workspaces import LocalWorkspaceBackend, ReadOnlyWorkspace, Workspace

from ..contracts import OperatorConfig, SourceSnapshot
from ..source import SourceService
from ..storage import Store, _private_directory
from .dependencies import AgentDeps, WorkspaceRef

CAPABILITY_ID = "corsair.v2.source-workspace.v1"
_WORKSPACE_DIRECTORY = "agent-workspaces"
_SOURCE_DIRECTORY = "source"
_SKILLS_DIRECTORY = "operator-skills"
_SHA256 = __import__("re").compile(r"^[0-9a-f]{64}$")
_SKILL_FILES = tuple(sorted(Path(__file__).with_name("roles").glob("*/skills/*/SKILL.md")))
_BUNDLE_SHA = hashlib.sha256(b"".join(p.parent.name.encode() + b"\0" + p.read_bytes() for p in _SKILL_FILES)).hexdigest()


def _checked_workspace_id(value: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("A pinned source-manifest SHA-256 is required")
    return value


def _managed_root(storage_root: str | Path, manifest_sha256: str) -> Path:
    """Build a lexical managed root; existence validation remains I/O-side only."""
    digest = _checked_workspace_id(manifest_sha256)
    root = Path(storage_root).expanduser().absolute()
    return root / _WORKSPACE_DIRECTORY / f"{_BUNDLE_SHA[:24]}-{digest}"


def _relative_managed_path(path: str) -> str:
    """Reject absolute, parent, and control-character path escapes before backend I/O."""
    if not isinstance(path, str) or not path or "\\" in path:
        raise PermissionError("Workspace paths must be nonempty canonical relative paths")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise PermissionError("Workspace path escapes are refused")
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise PermissionError("Workspace path contains a control character")
    return path


class _ConfinedReadOnlyWorkspace(ReadOnlyWorkspace):
    """Read-only wrapper that denies host-absolute and parent traversal paths.

    ``ReadOnlyWorkspace`` protects mutation/commands but intentionally does not
    make a local workspace an access-control boundary.  This wrapper supplies
    the missing path guard for the fixed captured-source/skill bundle layout.
    """

    def __init__(self, wrapped: Workspace, root: Path, manifest_sha256: str):
        super().__init__(wrapped)
        self._corsair_root = root.absolute()
        self._corsair_ref = NativeWorkspaceRef(provider="corsair-source", id=_checked_workspace_id(manifest_sha256))

    @property
    def ref(self) -> NativeWorkspaceRef:
        # Agent capability resolution requires that a supplier returns the
        # exact ref requested by ``agent.run(workspace=...)``. Do not leak the
        # local backend's host-path ``provider='local'`` identity.
        return self._corsair_ref

    def _path(self, path: str) -> str:
        # Native FileSystem resolves ``source`` to an absolute canonical path,
        # then calls realpath/stat on it. Accept that canonical internal form,
        # never arbitrary host absolutes.
        candidate = Path(path)
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        else:
            _relative_managed_path(path)
            resolved = (self._corsair_root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(self._corsair_root)
        except ValueError as error:
            raise PermissionError("Workspace access outside the managed source root is refused") from error
        return str(resolved)

    async def working_dir(self) -> str:
        # Harness FileSystem requires a configured root_dir to contain the
        # workspace working directory. The primary workspace still exposes the
        # fixed sibling skill library through its guarded backend, while model
        # file tools are scoped to this immutable source child.
        return str(self._corsair_root / _SOURCE_DIRECTORY)

    async def read_bytes(self, path: str) -> bytes:
        return await super().read_bytes(self._path(path))

    async def stat(self, path: str):  # type: ignore[no-untyped-def]
        return await super().stat(self._path(path))

    async def list_dir(self, path: str):  # type: ignore[no-untyped-def]
        return await super().list_dir(self._path(path))

    async def exists(self, path: str) -> bool:
        return await super().exists(self._path(path))

    async def realpath(self, path: str) -> str:
        return await super().realpath(self._path(path))

    async def resolve(self, path: str, base: str | None = None) -> str:
        # FileSystem resolves tool paths relative to its already-validated
        # working directory. Preserve that native API while checking both
        # operands before the local backend can apply absolute-path semantics.
        checked_base = Path(self._path(base)) if base is not None else self._corsair_root / _SOURCE_DIRECTORY
        candidate = Path(path) if Path(path).is_absolute() else checked_base / path
        return await super().resolve(self._path(str(candidate)))


def _verify_managed_tree(root: Path, snapshot: SourceSnapshot, store: Store) -> None:
    """Confirm a reusable workspace contains precisely the captured source bytes."""
    source = root / _SOURCE_DIRECTORY
    if not root.is_dir() or root.is_symlink() or not source.is_dir() or source.is_symlink():
        raise ValueError("Managed source workspace is not a real private directory")
    for item in snapshot.files:
        path = source.joinpath(*item.path.split("/"))
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError("Managed source workspace contains a nonregular captured file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item.artifact.sha256:
            raise ValueError("Managed source workspace bytes no longer match the source manifest")
    expected = {item.path for item in snapshot.files}
    found: set[str] = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("Managed source workspace contains a symbolic link")
        if path.is_file():
            found.add(path.relative_to(source).as_posix())
    if found != expected:
        raise ValueError("Managed source workspace does not match the immutable source manifest")
    skills = root / _SKILLS_DIRECTORY
    expected_skills = {p.parent.name: p.read_bytes() for p in _SKILL_FILES}
    actual_skills = {}
    for path in skills.rglob("*"):
        if path.is_symlink():
            raise ValueError("Managed operator skill bundle contains a symbolic link")
        if path.is_file():
            if path.name != "SKILL.md" or path.parent.parent != skills:
                raise ValueError("Unexpected operator skill bundle entry")
            actual_skills[path.parent.name] = path.read_bytes()
    if actual_skills != expected_skills:
        raise ValueError("Managed operator skill bundle differs from installed package")


def _copy_skills(destination: Path) -> None:
    """Copy only packaged operator instructions next to a materialized source tree."""
    origin = Path(__file__).with_name("roles")
    if destination.exists():
        raise ValueError("Operator skill destination must be fresh")
    destination.mkdir(mode=0o700)
    for role in ("analysis", "investigator", "control_author", "exploit_author", "validity", "repair"):
        source = origin / role / "skills"
        for skill in sorted(source.glob("*/SKILL.md")):
            data = skill.read_bytes()
            if len(data) > 64 * 1024:
                raise ValueError("Operator skill exceeds bounded package envelope")
            # Skills discovers a library's direct skill folders. Every role's
            # package-owned ID is globally unique, so a flat fixed library does
            # not permit cross-role discovery: factory ``include`` is exact.
            skill_target = destination / skill.parent.name
            skill_target.mkdir(mode=0o700)
            output = skill_target / "SKILL.md"
            output.write_bytes(data)
            os.chmod(output, 0o600)


def prepare_source_workspace(snapshot: SourceSnapshot, config: OperatorConfig) -> WorkspaceRef:
    """Publish a shared immutable source/skill cache; never execute its bytes."""
    if not isinstance(snapshot, SourceSnapshot) or not isinstance(config, OperatorConfig):
        raise ValueError("A v2 SourceSnapshot and OperatorConfig are required")  # noqa: TRY004 - invalid admission is consistently ValueError
    with Store(config.storage_root) as store:
        root = _managed_root(store.root, snapshot.manifest.sha256)
        parent = _private_directory(root.parent)
        # Cross-process publication lock: repeated cases share a content cache,
        # not a mutable workspace or an inference result. The bundle hash makes
        # skill edits select a new cache without clobbering in-flight readers.
        fd = os.open(parent / (root.name + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if root.exists():
                _verify_managed_tree(root, snapshot, store)
            else:
                temporary = Path(tempfile.mkdtemp(prefix=".source-", dir=parent))
                try:
                    SourceService(store).materialize(snapshot, temporary / _SOURCE_DIRECTORY)
                    _copy_skills(temporary / _SKILLS_DIRECTORY)
                    os.rename(temporary, root)
                    _verify_managed_tree(root, snapshot, store)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
        finally:
            os.close(fd)
    return WorkspaceRef(id=snapshot.manifest.sha256)


def cleanup_source_workspace(ref: WorkspaceRef, config: OperatorConfig) -> None:
    """Remove one fixed managed source copy; immutable artifacts remain private in Store."""
    if not isinstance(ref, WorkspaceRef) or not isinstance(config, OperatorConfig):
        raise ValueError("A v2 workspace reference and operator configuration are required")  # noqa: TRY004 - invalid admission is consistently ValueError
    root = _managed_root(config.storage_root, ref.id)
    parent = root.parent.absolute()
    if root.parent != parent or not parent.name == _WORKSPACE_DIRECTORY:
        raise ValueError("Refusing a source-workspace cleanup outside the managed root")
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Refusing cleanup of a non-directory managed workspace")
        for item in root.rglob("*"):
            if item.is_symlink():
                raise ValueError("Refusing cleanup of a workspace containing symbolic links")
        shutil.rmtree(root)


class SourceWorkspaceCapability(AbstractCapability[AgentDeps]):
    """Pure construction-time supplier for a fixed captured-source workspace."""

    id = CAPABILITY_ID

    def __init__(self, storage_root: str | Path):
        self._storage_root = str(Path(storage_root).expanduser().absolute())

    def get_workspace(self, ctx: RunContext[AgentDeps], *, ref: NativeWorkspaceRef | None):
        # This method is called during direct setup or durable activity dispatch.
        # It performs no existence checks, storage reads, or source materialization.
        if ref is None or ref.provider != "corsair-source" or not _SHA256.fullmatch(ref.id):
            return None
        deps = ctx.deps
        if not isinstance(deps, AgentDeps) or deps.workspace_ref is None:
            return None
        if ref.id != deps.workspace_ref.id or ref.id != deps.source_manifest.sha256:
            return None
        root = _managed_root(self._storage_root, ref.id)
        return _ConfinedReadOnlyWorkspace(Workspace(LocalWorkspaceBackend(root)), root, ref.id)


__all__ = [
    "CAPABILITY_ID",
    "SourceWorkspaceCapability",
    "WorkspaceRef",
    "cleanup_source_workspace",
    "prepare_source_workspace",
]
