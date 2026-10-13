"""Python build metadata to SPEC-0042 declarations. Files are parsed as data; `setup.py` is read with `ast`, never run."""
import ast
import configparser
import json
import re
import tomllib

from corsair.nodes.runtime.declarations import Collector, ci_versions, typed
from corsair.nodes.runtime.versions import VersionSyntaxError, exactly, parse_version, pep440, poetry, series

CLASSIFIER = re.compile(r'Programming Language :: Python :: (\d+\.\d+)$')
REQUIREMENT = re.compile(r'^\s*(pytest)\s*(?:\[[^\]]*\])?\s*([<>=!~][^;#]*)?(?:;[^#]*)?(?:#.*)?$', re.I)
TOX_ENV = re.compile(r'^py(\d)(\d+)$')
CI_KEYS = ('python-version', 'python', 'python_version', 'py', 'python-versions')
FRAMEWORK = ('test_framework', 'pytest', 'registry')
RUNTIME = ('runtime', 'cpython', 'image')
MAX_TOX_ENVS = 128
# requirements.txt, requirements-dev.txt, test-requirements.txt, dev_requirements.in, ...
REQUIREMENTS_FILE = r'([\w.]+[-_])?requirements([-_.][\w.-]*)?\.(txt|in)'


def _runtime(c: Collector, strength, source, path, needle, text, listed_series=True):
    """Add a CPython declaration from a version string; PyPy, -dev and 3.x style entries stay unparsed."""
    raw = text.strip().strip('\'"')
    try:
        version = parse_version(raw)
    except VersionSyntaxError:
        c.unparsed('runtime', 'cpython', 'image', path, needle or raw, f'not a CPython release: {raw!r}', strength=strength)
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


def _spec(c: Collector, table: dict, path: str) -> str | None:
    """The pytest requirement in a Pipfile or Poetry dependency table: a string, or a table's `version` string."""
    value = typed(c, table, 'pytest', (str, dict), FRAMEWORK, path, 'pytest')
    return typed(c, value, 'version', str, FRAMEWORK, path, 'pytest') if isinstance(value, dict) else value


def _pipfile_python(c: Collector, path: str, requires: dict | None) -> None:
    """Both `python_version` and `python_full_version` are pins; both are kept, so a full pin narrows the series."""
    for key in ('python_version', 'python_full_version'):
        if (version := typed(c, requires, key, str, RUNTIME, path, key, 'pinned')) is not None:
            _runtime(c, 'pinned', 'pipfile', path, key, version, listed_series=False)


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
        here = 'pyproject.toml'
        project = typed(c, data, 'project', dict, RUNTIME, here, '[project]') or {}
        if (spec := typed(c, project, 'requires-python', str, RUNTIME, here)) is not None:
            _requires_python(c, here, 'requires-python', spec)
        _classifiers(c, here, [x for x in project.get('classifiers') or [] if isinstance(x, str)] if isinstance(project.get('classifiers'), list) else [])
        optional = typed(c, project, 'optional-dependencies', dict, FRAMEWORK, here) or {}
        for group in list(optional):
            entries = typed(c, optional, group, list, FRAMEWORK, here) or []
            if any(not isinstance(r, str) for r in entries):
                c.unparsed(*FRAMEWORK, here, group, f'optional-dependencies {group!r} lists a non-string entry')
            _requirement_lines(c, here, [r for r in entries if isinstance(r, str)], 'extras')
        tool = typed(c, data, 'tool', dict, RUNTIME, here, '[tool') or {}
        poetry_table = typed(c, tool, 'poetry', dict, RUNTIME, here, '[tool.poetry') or {}
        dependencies = typed(c, poetry_table, 'dependencies', dict, RUNTIME, here, '[tool.poetry.dependencies') or {}
        python = typed(c, dependencies, 'python', str, RUNTIME, here, 'python')
        if python is not None:
            try:  # Poetry's caret/tilde/comma syntax maps onto npm-style ranges
                c.add('runtime', 'cpython', 'image', 'constraint', 'requires-python', 'pyproject.toml', 'python',
                      poetry(python))
            except VersionSyntaxError as error:
                c.unparsed('runtime', 'cpython', 'image', 'pyproject.toml', 'python', str(error))
        # Poetry dependency tables: the main and legacy dev tables, and every Poetry >= 1.2 group.
        tables = [dependencies, typed(c, poetry_table, 'dev-dependencies', dict, FRAMEWORK, here) or {}]
        for name, group in (typed(c, poetry_table, 'group', dict, FRAMEWORK, here, '[tool.poetry.group') or {}).items():
            group = typed(c, {name: group}, name, dict, FRAMEWORK, here, f'[tool.poetry.group.{name}') or {}
            tables.append(typed(c, group, 'dependencies', dict, FRAMEWORK, here, f'[tool.poetry.group.{name}') or {})
        for table in tables:
            pytest = _spec(c, table, here)
            if pytest is not None:
                try: c.add(*FRAMEWORK, 'constraint', 'poetry', here, 'pytest', poetry(pytest))
                except VersionSyntaxError as error: c.unparsed(*FRAMEWORK, here, 'pytest', str(error))
        # PEP 735 dependency groups (string entries; include-group tables name other groups) and uv's dev list.
        groups = typed(c, data, 'dependency-groups', dict, FRAMEWORK, here, '[dependency-groups]') or {}
        for name in list(groups):
            for entry in typed(c, groups, name, list, FRAMEWORK, here) or []:
                if isinstance(entry, str): _requirement_lines(c, here, [entry], 'dependency-groups')
                elif not (isinstance(entry, dict) and set(entry) == {'include-group'} and entry['include-group'] in groups):
                    c.unparsed(*FRAMEWORK, here, name, f'dependency-groups {name!r} entry {str(entry)[:40]!r} is not a requirement or include-group')
        uv = typed(c, tool, 'uv', dict, FRAMEWORK, here, '[tool.uv') or {}
        uv_dev = typed(c, uv, 'dev-dependencies', list, FRAMEWORK, here) or []
        _requirement_lines(c, here, [r for r in uv_dev if isinstance(r, str)], 'uv')
        if any(not isinstance(r, str) for r in uv_dev):
            c.unparsed(*FRAMEWORK, here, 'dev-dependencies', 'tool.uv dev-dependencies lists a non-string entry')
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
        if (path.count('/') == 0 and re.fullmatch(REQUIREMENTS_FILE, name)) or re.fullmatch(r'requirements/[^/]+\.(txt|in)', path):
            _requirement_lines(c, path, (c.text(path) or '').splitlines(), 'requirements')
    if (text := c.text('tox.ini')) is not None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read_string(text)
        except configparser.Error as error:
            c.unparsed('runtime', 'cpython', 'image', 'tox.ini', '', f'invalid tox.ini: {error}')
        else:
            envs = _expand(parser.get('tox', 'envlist')) if parser.has_option('tox', 'envlist') else []
            if envs is None:
                c.unparsed(*RUNTIME, 'tox.ini', 'envlist', f'envlist expands to more than {MAX_TOX_ENVS} environments')
                envs = []
            if envs:
                for env in envs:
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
        except tomllib.TOMLDecodeError as error:
            c.unparsed('runtime', 'cpython', 'image', 'Pipfile', '', f'invalid TOML: {error}')
            data = {}
        _pipfile_python(c, 'Pipfile', typed(c, data, 'requires', dict, RUNTIME, 'Pipfile', '[requires]', 'pinned'))
        for group in ('dev-packages', 'packages'):
            if (spec := _spec(c, typed(c, data, group, dict, FRAMEWORK, 'Pipfile', f'[{group}]') or {}, 'Pipfile')) is not None:
                _pytest(c, 'Pipfile', 'pytest', '' if spec == '*' else spec, 'pipfile')
    for path, key in (('uv.lock', 'requires-python'), ('poetry.lock', 'python-versions')):
        if (text := c.text(path)) is None: continue
        # The project-wide range is uv's top-level `requires-python` or Poetry's `[metadata] python-versions`;
        # ranges inside `[[package]]` entries are per dependency and never project constraints.
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            c.unparsed('runtime', 'cpython', 'image', path, '', f'invalid TOML: {error}')
            continue
        table = data if path == 'uv.lock' else data.get('metadata')
        value = table.get(key) if isinstance(table, dict) else None
        if value is None: continue
        start = text.find('[metadata]') if path == 'poetry.lock' else 0
        line = text.count('\n', 0, max(text.find(key, max(start, 0)), 0)) + 1
        needle = key
        if not isinstance(value, str):
            c.unparsed('runtime', 'cpython', 'image', path, needle, f'{key} {value!r} is not a string', line=line)
            continue
        try:
            versions = pep440(value) if path == 'uv.lock' else poetry(value)
            c.add('runtime', 'cpython', 'image', 'constraint', 'lockfile', path, needle, versions, line=line)
        except VersionSyntaxError as error:
            c.unparsed('runtime', 'cpython', 'image', path, needle, str(error), line=line)
    for path, value, source in ci_versions(c, CI_KEYS, ('python',)):
        _runtime(c, 'tested', source, path, value, value)
    if (text := c.text('Pipfile.lock')) is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            c.unparsed(*RUNTIME, 'Pipfile.lock', '', f'invalid JSON: {error}', strength='pinned')
            data = {}
        if not isinstance(data, dict):
            c.unparsed(*RUNTIME, 'Pipfile.lock', '', 'not a JSON object', strength='pinned')
            data = {}
        meta = typed(c, data, '_meta', dict, RUNTIME, 'Pipfile.lock', '"_meta"', 'pinned') or {}
        _pipfile_python(c, 'Pipfile.lock', typed(c, meta, 'requires', dict, RUNTIME, 'Pipfile.lock', '"requires"', 'pinned'))


def _expand(envlist: str) -> list[str] | None:
    """tox envlist entries with `{a,b}` factor groups expanded; comma or newline separated. None when the expansion
    would exceed MAX_TOX_ENVS, checked before each product is materialised (eight groups already make 256)."""
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
            options = match[1].split(',')
            if len(expanded) + len(stack) + len(options) > MAX_TOX_ENVS: return None
            stack += [item[:match.start()] + option.strip() + item[match.end():] for option in options]
    return expanded
