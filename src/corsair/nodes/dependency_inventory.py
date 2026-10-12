"""SPEC-0026 realized dependency inventory: strict receipt parser and replay comparison (offline).

Paths are relative to the operator script's per-ecosystem root (Python environment prefix, Maven
local repository, JavaScript project directory). Coverage for Ruby and Perl is not yet defined.
"""
from dataclasses import dataclass
from fnmatch import fnmatchcase
import re
from types import MappingProxyType

from corsair.adapters.git_source import confined_path
from corsair.ports.artifacts import ArtifactRef

# Operator-owned bookkeeping compared by presence only. A pattern without '/' matches the basename;
# one with '/' must equal the path.
GENERATED_PATHS = MappingProxyType({
    'python': (),
    'java': ('_remote.repositories', '*.lastUpdated', 'resolver-status.properties', 'maven-metadata-*.xml'),
    'javascript': ('node_modules/.package-lock.json',),
})
# Generation is prevented natively (--no-compile, PYTHONDONTWRITEBYTECODE=1); any component matching is refused.
PREVENTED_PATHS = MappingProxyType({'python': ('__pycache__', '*.pyc', '*.pyo')})


def generated(ecosystem: str, path: str) -> bool:
    return any(path == p if '/' in p else fnmatchcase(path.rsplit('/', 1)[-1], p) for p in GENERATED_PATHS[ecosystem])


@dataclass(frozen=True)
class DependencyInventory:
    ecosystem: str
    image: str
    files: tuple[tuple[str, ArtifactRef], ...]
    generated: tuple[str, ...]


@dataclass(frozen=True)
class InventoryDrift:
    image_changed: bool
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not (self.image_changed or self.added or self.removed or self.changed)


LINE = re.compile(r'(?:file ([0-9a-f]{64}) (0|[1-9][0-9]*)|generated) ((?:[0-9a-f]{2})+)')


def parse_inventory(stdout: bytes, ecosystem: str, max_entries: int) -> DependencyInventory:
    if ecosystem not in GENERATED_PATHS: raise ValueError('Unknown or not yet covered ecosystem')
    if not isinstance(stdout, bytes) or not stdout.endswith(b'\n'): raise ValueError('Complete LF receipt required')
    lines = stdout[:-1].split(b'\n')
    if len(lines) < 3 or len(lines) - 3 > max_entries: raise ValueError('Receipt missing lines or inventory over bound')
    try: lines = [line.decode('ascii') for line in lines]
    except UnicodeDecodeError: raise ValueError('ASCII receipt required') from None
    image, end = re.fullmatch('image (sha256:[0-9a-f]{64})', lines[1]), re.fullmatch('end (0|[1-9][0-9]*)', lines[-1])
    if lines[0] != 'corsair-dependency-inventory v1 ' + ecosystem or not image or not end:
        raise ValueError('Malformed inventory header, image digest or trailer')
    files, extra, previous = [], [], ''
    for line in lines[2:-1]:
        match = LINE.fullmatch(line)
        if not match: raise ValueError('Malformed inventory line or missing digest')
        digest, size, hexpath = match.groups()
        if hexpath <= previous: raise ValueError('Inventory not strictly sorted or duplicated')
        previous = hexpath
        try: path = bytes.fromhex(hexpath).decode('utf8')
        except UnicodeDecodeError: raise ValueError('UTF8 path required') from None
        confined_path(path)
        if any(fnmatchcase(part, p) for part in path.split('/') for p in PREVENTED_PATHS.get(ecosystem, ())):
            raise ValueError('Prevented generated file present: ' + path)
        if (digest is None) != generated(ecosystem, path): raise ValueError('Generated classification mismatch: ' + path)
        if digest is None: extra.append(path)
        else: files.append((path, ArtifactRef(digest, int(size))))
    if int(end[1]) != len(files) + len(extra): raise ValueError('Inventory count mismatch')
    return DependencyInventory(ecosystem, image[1], tuple(files), tuple(extra))


def compare_inventories(recorded: DependencyInventory, replayed: DependencyInventory) -> InventoryDrift:
    if recorded.ecosystem != replayed.ecosystem: raise ValueError('Inventories of different ecosystems')
    old = dict(recorded.files) | {p: None for p in recorded.generated}
    new = dict(replayed.files) | {p: None for p in replayed.generated}
    return InventoryDrift(recorded.image != replayed.image, tuple(sorted(new.keys() - old.keys())),
                          tuple(sorted(old.keys() - new.keys())),
                          tuple(sorted(p for p in old.keys() & new.keys() if old[p] != new[p])))
