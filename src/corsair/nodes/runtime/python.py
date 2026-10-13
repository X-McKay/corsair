"""Python build metadata to SPEC-0042 declarations. Files are parsed as data; `setup.py` is read with `ast`, never run."""
import ast
import configparser
import json
import re
import tomllib

from corsair.nodes.runtime.declarations import Collector, ci_versions
from corsair.nodes.runtime.versions import VersionSyntaxError, exactly, parse_version, pep440, poetry, series

CLASSIFIER = re.compile(r'Programming Language :: Python :: (\d+\.\d+)$')
REQUIREMENT = re.compile(r'^\s*(pytest)\s*(?:\[[^\]]*\])?\s*([<>=!~][^;#]*)?(?:;[^#]*)?(?:#.*)?$', re.I)
TOX_ENV = re.compile(r'^py(\d)(\d+)$')
CI_KEYS = ('python-version', 'python', 'python_version', 'py', 'python-versions')
FRAMEWORK = ('test_framework', 'pytest', 'registry')


def _runtime(c: Collector, strength, source, path, needle, text, listed_series=True):
    """Add a CPython declaration from a version string; PyPy, -dev and 3.x style entries stay unparsed."""
    raw = text.strip().strip('\'"')
    try:
        version = parse_version(raw)
    except VersionSyntaxError:
        c.unparsed('runtime', 'cpython', 'image', path, needle or raw, f'not a CPython release: {raw!r}')
        return
    c.add('runtime', 'cpython', 'image', strength, source, path, needle or raw,
          series(version) if listed_series or len(version) < 3 else exactly(version),
          listed=version[:2] if listed_series else version)


def _requires_python(c: Collector, path: str, needle: str, spec: str):
    try:
        c.add('runtime', 'cpython', 'image', 'constraint', 'requires-python', path, needle, pep440(spec))
    except VersionSyntaxError as error:
        c.unparsed('runtime', 'cpython', 'image', path, needle, str(error))


def _pytest(c: Collector, path: str, needle: str, spec: str | None, source: str):
    try:
        c.add(*FRAMEWORK, 'constraint', source, path, needle, pep440(spec or ''))
    except VersionSyntaxError as error:
        c.unparsed(*FRAMEWORK, path, needle, str(error))


def _classifiers(c: Collector, path: str, values):
    for value in values:
        if (match := CLASSIFIER.search(value.strip())):
            _runtime(c, 'tested', 'classifier', path, value.strip(), match[1])


def _requirement_lines(c: Collector, path: str, lines, source: str):
    for line in lines:
        if (match := REQUIREMENT.match(line)): _pytest(c, path, line.strip(), match[2], source)


def detect(c: Collector) -> None:
    files = c.files
    if (text := c.text('pyproject.toml')) is not None:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            c.unparsed('runtime', 'cpython', 'image', 'pyproject.toml', '', f'invalid TOML: {error}')
            data = {}
        project = data.get('project') if isinstance(data.get('project'), dict) else {}
        if isinstance(project.get('requires-python'), str):
            _requires_python(c, 'pyproject.toml', 'requires-python', project['requires-python'])
        _classifiers(c, 'pyproject.toml', [x for x in project.get('classifiers') or [] if isinstance(x, str)] if isinstance(project.get('classifiers'), list) else [])
        optional = project.get('optional-dependencies') if isinstance(project.get('optional-dependencies'), dict) else {}
        _requirement_lines(c, 'pyproject.toml', [r for group in optional.values() if isinstance(group, list) for r in group if isinstance(r, str)], 'extras')
        tool = data.get('tool') if isinstance(data.get('tool'), dict) else {}
        poetry_table = tool.get('poetry') if isinstance(tool.get('poetry'), dict) else {}
        python = (poetry_table.get('dependencies') or {}).get('python') if isinstance(poetry_table.get('dependencies'), dict) else None
        if isinstance(python, str):
            try:  # Poetry's caret/tilde/comma syntax maps onto npm-style ranges
                c.add('runtime', 'cpython', 'image', 'constraint', 'requires-python', 'pyproject.toml', 'python',
                      poetry(python))
            except VersionSyntaxError as error:
                c.unparsed('runtime', 'cpython', 'image', 'pyproject.toml', 'python', str(error))
        for group in ('dev-dependencies',):
            pytest = poetry_table.get(group).get('pytest') if isinstance(poetry_table.get(group), dict) else None
            if isinstance(pytest, str):
                try: c.add(*FRAMEWORK, 'constraint', 'poetry', 'pyproject.toml', 'pytest', poetry(pytest))
                except VersionSyntaxError as error: c.unparsed(*FRAMEWORK, 'pyproject.toml', 'pytest', str(error))
        if 'pytest' in tool:
            c.add(*FRAMEWORK, 'constraint', 'config', 'pyproject.toml', '[tool.pytest', pep440(''))
        backend = data['build-system'].get('build-backend') if isinstance(data.get('build-system'), dict) else None
        if isinstance(backend, str):
            c.add('build_tool', backend.split('.')[0].split(':')[0], 'registry', 'constraint', 'build-backend', 'pyproject.toml', 'build-backend', pep440(''))
    if (text := c.text('setup.cfg')) is not None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read_string(text)
        except configparser.Error as error:
            c.unparsed('runtime', 'cpython', 'image', 'setup.cfg', '', f'invalid setup.cfg: {error}')
        else:
            if parser.has_option('options', 'python_requires'):
                spec = parser.get('options', 'python_requires')
                _requires_python(c, 'setup.cfg', 'python_requires', spec)
            if parser.has_option('metadata', 'classifiers'):
                _classifiers(c, 'setup.cfg', parser.get('metadata', 'classifiers').splitlines())
            for section in ('options.extras_require',):
                if parser.has_section(section):
                    _requirement_lines(c, 'setup.cfg', [l for _, v in parser.items(section) for l in v.splitlines()], 'extras')
            if parser.has_option('options', 'tests_require'):
                _requirement_lines(c, 'setup.cfg', parser.get('options', 'tests_require').splitlines(), 'tests_require')
            if parser.has_section('tool:pytest'):
                c.add(*FRAMEWORK, 'constraint', 'config', 'setup.cfg', '[tool:pytest]', pep440(''))
    if (text := c.text('setup.py')) is not None:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError) as error:
            c.unparsed('runtime', 'cpython', 'image', 'setup.py', '', f'setup.py does not parse: {error}')
            tree = None
        for node in ast.walk(tree) if tree else ():
            if isinstance(node, ast.keyword) and node.arg == 'python_requires':
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    _requires_python(c, 'setup.py', 'python_requires', node.value.value)
                else:
                    c.unparsed('runtime', 'cpython', 'image', 'setup.py', 'python_requires', 'python_requires is computed', line=node.value.lineno)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if CLASSIFIER.search(node.value.strip()): _classifiers(c, 'setup.py', [node.value])
                elif (match := REQUIREMENT.match(node.value)) and match[1].lower() == 'pytest':
                    _pytest(c, 'setup.py', node.value, match[2], 'setup.py')
    for path in sorted(files):
        name = path.rsplit('/', 1)[-1]
        if (path.count('/') == 0 and re.fullmatch(r'requirements.*\.(txt|in)', name)) or re.fullmatch(r'requirements/[^/]+\.(txt|in)', path):
            _requirement_lines(c, path, (c.text(path) or '').splitlines(), 'requirements')
    if (text := c.text('tox.ini')) is not None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read_string(text)
        except configparser.Error as error:
            c.unparsed('runtime', 'cpython', 'image', 'tox.ini', '', f'invalid tox.ini: {error}')
        else:
            if parser.has_option('tox', 'envlist'):
                for env in _expand(parser.get('tox', 'envlist')):
                    for factor in env.split('-'):
                        if (match := TOX_ENV.fullmatch(factor)):
                            _runtime(c, 'tested', 'tox', 'tox.ini', factor, f'{match[1]}.{match[2]}')
            for section in parser.sections():
                if section.startswith('testenv'):
                    for option in ('deps', 'commands'):
                        if parser.has_option(section, option):
                            value = parser.get(section, option)
                            _requirement_lines(c, 'tox.ini', value.splitlines(), 'tox')
                            if option == 'commands' and re.search(r'(^|\s|/)(py\.test|pytest)\b|-m pytest', value):
                                c.add(*FRAMEWORK, 'constraint', 'tox', 'tox.ini', 'pytest', pep440(''))
            if parser.has_section('pytest'):
                c.add(*FRAMEWORK, 'constraint', 'config', 'tox.ini', '[pytest]', pep440(''))
    if 'pytest.ini' in files:
        c.add(*FRAMEWORK, 'constraint', 'config', 'pytest.ini', '', pep440(''))
    for path in ('.python-version', 'runtime.txt'):
        if (text := c.text(path)) is not None:
            first = next((l.strip() for l in text.splitlines() if l.strip() and not l.startswith('#')), '')
            _runtime(c, 'pinned', 'version-file', path, first, first.removeprefix('python-'), listed_series=False)
    if (text := c.text('Pipfile')) is not None:
        try:
            data = tomllib.loads(text)
            version = (data.get('requires') or {}).get('python_version') or (data.get('requires') or {}).get('python_full_version')
            if version: _runtime(c, 'pinned', 'pipfile', 'Pipfile', 'python_', str(version), listed_series=False)
            for group in ('dev-packages', 'packages'):
                if isinstance((data.get(group) or {}).get('pytest'), str):
                    _pytest(c, 'Pipfile', 'pytest', '' if data[group]['pytest'] == '*' else data[group]['pytest'], 'pipfile')
        except tomllib.TOMLDecodeError as error:
            c.unparsed('runtime', 'cpython', 'image', 'Pipfile', '', f'invalid TOML: {error}')
    for path, needle in (('uv.lock', 'requires-python'), ('poetry.lock', 'python-versions')):
        if (text := c.text(path)) is not None and (match := re.search(rf'^{needle}\s*=\s*"([^"]+)"', text, re.M)):
            try:
                versions = pep440(match[1]) if path == 'uv.lock' else poetry(match[1])
                c.add('runtime', 'cpython', 'image', 'constraint', 'lockfile', path, match[0], versions)
            except VersionSyntaxError as error:
                c.unparsed('runtime', 'cpython', 'image', path, match[0], str(error))
    for path, value, source in ci_versions(c, CI_KEYS, ('python',)):
        _runtime(c, 'tested', source, path, value, value)
    if (text := c.text('Pipfile.lock')) is not None:
        try:
            version = ((json.loads(text).get('_meta') or {}).get('requires') or {}).get('python_version')
            if version: _runtime(c, 'pinned', 'pipfile', 'Pipfile.lock', 'python_version', str(version), listed_series=False)
        except (json.JSONDecodeError, AttributeError):
            c.unparsed('runtime', 'cpython', 'image', 'Pipfile.lock', '', 'invalid JSON')


def _expand(envlist: str) -> list[str]:
    """tox envlist entries with `{a,b}` factor groups expanded; comma or newline separated."""
    entries, depth, current = [], 0, ''
    for char in envlist:
        if char == ',' and depth == 0 or char == '\n':
            entries.append(current.strip()); current = ''
            continue
        depth += char == '{'
        depth -= char == '}'
        current += char
    entries.append(current.strip())
    expanded = []
    for entry in filter(None, entries):
        stack = [entry]
        while stack:
            item = stack.pop()
            match = re.search(r'\{([^{}]*)\}', item)
            if not match:
                expanded.append(item)
                continue
            stack += [item[:match.start()] + option.strip() + item[match.end():] for option in match[1].split(',')]
    return expanded
