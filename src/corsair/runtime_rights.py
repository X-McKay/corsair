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
import selectors
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from email.parser import BytesParser


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_EVIDENCE_FILE = 16 * 1024 * 1024
_MAX_EVIDENCE_TOTAL = 64 * 1024 * 1024


@dataclass(frozen=True)
class EvidenceFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class ImageFileFact:
    path: str
    resolved_path: str
    kind: str
    link_target: str | None
    sha256: str


@dataclass(frozen=True)
class EvidenceReference:
    source_path: str
    source_sha256: str
    byte_start: int
    byte_end: int
    raw_reference: str
    reference_kind: str
    requested_path: str | None
    candidate_paths: tuple[str, ...]
    status: str
    target_path: str | None
    target_sha256: str | None
    reason: str


@dataclass(frozen=True)
class InputComparison:
    image_path: str
    repository_path: str
    image_sha256: str
    repository_sha256: str
    byte_identical: bool


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
    configured_image_reference: str = ""
    rootfs_diff_ids: tuple[str, ...] = ()
    parent_rootfs_diff_ids: tuple[str, ...] = ()
    input_files: tuple[EvidenceFile, ...] = ()
    file_facts: tuple[ImageFileFact, ...] = ()
    references: tuple[EvidenceReference, ...] = ()
    input_comparisons: tuple[InputComparison, ...] = ()
    observations: tuple[str, ...] = ()
    remaining_blockers: tuple[str, ...] = ()


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
_TAR_FILES = ("tar --null --verbatim-files-from --files-from=- "
              "--create --dereference --hard-dereference --file=-")
_ARCHIVE_FILES = "LC_ALL=C sort -zu | " + _TAR_FILES


def _license_command(*sources: str) -> str:
    # Enumerate links themselves: following them here would silently omit
    # dangling or nonregular targets before archive/fact validation can reject them.
    discovery = " && ".join((_COPYRIGHT_FILES,
                              r"find /usr/share/common-licenses -maxdepth 1 \( -type f -o -type l \) -print0",
                              *sources))
    # POSIX sh reports only the last pipeline stage. Keep the binary archive on
    # fd 3 and collect every stage's status on fd 4, without files or pipefail.
    # Status arrival order is immaterial: success requires exactly three zeros.
    return ("{ statuses=$( { "
            "{ " + discovery + "; printf '%s\\n' \"$?\" >&4; } | "
            "{ LC_ALL=C sort -zu; printf '%s\\n' \"$?\" >&4; } | "
            "{ " + _TAR_FILES + " >&3; printf '%s\\n' \"$?\" >&4; }"
            " ; } 4>&1 ); [ \"$statuses\" = '0\n0\n0' ]; } 3>&1")


RUNTIME_SPECS = (
    RuntimeSpec(
        runtime_row="pytest-cpython312",
        image="corsair-lite-python:dev",
        parent="docker.io/library/python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704",
        dockerfile="images/python/Dockerfile",
        version_command="python -B --version; python -B -m pip freeze --all",
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
    try:
        value.encode("utf-8")
    except (UnicodeEncodeError, AttributeError):
        return False
    if (not value or value == "/" or value.startswith("//")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
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


def _image_metadata(raw: bytes, reference: str) -> dict:
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
    rootfs = item.get("RootFS")
    if (not isinstance(rootfs, dict) or rootfs.get("Type") != "layers"
            or not isinstance(rootfs.get("Layers"), list)
            or any(not isinstance(layer, str) or not _IMAGE_ID.fullmatch(layer)
                   for layer in rootfs["Layers"])):
        raise ValueError(f"invalid Docker RootFS metadata for {reference}")
    return {**{name: item[name] for name in required}, "diff_ids": tuple(rootfs["Layers"])}


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


# Fixed programs receive paths as positional arguments, never shell source.
_PATH_ARCHIVE_COMMAND = ('printf "%s\\0" "$@" | ' + _ARCHIVE_FILES)
_FACT_COMMAND = r'''set -eu
for path do
    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        printf '%s\0absent\0\0\0\0\0' "$path"
        continue
    fi
    resolved=$(readlink -e -- "$path")
    [ -f "$resolved" ] || exit 1
    printf '%s\0present\0%s\0' "$path" "$resolved"
    if [ -L "$path" ]; then
        printf 'symlink\0'
        readlink -z -- "$path"
    else
        printf 'regular\0\0'
    fi
    digest=$(sha256sum -- "$path")
    printf '%s\0' "${digest%% *}"
done'''
_NODE_SQLITE_COMMAND = '''const {DatabaseSync}=require('node:sqlite');
const db=new DatabaseSync(':memory:');
console.log(JSON.stringify(db.prepare('SELECT sqlite_version() AS sqlite_version, sqlite_source_id() AS sqlite_source_id').get()));
db.close();'''
_NODE_PATH_COMMAND = '''set -eu
for path in /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-v1.22.22 /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg; do
    if [ -e "$path" ] || [ -L "$path" ]; then state=present; else state=absent; fi
    printf 'path:%s=%s\\n' "$path" "$state"
done
for name in npm npx corepack yarn yarnpkg; do
    if command -v "$name" >/dev/null 2>&1; then state=present; else state=absent; fi
    printf 'launcher:%s=%s\\n' "$name" "$state"
done'''
_SCAN_SCOPE = ('reference_scan_scope=absolute-image-paths,License-File-headers,ancillary-notice-names,'
               'external-URLs;semantic-completeness=not-established')
_COMMON_BLOCKERS = (
    'package/source applicability unresolved', 'complete layered-distribution coverage unresolved',
    'distribution obligations/source delivery unresolved', 'independent rights review unresolved',
    'clean-rebuild identity unresolved',
)
_ROW_BLOCKERS = {
    'pytest-cpython312': ('patched pip-vendor provenance/terms unresolved',
                          'retained ensurepip wheel coverage unresolved'),
    'node-test-node22': ('exact SQLite source/notice provenance unresolved',
                         'inherited npm/Corepack/Yarn/dependency/layer coverage unresolved'),
    'javac-java21': ('GCC documentation/runtime exceptions unresolved',
                     'JDK module/Classpath/assembly applicability unresolved'),
    'perl-tap-540': ('mixed core/module clauses/exceptions unresolved',
                     'alias-to-owner/source mapping unresolved',
                     'independently authenticated package archive hashes unresolved'),
}


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _repository_bytes(root: Path, relative: str) -> bytes:
    if not _is_canonical_posix_path(relative, absolute=False):
        raise ValueError('unsafe repository path')
    path = root
    for part in relative.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('unsafe repository symlink component')
    if not path.is_file() or not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError('unsafe repository file')
    with path.open('rb') as stream:
        content = stream.read(_MAX_EVIDENCE_FILE + 1)
    if len(content) > _MAX_EVIDENCE_FILE:
        raise ValueError('oversized repository input')
    return content


def _file_facts(raw: bytes, paths: tuple[str, ...]) -> tuple[tuple[ImageFileFact, ...], set[str]]:
    if len(raw) > _MAX_EVIDENCE_TOTAL:
        raise ValueError('oversized file facts')
    try:
        fields = raw.decode('utf-8').split('\0')
    except UnicodeDecodeError as error:
        raise ValueError('invalid UTF-8 file facts') from error
    if fields[-1] != '' or (len(fields) - 1) % 6:
        raise ValueError('invalid file fact framing')
    facts = []
    absent = set()
    seen = set()
    for offset in range(0, len(fields) - 1, 6):
        path, state, resolved, kind, link, digest = fields[offset:offset + 6]
        if path not in paths or path in seen:
            raise ValueError('duplicate or unexpected file fact')
        seen.add(path)
        if state == 'absent':
            if any((resolved, kind, link, digest)):
                raise ValueError('invalid absent file fact')
            absent.add(path)
        elif state == 'present':
            if (not _is_canonical_posix_path(resolved, absolute=True)
                    or kind not in ('regular', 'symlink') or not _SHA256.fullmatch(digest)
                    or (kind == 'regular' and link) or (kind == 'symlink' and not link)):
                raise ValueError('unsafe file fact')
            facts.append(ImageFileFact(path, resolved, kind, link if kind == 'symlink' else None, digest))
        else:
            raise ValueError('invalid file fact existence state')
    if seen != set(paths):
        raise ValueError('missing file facts')
    return tuple(sorted(facts, key=lambda fact: fact.path)), absent


def _metadata_declarations(files: tuple[EvidenceFile, ...]) -> tuple:
    declarations = []
    for source in files:
        if not source.path.endswith('.dist-info/METADATA'):
            continue
        try:
            source.content.decode('utf-8')
        except UnicodeDecodeError:
            continue  # the prose scan records exact unparsed-source bytes
        parsed = BytesParser().parsebytes(source.content, headersonly=True)
        headers = parsed.get_all('License-File', [])
        spans = []
        offset = 0
        current = None
        for line in source.content.splitlines(keepends=True):
            if line in (b'\n', b'\r\n'):
                break
            if line.startswith((b' ', b'\t')) and current is not None:
                current[1] = offset + len(line.rstrip(b'\r\n'))
            else:
                current = None
                if line.lower().startswith(b'license-file:'):
                    start = offset + len(b'license-file:')
                    while start < offset + len(line) and source.content[start:start+1] in (b' ', b'\t'):
                        start += 1
                    current = [start, offset + len(line.rstrip(b'\r\n'))]
                    spans.append(current)
            offset += len(line)
        if len(headers) != len(spans):
            raise ValueError('ambiguous License-File header framing')
        for header, (start, end) in zip(headers, spans):
            # RFC unfolding replaces a fold with whitespace, not concatenation.
            value = re.sub(r'\r?\n[ \t]+', ' ', str(header)).strip(' \t')
            if (not _is_canonical_posix_path(value, absolute=False)
                    or any(character in value for character in '*?[]')):
                raise ValueError('unsafe metadata License-File declaration')
            directory = source.path.rsplit('/', 1)[0]
            candidates = tuple(sorted({directory + '/' + value, directory + '/licenses/' + value}))
            raw = source.content[start:end].decode('utf-8')
            declarations.append((source, start, end, raw, candidates))
    return tuple(declarations)


def _reference_key(ref: EvidenceReference) -> tuple:
    return (ref.source_path, ref.byte_start, ref.byte_end, ref.reference_kind,
            ref.raw_reference, ref.candidate_paths)


def _reference(source: EvidenceFile, start: int, end: int, raw: str, kind: str,
               candidates: tuple[str, ...], files: dict[str, EvidenceFile], absent: set[str],
               *, requested: str | None) -> EvidenceReference:
    found = [path for path in candidates if path in files]
    target = found[0] if len(found) == 1 else None
    if len(found) > 1:
        status, reason = 'unresolved-ambiguous', 'multiple-embedded-candidates'
    elif target is not None:
        status, reason = 'embedded', 'byte-availability-only'
    elif kind != 'ancillary-name' and candidates and all(path in absent for path in candidates):
        status, reason = 'unresolved-missing', 'probed-absent'
    else:
        status, reason = 'unresolved-unsupported', 'outside-phase-a-collection'
    return EvidenceReference(source.path, _digest(source.content), start, end, raw, kind,
                             requested, tuple(sorted(set(candidates))), status, target,
                             _digest(files[target].content) if target else None, reason)


# Tokens retain observed punctuation in the source span. Only a final period,
# comma or semicolon at a token boundary, or a matching bracket/curly quote/backtick,
# supplies an additional candidate; the literal spelling is never discarded.
_TOKEN = re.compile(rb'https?://[^\s<>"\x27]+|(?<![\w:/])/(?!/)[^\s<>"\x27]+|\b(?:AUTHORS|NOTICE|COPYING)(?:\.[A-Za-z0-9_-]+)?\b')


def _scan_references(files: tuple[EvidenceFile, ...], *, absent: set[str] | None = None) -> tuple[EvidenceReference, ...]:
    absent = absent or set()
    by_path = {item.path: item for item in files}
    result = []
    metadata_spans = {(s.path, start, end) for s, start, end, _, _ in _metadata_declarations(files)}
    for source in files:
        try:
            source.content.decode('utf-8')
        except UnicodeDecodeError:
            result.append(EvidenceReference(source.path, _digest(source.content), 0, 0, '',
                'unparsed-source', None, (), 'unresolved-non-utf8', None, None, 'source-is-not-UTF-8'))
            continue
        for match in _TOKEN.finditer(source.content):
            if len(result) >= _MAX_EVIDENCE_TOTAL // 128:
                raise ValueError('oversized reference count')
            start, end = match.span()
            if any(path == source.path and begin <= start < finish for path, begin, finish in metadata_spans):
                continue
            raw = match.group().decode('utf-8')
            if raw.startswith(('http://', 'https://')):
                result.append(EvidenceReference(source.path, _digest(source.content), start, end, raw,
                    'external-url', None, (), 'unresolved-external', None, None, 'external-not-fetched'))
                continue
            if raw.startswith('/'):
                kind = 'absolute-path'
                candidates = {raw}
                parsed = raw
                if parsed[-1:] in ('.', ',', ';'):
                    parsed = parsed[:-1]
                closing = {')': b'(', ']': b'[', '}': b'{', '’': '‘'.encode(), '”': '“'.encode(), '`': b'`'}
                opening = closing.get(parsed[-1:])
                if opening and source.content[:start].endswith(opening):
                    parsed = parsed[:-1]
                candidates.add(parsed)
                candidates = tuple(sorted(path for path in candidates if _is_canonical_posix_path(path, absolute=True)))
                requested = parsed if _is_canonical_posix_path(parsed, absolute=True) else None
            else:
                kind = 'ancillary-name'
                requested = source.path.rsplit('/', 1)[0] + '/' + raw
                candidates = (requested,)
            ref = _reference(source, start, end, raw, kind, candidates, by_path, absent, requested=requested)
            # Delimiter alternatives do not make a proven missing canonical path
            # unknown merely because punctuation itself was not probed.
            if ref.status == 'unresolved-unsupported' and kind == 'absolute-path' and requested in absent:
                ref = EvidenceReference(source.path, ref.source_sha256, start, end, raw, kind, requested,
                    candidates, 'unresolved-missing', None, None, 'probed-absent')
            result.append(ref)
    return tuple(sorted(result, key=_reference_key))


def _validate_evidence(evidence: RuntimeEvidence) -> None:
    files = (*evidence.license_files, *evidence.input_files)
    if sum(len(item.content) for item in files) > _MAX_EVIDENCE_TOTAL:
        raise ValueError('oversized combined evidence files')
    if any(len(item.content) > _MAX_EVIDENCE_FILE for item in files):
        raise ValueError('oversized evidence file')
    paths = [item.path for item in files]
    if len(paths) != len(set(paths)):
        raise ValueError('evidence paths must be unique across collections')
    if any(not _is_canonical_posix_path(path, absolute=True) for path in paths):
        raise ValueError('unsafe evidence path')
    by_path = {item.path: item for item in files}
    inputs = {item.path: item for item in evidence.input_files}
    for layers in (evidence.rootfs_diff_ids, evidence.parent_rootfs_diff_ids):
        if any(not _IMAGE_ID.fullmatch(layer) for layer in layers):
            raise ValueError('invalid rootfs diff ID')
    for records, key in ((evidence.file_facts, lambda fact: fact.path),
                         (evidence.references, lambda ref: (ref.source_path, ref.byte_start, ref.byte_end, ref.reference_kind)),
                         (evidence.input_comparisons, lambda item: (item.image_path, item.repository_path))):
        keys = [key(record) for record in records]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate structured record key')
    for fact in evidence.file_facts:
        if (fact.path not in by_path or _digest(by_path[fact.path].content) != fact.sha256
                or not _is_canonical_posix_path(fact.resolved_path, absolute=True)
                or fact.kind not in ('regular', 'symlink')
                or (fact.kind == 'regular' and fact.link_target is not None)
                or (fact.kind == 'symlink' and not fact.link_target)):
            raise ValueError('invalid file fact edge')
        if fact.resolved_path in by_path and _digest(by_path[fact.resolved_path].content) != fact.sha256:
            raise ValueError('resolved file fact digest mismatch')
    for ref in evidence.references:
        if (ref.source_path not in by_path or ref.source_path in inputs
                or _digest(by_path[ref.source_path].content) != ref.source_sha256):
            raise ValueError('invalid reference source digest edge')
        content = by_path[ref.source_path].content
        if not 0 <= ref.byte_start <= ref.byte_end <= len(content):
            raise ValueError('invalid reference byte span')
        if ref.reference_kind == 'unparsed-source':
            try:
                content.decode('utf-8')
            except UnicodeDecodeError:
                pass
            else:
                raise ValueError('unparsed non-UTF-8 reference has UTF-8 source')
            if (ref.status != 'unresolved-non-utf8' or ref.raw_reference != ''
                    or (ref.byte_start, ref.byte_end) != (0, 0)):
                raise ValueError('invalid unparsed-source record')
        elif content[ref.byte_start:ref.byte_end] != ref.raw_reference.encode('utf-8'):
            raise ValueError('reference byte span does not reproduce raw reference')
        if ref.reference_kind not in ('absolute-path', 'metadata-license-file', 'ancillary-name', 'external-url', 'unparsed-source'):
            raise ValueError('invalid reference kind')
        if ref.status not in ('embedded', 'unresolved-missing', 'unresolved-ambiguous', 'unresolved-external', 'unresolved-unsupported', 'unresolved-non-utf8'):
            raise ValueError('invalid reference status')
        if tuple(sorted(set(ref.candidate_paths))) != ref.candidate_paths:
            raise ValueError('invalid reference candidate ordering')
        for path in (*ref.candidate_paths, ref.requested_path, ref.target_path):
            if path is not None and not _is_canonical_posix_path(path, absolute=True):
                raise ValueError('unsafe reference path')
        if ref.status == 'embedded':
            if (ref.target_path not in by_path or ref.target_path not in ref.candidate_paths
                    or _digest(by_path[ref.target_path].content) != ref.target_sha256):
                raise ValueError('invalid reference target digest edge')
        elif ref.target_path is not None or ref.target_sha256 is not None:
            raise ValueError('unresolved reference has selected target')
    for comparison in evidence.input_comparisons:
        if (comparison.image_path not in inputs
                or _digest(inputs[comparison.image_path].content) != comparison.image_sha256
                or not _is_canonical_posix_path(comparison.repository_path, absolute=False)
                or not _SHA256.fullmatch(comparison.repository_sha256)
                or comparison.byte_identical != (comparison.image_sha256 == comparison.repository_sha256)):
            raise ValueError('invalid input comparison edge')
    structured_size = sum(len(json.dumps(asdict(record), ensure_ascii=True)) for record in
                          (*evidence.file_facts, *evidence.references, *evidence.input_comparisons))
    structured_size += sum(len(value.encode('utf-8')) for value in (*evidence.observations, *evidence.remaining_blockers))
    if structured_size + sum(len(item.content) for item in files) > _MAX_EVIDENCE_TOTAL:
        raise ValueError('oversized structured evidence')


def _json_list(parts: list[bytes], name: str, values) -> None:
    parts.append(name.encode('ascii') + b':\n')
    for value in values:
        parts.append(b'  - ' + json.dumps(value, sort_keys=True, ensure_ascii=True,
                                        separators=(',', ':')).encode('ascii') + b'\n')


def collect_runtime_evidence(root: Path, spec: RuntimeSpec, *, runner: CommandRunner,
                             image_id: str | None = None) -> RuntimeEvidence:
    """Observe one frozen image; unresolved references never become rights conclusions."""
    if image_id is not None and not _IMAGE_ID.fullmatch(image_id):
        raise ValueError("override must be a full SHA-256 image ID")
    root = Path(root).resolve(strict=True)
    dockerfile_bytes = _repository_bytes(root, spec.dockerfile)
    budget = 0

    def run(arguments: tuple[str, ...]) -> bytes:
        nonlocal budget
        result = runner(arguments)
        budget += len(result)
        if budget > _MAX_EVIDENCE_TOTAL:
            raise ValueError("oversized aggregate acquisition responses")
        return result

    selected = image_id if image_id is not None else spec.image
    image = _image_metadata(run(("image", "inspect", selected)), selected)
    frozen = image["Id"]
    if image_id is not None and image_id != frozen:
        raise ValueError("inspected image ID differs from override")
    parent = _image_metadata(run(("image", "inspect", spec.parent)), spec.parent)
    if (image["Architecture"], image["Os"]) != (parent["Architecture"], parent["Os"]):
        raise ValueError("runtime and parent platforms differ")
    prefix = ("run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
              "--security-opt", "no-new-privileges")

    def shell(command: str, paths: tuple[str, ...] = ()) -> bytes:
        suffix = ("--", *paths) if paths else ()
        return run((*prefix, "--entrypoint", "sh", frozen, "-c", command, *suffix))

    versions = _lines(shell(spec.version_command), "runtime version inventory")
    packages = _lines(run((*prefix, "--entrypoint", "dpkg-query", frozen,
                          "-W", "-f=${Package}\\t${Version}\\n")), "package inventory")
    licenses = evidence_files_from_tar(shell(spec.license_command))
    missing = missing_package_copyrights(packages, licenses)
    if missing:
        raise ValueError(f"installed packages lack extracted copyright bytes: {', '.join(missing)}")
    artifacts = _artifacts(shell(spec.artifact_command))
    declarations = _metadata_declarations(licenses)  # validate ALL before any candidate probe
    all_candidates = {path for _, _, _, _, candidates in declarations for path in candidates}
    common = {item.path for item in licenses if item.path.startswith("/usr/share/common-licenses/")}
    # Only known common-directory references get existence probes; arbitrary prose
    # references are not an instruction to read additional filesystem locations.
    for ref in _scan_references(licenses):
        common.update(path for path in ref.candidate_paths
                      if ref.reference_kind == "absolute-path"
                      and str(PurePosixPath(path).parent) == "/usr/share/common-licenses")
    probe_paths = tuple(sorted(common | all_candidates))
    facts, absent = _file_facts(shell(_FACT_COMMAND, probe_paths), probe_paths) if probe_paths else ((), set())
    existing = {fact.path for fact in facts}
    known = {item.path: item for item in licenses}
    acquire = tuple(sorted(existing - known.keys()))
    if acquire:
        # Common reference paths outside the fixed initial common inventory are
        # facts only; only declared candidates expand the notice acquisition set.
        acquire = tuple(path for path in acquire if path in all_candidates)
    if acquire:
        additions = evidence_files_from_tar(shell(_PATH_ARCHIVE_COMMAND, acquire))
        if {item.path for item in additions} != set(acquire):
            raise ValueError("declared-file archive does not match requested paths")
        known.update((item.path, item) for item in additions)
    licenses = tuple(sorted(known.values(), key=lambda item: item.path))
    facts = tuple(fact for fact in facts if fact.path in known)
    refs = list(_scan_references(licenses, absent=absent))
    for source, start, end, raw, candidates in declarations:
        refs.append(_reference(source, start, end, raw, "metadata-license-file", candidates,
                               known, absent, requested=None))
    refs = tuple(sorted(refs, key=_reference_key))
    inputs: tuple[EvidenceFile, ...] = ()
    comparisons: tuple[InputComparison, ...] = ()
    observations = [_SCAN_SCOPE]
    blockers = list(_COMMON_BLOCKERS + _ROW_BLOCKERS.get(spec.runtime_row, ()))
    input_path = {"pytest-cpython312": "/usr/local/lib/python3.12/site-packages/pip/_vendor/vendor.txt",
                  "perl-tap-540": "/opt/corsair/packages.lock"}.get(spec.runtime_row)
    if input_path:
        inputs = evidence_files_from_tar(shell(_PATH_ARCHIVE_COMMAND, (input_path,)))
        if len(inputs) != 1 or inputs[0].path != input_path:
            raise ValueError("required installed input file is missing")
    if spec.runtime_row == "perl-tap-540":
        repository_path = "images/perl/packages.lock"
        repository = _repository_bytes(root, repository_path)
        installed = inputs[0].content
        comparisons = (InputComparison(input_path, repository_path, _digest(installed),
                                       _digest(repository), installed == repository),)
        artifacts = tuple(sorted((*artifacts, (input_path, _digest(installed)))))
        if installed != repository:
            blockers.append("installed/repository Perl packages.lock mismatch")
    if spec.runtime_row == "node-test-node22":
        sqlite = json.loads(run((*prefix, "--entrypoint", "node", frozen, "-e", _NODE_SQLITE_COMMAND)))
        if not isinstance(sqlite, dict) or set(sqlite) != {"sqlite_version", "sqlite_source_id"}:
            raise ValueError("invalid SQLite identity result")
        for key, value in sorted(sqlite.items()):
            if not isinstance(value, str):
                raise ValueError("invalid SQLite identity value")
            _safe_text("SQLite identity", value)
            observations.append(f"{key}={value}")
        for value in _lines(shell(_NODE_PATH_COMMAND), "Node final-tree facts"):
            if not re.fullmatch(r"(?:path:/[^=]+|launcher:[a-z]+)=(?:present|absent)", value):
                raise ValueError("invalid Node final-tree fact")
            observations.append(value)
            if value.endswith("=present"):
                blockers.append("Node final-tree material remains present: " + value)
    blockers.extend(f"{ref.status}: {ref.source_path}:{ref.byte_start}:{ref.reference_kind}: {ref.raw_reference}"
                    for ref in refs if ref.status != "embedded")
    evidence = RuntimeEvidence(
        runtime_row=spec.runtime_row, image_reference=selected, configured_image_reference=spec.image,
        image_id=frozen, platform=f"{image['Os']}/{image['Architecture']}", image_created=image["Created"],
        parent_reference=spec.parent, parent_image_id=parent["Id"],
        rootfs_diff_ids=image["diff_ids"], parent_rootfs_diff_ids=parent["diff_ids"],
        dockerfile=spec.dockerfile, dockerfile_sha256=_digest(dockerfile_bytes),
        runtime_versions=versions, packages=packages, artifacts=artifacts, license_files=licenses,
        input_files=inputs, file_facts=facts, references=refs, input_comparisons=comparisons,
        observations=tuple(sorted(set(observations))), remaining_blockers=tuple(sorted(set(blockers))),
    )
    _validate_evidence(evidence)
    return evidence


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
    _validate_evidence(evidence)
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
        b"schema: corsair-runtime-rights-evidence/2\n",
        b'observation_scope: "merged-filesystem-and-image-metadata"\n',
        b'layer_coverage: "not-collected"\n',
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
        ("configured_image_reference", evidence.configured_image_reference or evidence.image_reference),
        ("image_id", evidence.image_id),
        ("platform", evidence.platform),
        ("image_created", evidence.image_created),
        ("parent_reference", evidence.parent_reference),
        ("parent_image_id", evidence.parent_image_id),
        ("dockerfile", evidence.dockerfile),
        ("dockerfile_sha256", evidence.dockerfile_sha256),
    ):
        _field(parts, name, value)
    _json_list(parts, "rootfs_diff_ids", evidence.rootfs_diff_ids)
    _json_list(parts, "parent_rootfs_diff_ids", evidence.parent_rootfs_diff_ids)
    _json_list(parts, "file_facts", (asdict(item) for item in sorted(evidence.file_facts, key=lambda item: item.path)))
    _json_list(parts, "references", (asdict(item) for item in sorted(evidence.references, key=_reference_key)))
    _json_list(parts, "input_comparisons", (asdict(item) for item in sorted(evidence.input_comparisons,
               key=lambda item: (item.image_path, item.repository_path))))
    _json_list(parts, "observations", ({"text": value} for value in sorted(set(evidence.observations))))
    _json_list(parts, "remaining_blockers", ({"text": value} for value in sorted(set(evidence.remaining_blockers))))
    _list(parts, "runtime_versions", evidence.runtime_versions)
    _list(parts, "installed_packages", evidence.packages)
    parts.append(b"artifacts:\n")
    for name, digest in sorted(evidence.artifacts):
        _safe_text("artifact name", name)
        if not _is_canonical_posix_path(name, absolute=True):
            raise ValueError("artifact name must be one canonical absolute path")
        parts.extend((b"  - name: ", _quoted(name), b"\n    sha256: ", digest.encode("ascii"), b"\n"))
    parts.append(b"\n")
    for kind, files in (("LICENSE", evidence.license_files), ("INPUT", evidence.input_files)):
        for item in sorted(files, key=lambda candidate: candidate.path):
            parts.extend((
                f"--- BEGIN {kind} FILE ---\norigin: image\npath: ".encode("ascii"), _quoted(item.path),
                b"\nsha256: ", _digest(item.content).encode("ascii"),
                b"\nsize: ", str(len(item.content)).encode("ascii"), b"\ncontent:\n", item.content,
            ))
            if not item.content.endswith(b"\n"):
                parts.append(b"\n")
            parts.append(f"--- END {kind} FILE ---\n\n".encode("ascii"))
    if sum(map(len, parts)) > _MAX_EVIDENCE_TOTAL:
        raise ValueError("oversized rendered evidence")
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
    # Drain both pipes incrementally; communicate()/run() would allocate an
    # unbounded response before the acquisition budget could reject it.
    stdout = bytearray()
    stderr = bytearray()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, stdout)
                selector.register(process.stderr, selectors.EVENT_READ, stderr)
                total = 0
                while selector.get_map():
                    for key, _ in selector.select():
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > _MAX_EVIDENCE_TOTAL:
                            raise ValueError("oversized Docker subprocess output")
                        key.data.extend(chunk)
            returncode = process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise
    if returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Docker command failed ({arguments[0]}): {detail[:2000]}")
    return bytes(stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check exact runtime-rights evidence bundles")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="atomically update checked-in evidence")
    mode.add_argument("--check", action="store_true", help="fail if checked-in evidence differs")
    parser.add_argument("--row", action="append", choices=tuple(spec.runtime_row for spec in RUNTIME_SPECS),
                        help="limit collection to a runtime row; repeat for multiple rows")
    parser.add_argument("--image-id", action="append", default=[], metavar="ROW=sha256:...",
                        help="collect an existing immutable image ID for a runtime row")
    args = parser.parse_args(argv)
    selected = tuple(spec for spec in RUNTIME_SPECS if args.row is None or spec.runtime_row in args.row)
    try:
        overrides = {}
        for assignment in args.image_id:
            row, separator, identity = assignment.partition("=")
            if (not separator or row not in {spec.runtime_row for spec in selected}
                    or row in overrides or not _IMAGE_ID.fullmatch(identity)):
                raise ValueError("invalid, duplicate, or unselected --image-id override")
            overrides[row] = identity
        for spec in selected:
            evidence = collect_runtime_evidence(args.root, spec, runner=docker_runner,
                                                image_id=overrides.get(spec.runtime_row))
            path = write_rights_evidence(args.root, evidence, check=args.check)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"{spec.runtime_row} {digest} {path.relative_to(args.root.resolve())}")
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"runtime-rights: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
