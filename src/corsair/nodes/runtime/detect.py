"""SPEC-0042 entry point: select a project's build files and derive its runtime requirement, deterministically.

`is_build_file` lets a caller pick the few files it needs from a captured snapshot manifest; `detect` takes
those bytes (never a live checkout) and returns a `RuntimeRequirement`. Language comes from the caller when
known (a case's agent-visible language); otherwise exactly one ecosystem must be present at the root.
"""
from fnmatch import fnmatchcase
from typing import Mapping

from corsair.nodes.runtime import java, javascript, perl, python, ruby
from corsair.nodes.runtime.contracts import Language, RuntimeRequirement
from corsair.nodes.runtime.declarations import Collector, combine

MAX_FILE_BYTES = 1 << 20
MAX_FILES = 4096
# Basename patterns at any depth (Maven reactors nest POMs) and exact repository-relative paths.
ANYWHERE = ('pom.xml',)
ROOT = ('pyproject.toml', 'setup.py', 'setup.cfg', 'requirements*.txt', 'requirements*.in', 'Pipfile', 'Pipfile.lock',
        'poetry.lock', 'uv.lock', '.python-version', 'runtime.txt', 'tox.ini', 'pytest.ini', 'build.gradle',
        'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts', '.java-version', '.sdkmanrc', '.tool-versions',
        'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', '.nvmrc', '.node-version', 'Gemfile',
        'Gemfile.lock', '*.gemspec', '.ruby-version', 'Makefile.PL', 'Build.PL', 'cpanfile', 'META.json', 'META.yml',
        'dist.ini', '.travis.yml', 'appveyor.yml', 'Jenkinsfile', 'requirements/*.txt', 'requirements/*.in',
        '.mvn/wrapper/maven-wrapper.properties', 'gradle/wrapper/gradle-wrapper.properties', '.github/workflows/*.yml',
        '.github/workflows/*.yaml')
# Root-only names whose leading `*` must not cross directories (test-requirements.txt, dev_requirements.in).
TOP = ('*-requirements*.txt', '*_requirements*.txt', '*-requirements*.in', '*_requirements*.in')
MARKERS: dict[Language, tuple[str, ...]] = {
    'python': ('pyproject.toml', 'setup.py', 'setup.cfg', 'Pipfile', 'requirements.txt', 'tox.ini'),
    'java': ('pom.xml', 'build.gradle', 'build.gradle.kts'),
    'javascript': ('package.json',),
    'ruby': ('Gemfile', '*.gemspec'),
    'perl': ('Makefile.PL', 'Build.PL', 'cpanfile', 'dist.ini'),
}


def is_build_file(path: str) -> bool:
    """Whether `path` (relative to the project root, '/'-separated) is build metadata the detector reads."""
    if '/node_modules/' in f'/{path}' or path.startswith('/'): return False
    name = path.rsplit('/', 1)[-1]
    return any(fnmatchcase(name, p) for p in ANYWHERE) or any(fnmatchcase(path, p) for p in ROOT) or \
        ('/' not in path and any(fnmatchcase(path, p) for p in TOP))


def languages(paths) -> tuple[Language, ...]:
    names = {p for p in paths if '/' not in p}
    return tuple(language for language, markers in MARKERS.items()
                 if any(fnmatchcase(n, m) for n in names for m in markers))


def detect(files: Mapping[str, bytes], language: Language | None = None, *, root: str = '.',
           parents: Mapping[str, bytes] | None = None) -> RuntimeRequirement | str:
    """The requirement, or a reason string when no single language can be chosen.

    `files` maps project-relative paths to bytes; anything that is not a build file, over the per-file
    bound, or beyond the file-count bound is ignored and listed as unresolved."""
    unresolved = []
    selected = {}
    for path in sorted(files):
        if not is_build_file(path): continue
        if len(selected) >= MAX_FILES:
            unresolved.append(f'more than {MAX_FILES} build files; the rest were not read'); break
        if len(files[path]) > MAX_FILE_BYTES:
            unresolved.append(f'{path} over {MAX_FILE_BYTES} bytes, not read'); continue
        selected[path] = files[path]
    present = languages(selected)
    if language is None:
        if len(present) != 1:
            return 'no build files recognised at the project root' if not present else \
                f'several ecosystems at the project root ({", ".join(present)}); the language must be given'
        language = present[0]
    elif language not in present:
        return f'no {language} build file at the project root'
    collector = Collector(selected, unresolved=unresolved)
    {'python': python.detect, 'javascript': javascript.detect, 'ruby': ruby.detect, 'perl': perl.detect,
     'java': lambda c: java.detect(c, parents or {})}[language](collector)
    return RuntimeRequirement(language=language, root=root, components=combine(collector.declarations),
                              files=tuple(selected), unresolved=tuple(dict.fromkeys(collector.unresolved))[:64])
