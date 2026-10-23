"""Deterministic evidence bundles for the locally built probe runtimes.

The bundle is an acquisition and review input.  It deliberately records no
aggregate license conclusion or reviewer approval; those remain separate,
human-owned corpus admission decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_EVIDENCE_FILE = 16 * 1024 * 1024
_MAX_EVIDENCE_TOTAL = 64 * 1024 * 1024


@dataclass(frozen=True)
class EvidenceFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class RuntimeEvidence:
    runtime_row: str
    image_reference: str
    image_id: str
    platform: str
    image_created: str
    parent_reference: str
    parent_image_id: str
    dockerfile: str
    dockerfile_sha256: str
    runtime_versions: tuple[str, ...]
    packages: tuple[str, ...]
    artifacts: tuple[tuple[str, str], ...]
    license_files: tuple[EvidenceFile, ...]


@dataclass(frozen=True)
class RuntimeSpec:
    runtime_row: str
    image: str
    parent: str
    dockerfile: str
    version_command: str
    license_command: str
    artifact_command: str


_COPYRIGHT_FILES = "find -L /usr/share/doc -mindepth 2 -maxdepth 2 -name copyright -type f -print0"
_ARCHIVE_FILES = ("LC_ALL=C sort -zu | tar --null --verbatim-files-from --files-from=- "
                  "--create --dereference --hard-dereference --file=-")


def _license_command(*sources: str) -> str:
    return "{ " + "; ".join((_COPYRIGHT_FILES, *sources)) + "; } | " + _ARCHIVE_FILES


RUNTIME_SPECS = (
    RuntimeSpec(
        runtime_row="pytest-cpython312",
        image="corsair-lite-python:dev",
        parent="docker.io/library/python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704",
        dockerfile="images/python/Dockerfile",
        version_command="python --version; python -m pip freeze --all",
        license_command=_license_command(
            "printf '%s\\0' /usr/local/lib/python3.12/LICENSE.txt",
            ("find -L /usr/local/lib/python3.12/site-packages -type f "
             "\\( -path '*.dist-info/licenses/*' -o -path '*.dist-info/METADATA' "
             "-o -path '*.dist-info/LICENSE*' \\) -print0"),
        ),
        artifact_command="sha256sum /usr/local/bin/python3.12 /opt/corsair/requirements.lock",
    ),
    RuntimeSpec(
        runtime_row="node-test-node22",
        image="corsair-lite-javascript:dev",
        parent="docker.io/library/node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392",
        dockerfile="images/javascript/Dockerfile",
        version_command="node --version; node -p 'JSON.stringify(process.versions)'",
        license_command=_license_command("printf '%s\\0' /usr/local/LICENSE"),
        artifact_command="sha256sum /usr/local/bin/node /usr/local/LICENSE",
    ),
    RuntimeSpec(
        runtime_row="javac-java21",
        image="corsair-lite-java:dev",
        parent=("docker.io/library/eclipse-temurin@sha256:"
                "742daacb9316be4b6fc60258f6e4ac2a11882f6c597373c92290a57bfad0d2e0"),
        dockerfile="images/java21/Dockerfile",
        version_command=("java -version 2>&1; java -XshowSettings:properties -version 2>&1 | "
                         "grep -E '^[[:space:]]+(java.runtime.version|java.vendor|os.arch) = '"),
        license_command=_license_command(
            "find -L \"$JAVA_HOME/legal\" -type f -print0",
            "find -L /opt/corsair/licenses -type f -print0",
        ),
        artifact_command=("sha256sum /opt/java/openjdk/bin/java /opt/corsair/jacoco-agent.jar "
                          "/opt/corsair/jacoco-cli.jar"),
    ),
    RuntimeSpec(
        runtime_row="perl-tap-540",
        image="corsair-lite-perl:dev",
        parent="docker.io/library/debian@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad",
        dockerfile="images/perl/Dockerfile",
        version_command=("perl -V:version -V:archname; perl -e 'require Devel::Cover; "
                         "require Test::More; require JSON::PP; "
                         "print qq(Devel::Cover=$Devel::Cover::VERSION\\n); "
                         "print qq(Test::More=$Test::More::VERSION\\n); "
                         "print qq(JSON::PP=$JSON::PP::VERSION\\n)'"),
        license_command=_license_command(),
        artifact_command="sha256sum /usr/bin/perl /usr/bin/cover",
    ),
)


CommandRunner = Callable[[tuple[str, ...]], bytes]


def _is_canonical_posix_path(value: str, *, absolute: bool) -> bool:
    if not value or value == "/" or value.startswith("//"):
        return False
    candidate = PurePosixPath(value)
    return (candidate.is_absolute() is absolute
            and value == candidate.as_posix()
            and not any(part in {"", ".", ".."} for part in candidate.parts))


def missing_package_copyrights(packages: tuple[str, ...], files: tuple[EvidenceFile, ...]) -> tuple[str, ...]:
    """Return installed dpkg package names that lack their in-image copyright bytes."""
    paths = {item.path for item in files}
    names: list[str] = []
    for record in packages:
        if "\t" not in record:
            raise ValueError("invalid package inventory")
        package, version = record.split("\t", 1)
        package = package.split(":", 1)[0]
        if not package or not version:
            raise ValueError("invalid package inventory")
        if f"/usr/share/doc/{package}/copyright" not in paths:
            names.append(package)
    return tuple(sorted(set(names)))


def _image_metadata(raw: bytes, reference: str) -> dict[str, str]:
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid Docker metadata for {reference}") from error
    if not isinstance(decoded, list) or len(decoded) != 1 or not isinstance(decoded[0], dict):
        raise ValueError(f"invalid Docker metadata for {reference}")
    item = decoded[0]
    required = ("Id", "Architecture", "Os", "Created")
    if any(not isinstance(item.get(name), str) or not item[name] for name in required):
        raise ValueError(f"incomplete Docker metadata for {reference}")
    if not _IMAGE_ID.fullmatch(item["Id"]):
        raise ValueError(f"invalid Docker image ID for {reference}")
    return {name: item[name] for name in required}


def _lines(raw: bytes, name: str) -> tuple[str, ...]:
    try:
        values = tuple(line for line in raw.decode("utf-8").splitlines() if line)
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} is not UTF-8") from error
    if not values:
        raise ValueError(f"{name} is empty")
    for value in values:
        _safe_list_text(name, value)
    return tuple(sorted(values))


def _artifacts(raw: bytes) -> tuple[tuple[str, str], ...]:
    artifacts: list[tuple[str, str]] = []
    for line in _lines(raw, "artifact inventory"):
        pieces = line.split(maxsplit=1)
        if len(pieces) != 2 or not _SHA256.fullmatch(pieces[0]):
            raise ValueError("invalid artifact inventory")
        name = pieces[1].strip()
        _safe_text("artifact name", name)
        if not _is_canonical_posix_path(name, absolute=True):
            raise ValueError("artifact name must be one canonical absolute path")
        artifacts.append((name, pieces[0]))
    if len({name for name, _ in artifacts}) != len(artifacts):
        raise ValueError("artifact names must be unique")
    return tuple(sorted(artifacts))


def collect_runtime_evidence(root: Path, spec: RuntimeSpec, *, runner: CommandRunner) -> RuntimeEvidence:
    """Collect one image using a supplied Docker command runner, keeping rendering independently testable."""
    root = Path(root).resolve(strict=True)
    dockerfile = root / spec.dockerfile
    if (dockerfile.is_symlink() or not dockerfile.is_file()
            or not dockerfile.resolve(strict=True).is_relative_to(root)):
        raise ValueError("unsafe Dockerfile path")
    image = _image_metadata(runner(("image", "inspect", spec.image)), spec.image)
    parent = _image_metadata(runner(("image", "inspect", spec.parent)), spec.parent)
    if (image["Architecture"], image["Os"]) != (parent["Architecture"], parent["Os"]):
        raise ValueError("runtime and parent platforms differ")
    prefix = ("run", "--rm", "--network", "none")
    versions = _lines(runner((*prefix, "--entrypoint", "sh", spec.image, "-c", spec.version_command)),
                      "runtime version inventory")
    packages = _lines(runner((*prefix, "--entrypoint", "dpkg-query", spec.image,
                              "-W", "-f=${Package}\\t${Version}\\n")), "package inventory")
    licenses = evidence_files_from_tar(
        runner((*prefix, "--entrypoint", "sh", spec.image, "-c", spec.license_command)))
    missing = missing_package_copyrights(packages, licenses)
    if missing:
        raise ValueError(f"installed packages lack extracted copyright bytes: {', '.join(missing)}")
    artifacts = _artifacts(
        runner((*prefix, "--entrypoint", "sh", spec.image, "-c", spec.artifact_command)))
    return RuntimeEvidence(
        runtime_row=spec.runtime_row,
        image_reference=spec.image,
        image_id=image["Id"],
        platform=f"{image['Os']}/{image['Architecture']}",
        image_created=image["Created"],
        parent_reference=spec.parent,
        parent_image_id=parent["Id"],
        dockerfile=spec.dockerfile,
        dockerfile_sha256=hashlib.sha256(dockerfile.read_bytes()).hexdigest(),
        runtime_versions=versions,
        packages=packages,
        artifacts=artifacts,
        license_files=licenses,
    )


def evidence_files_from_tar(archive: bytes) -> tuple[EvidenceFile, ...]:
    """Read a Docker-produced license archive without accepting links or path traversal."""
    files: list[EvidenceFile] = []
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
            for member in source:
                if not member.isfile():
                    raise ValueError("unsafe nonregular evidence archive entry")
                raw = member.name
                if not _is_canonical_posix_path(raw, absolute=False):
                    raise ValueError("unsafe evidence archive path")
                path = "/" + raw
                if path in seen or member.size > _MAX_EVIDENCE_FILE:
                    raise ValueError("unsafe evidence archive member")
                stream = source.extractfile(member)
                if stream is None:
                    raise ValueError("unsafe unreadable evidence archive member")
                content = stream.read(_MAX_EVIDENCE_FILE + 1)
                if len(content) != member.size:
                    raise ValueError("unsafe evidence archive size")
                total += len(content)
                if total > _MAX_EVIDENCE_TOTAL:
                    raise ValueError("unsafe oversized evidence archive")
                seen.add(path)
                files.append(EvidenceFile(path=path, content=content))
    except tarfile.TarError as error:
        raise ValueError("unsafe evidence archive") from error
    return tuple(sorted(files, key=lambda item: item.path))


def _safe_text(name: str, value: str) -> None:
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"unsafe {name}")


def _safe_list_text(name: str, value: str) -> None:
    if not value or any((ord(character) < 32 and character != "\t") or ord(character) == 127
                        for character in value):
        raise ValueError(f"unsafe {name}")


def _quoted(value: str) -> bytes:
    return json.dumps(value, ensure_ascii=True).encode("ascii")


def _field(parts: list[bytes], name: str, value: str) -> None:
    _safe_text(name, value)
    parts.extend((name.encode("ascii"), b": ", _quoted(value), b"\n"))


def _list(parts: list[bytes], name: str, values: tuple[str, ...]) -> None:
    parts.extend((name.encode("ascii"), b":\n"))
    for value in sorted(values):
        _safe_list_text(name, value)
        parts.extend((b"  - ", _quoted(value), b"\n"))


def render_rights_evidence(evidence: RuntimeEvidence) -> bytes:
    """Render one stable, self-contained evidence file without a wall-clock timestamp."""
    if not _IMAGE_ID.fullmatch(evidence.image_id) or not _IMAGE_ID.fullmatch(evidence.parent_image_id):
        raise ValueError("image identities must be full SHA-256 image IDs")
    if not _SHA256.fullmatch(evidence.dockerfile_sha256):
        raise ValueError("Dockerfile digest must be SHA-256")
    paths = [item.path for item in evidence.license_files]
    if len(paths) != len(set(paths)):
        raise ValueError("license evidence paths must be unique")
    for path in paths:
        if (not _is_canonical_posix_path(path, absolute=True)
                or any(ord(character) < 32 or ord(character) == 127 for character in path)):
            raise ValueError("unsafe license evidence path")
    artifact_names = [name for name, _ in evidence.artifacts]
    if len(artifact_names) != len(set(artifact_names)):
        raise ValueError("artifact names must be unique")
    if any(not _SHA256.fullmatch(digest) for _, digest in evidence.artifacts):
        raise ValueError("artifact digest must be SHA-256")

    parts = [
        b"schema: corsair-runtime-rights-evidence/1\n",
        b"review_status: candidate-evidence-unreviewed\n",
        b"license_conclusion: absent-pending-independent-review\n",
        b"clean_rebuild_identity: not-established\n",
        (b"qualification_blocker: \"The evidence binds the exact collected image ID; "
         b"no stable clean-rebuild image ID is asserted.\"\n"),
        (b"case_binding: \"Cases cite this evidence by runtime row, exact image ID, "
         b"and receipt; the bundle is case-agnostic.\"\n"),
    ]
    for name, value in (
        ("runtime_row", evidence.runtime_row),
        ("image_reference", evidence.image_reference),
        ("image_id", evidence.image_id),
        ("platform", evidence.platform),
        ("image_created", evidence.image_created),
        ("parent_reference", evidence.parent_reference),
        ("parent_image_id", evidence.parent_image_id),
        ("dockerfile", evidence.dockerfile),
        ("dockerfile_sha256", evidence.dockerfile_sha256),
    ):
        _field(parts, name, value)
    _list(parts, "runtime_versions", evidence.runtime_versions)
    _list(parts, "installed_packages", evidence.packages)
    parts.append(b"artifacts:\n")
    for name, digest in sorted(evidence.artifacts):
        _safe_text("artifact name", name)
        if not _is_canonical_posix_path(name, absolute=True):
            raise ValueError("artifact name must be one canonical absolute path")
        parts.extend((b"  - name: ", _quoted(name), b"\n    sha256: ", digest.encode("ascii"), b"\n"))
    parts.append(b"\n")
    for item in sorted(evidence.license_files, key=lambda candidate: candidate.path):
        parts.extend((
            b"--- BEGIN LICENSE FILE ---\npath: ", _quoted(item.path),
            b"\nsha256: ", hashlib.sha256(item.content).hexdigest().encode("ascii"),
            b"\nsize: ", str(len(item.content)).encode("ascii"), b"\ncontent:\n", item.content,
        ))
        if not item.content.endswith(b"\n"):
            parts.append(b"\n")
        parts.append(b"--- END LICENSE FILE ---\n\n")
    return b"".join(parts)


def write_rights_evidence(root: Path, evidence: RuntimeEvidence, *, check: bool = False) -> Path:
    """Write one generated bundle atomically, or verify the checked-in bytes in check mode."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,127}", evidence.runtime_row):
        raise ValueError("unsafe runtime row")
    root = Path(root).resolve(strict=True)
    directory = root / "benchmarks/dataset/evidence/runtime" / evidence.runtime_row
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.resolve(strict=True).is_relative_to(root):
        raise ValueError("unsafe runtime evidence directory")
    destination = directory / "RIGHTS-EVIDENCE.txt"
    content = render_rights_evidence(evidence)
    if check:
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != content:
            raise ValueError(f"runtime rights evidence differs for {evidence.runtime_row}")
        return destination
    if destination.is_symlink():
        raise ValueError("unsafe runtime evidence destination")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".RIGHTS-EVIDENCE.", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def docker_runner(arguments: tuple[str, ...]) -> bytes:
    """Run the managed local Docker client without inheriting endpoint selectors."""
    environment = os.environ.copy()
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(name, None)
    command = ("docker", "--host=unix:///var/run/docker.sock", *arguments)
    completed = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Docker command failed ({arguments[0]}): {detail[:2000]}")
    return completed.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check exact runtime-rights evidence bundles")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="atomically update checked-in evidence")
    mode.add_argument("--check", action="store_true", help="fail if checked-in evidence differs")
    parser.add_argument("--row", action="append", choices=tuple(spec.runtime_row for spec in RUNTIME_SPECS),
                        help="limit collection to a runtime row; repeat for multiple rows")
    args = parser.parse_args(argv)
    selected = tuple(spec for spec in RUNTIME_SPECS if args.row is None or spec.runtime_row in args.row)
    try:
        for spec in selected:
            evidence = collect_runtime_evidence(args.root, spec, runner=docker_runner)
            path = write_rights_evidence(args.root, evidence, check=args.check)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"{spec.runtime_row} {digest} {path.relative_to(args.root.resolve())}")
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"runtime-rights: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
