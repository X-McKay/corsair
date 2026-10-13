"""Perl build metadata (Makefile.PL, Build.PL, cpanfile, META, dist.ini, CI) to SPEC-0042 declarations.

Build scripts are Perl code; only literal declarations are read, nothing is evaluated. Tests run through
Test::Harness (`make test`/`prove`), so a recognised build file implies the TAP harness framework.
"""
import json
import re

from corsair.nodes.runtime.declarations import Collector, ci_versions, load_yaml
from corsair.nodes.runtime.versions import ANY, VersionSyntaxError, at_least, parse_version, perl, series

CI_KEYS = ('perl', 'perl-version', 'perl_version', 'perl-versions')
USE = re.compile(r'^\s*(?:use|require)\s+(v?5[\d._]*)\s*;', re.M)
MIN = re.compile(r'''MIN_PERL_VERSION['"]?\s*=>\s*['"]?(v?5[\d._]*)''')
CPAN_PERL = re.compile(r'''requires\s*\(?\s*['"]perl['"]\s*(?:,|=>)\s*['"]?(v?5[\d._]*)''')
TEST_MORE = re.compile(r'''['"]Test::More['"]\s*(?:,|=>)\s*['"]?([\d._]+)''')


def _constraint(c: Collector, path: str, needle: str, raw: str, source: str):
    try:
        c.add('runtime', 'perl', 'image', 'constraint', source, path, needle, at_least(perl(raw.replace('_', ''))))
    except VersionSyntaxError as error:
        c.unparsed('runtime', 'perl', 'image', path, needle, str(error))


def detect(c: Collector) -> None:
    builders = []
    for path, tool in (('Makefile.PL', 'make'), ('Build.PL', 'module-build'), ('dist.ini', 'dist-zilla')):
        if (text := c.text(path)) is None: continue
        builders.append(path)
        c.add('build_tool', tool, 'image' if tool == 'make' else 'registry', 'constraint', 'build-file', path, '', ANY)
        for pattern, source in ((USE, 'use-version'), (MIN, 'MIN_PERL_VERSION')):
            for match in pattern.finditer(text):
                _constraint(c, path, match[0].strip(), match[1], source)
        if path == 'dist.ini' and (match := re.search(r'^\s*perl\s*=\s*(v?5[\d._]*)', text, re.M)):
            _constraint(c, path, match[0].strip(), match[1], 'dist.ini')
        for match in TEST_MORE.finditer(text):
            c.add('test_framework', 'tap-harness', 'registry', 'constraint', 'Test::More', path, match[0], ANY)
    if (text := c.text('cpanfile')) is not None:
        builders.append('cpanfile')
        for match in CPAN_PERL.finditer(text): _constraint(c, 'cpanfile', match[0], match[1], 'cpanfile')
    for path in ('META.json', 'META.yml'):
        if (text := c.text(path)) is None: continue
        try:
            data = json.loads(text) if path.endswith('json') else load_yaml(text)
        except ValueError:
            c.unparsed('runtime', 'perl', 'image', path, '', 'invalid META')
            continue
        prereqs = (data or {}).get('prereqs') if isinstance(data, dict) else None
        requires = (((prereqs or {}).get('runtime') or {}).get('requires') or {}) if isinstance(prereqs, dict) else \
            ((data or {}).get('requires') or {}) if isinstance(data, dict) else {}
        if isinstance(requires, dict) and requires.get('perl') not in (None, '0', 0):
            _constraint(c, path, '"perl"' if path.endswith('json') else 'perl:', str(requires['perl']), 'META')
    if builders:
        c.add('test_framework', 'tap-harness', 'registry', 'constraint', 'build-file', builders[0], '', ANY)
    for path, value, source in ci_versions(c, CI_KEYS, ('perl',)):
        raw = value.strip().strip('\'"')
        try:
            version = parse_version(raw)
            c.add('runtime', 'perl', 'image', 'tested', source, path, value, series(version[:2]), listed=version[:2])
        except VersionSyntaxError:
            c.unparsed('runtime', 'perl', 'image', path, value, f'not a perl release: {raw!r}')
