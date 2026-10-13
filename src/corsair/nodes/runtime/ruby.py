"""Ruby build metadata (gemspecs, Gemfile, Gemfile.lock, version files, CI) to SPEC-0042 declarations.

Gemspecs and Gemfiles are Ruby code; only literal strings in recognised calls are read, nothing is evaluated.
"""
import re

from corsair.nodes.runtime.declarations import Collector, ci_versions
from corsair.nodes.runtime.versions import ANY, VersionSyntaxError, exactly, gem, parse_version, series

FRAMEWORKS = ('rspec', 'minitest', 'test-unit')
CI_KEYS = ('ruby', 'ruby-version', 'ruby_version', 'rvm')
STRINGS = re.compile(r'''['"]([^'"]+)['"]''')
REQUIRED = re.compile(r'''required_ruby_version\s*=\s*(?:Gem::Requirement\.new\()?\s*\[?((?:\s*['"][^'"]+['"]\s*,?)+)''')
DEPENDENCY = re.compile(r'''(?:add_(?:development_|runtime_)?dependency|^\s*gem)\s*\(?\s*['"](rspec(?:-core|-rails)?|minitest|test-unit)['"]((?:\s*,\s*['"][^'"]+['"])*)''', re.M)


def _ruby(c: Collector, strength: str, source: str, path: str, needle: str, raw: str):
    raw = raw.strip().strip('\'"').removeprefix('ruby-')
    try:
        version = parse_version(re.sub(r'p\d+$', '', raw))
    except VersionSyntaxError:
        c.unparsed('runtime', 'ruby', 'image', path, needle or raw, f'not an MRI release: {raw!r}', strength=strength)
        return
    c.add('runtime', 'ruby', 'image', strength, source, path, needle or raw,
          series(version) if strength == 'tested' or len(version) < 3 else exactly(version), listed=version)


def _framework(c: Collector, path: str, match, source: str):
    # rspec-rails and friends version independently of rspec; only rspec/rspec-core constrain the framework.
    clauses = STRINGS.findall(match[2] or '') if match[1] in ('rspec', 'rspec-core', 'minitest', 'test-unit') else []
    family = 'rspec' if match[1].startswith('rspec') else match[1]
    try:
        versions = gem(clauses) if clauses else ANY
    except VersionSyntaxError as error:
        c.unparsed('test_framework', family, 'registry', path, match[0].strip(), str(error))
        return
    c.add('test_framework', family, 'registry', 'constraint', source, path, match[0].strip(), versions)


def detect(c: Collector) -> None:
    for path in sorted(p for p in c.files if '/' not in p and p.endswith('.gemspec')):
        text = c.text(path) or ''
        for match in REQUIRED.finditer(text):
            try:
                c.add('runtime', 'ruby', 'image', 'constraint', 'required_ruby_version', path, match[0], gem(STRINGS.findall(match[1])))
            except VersionSyntaxError as error:
                c.unparsed('runtime', 'ruby', 'image', path, match[0], str(error))
        for match in DEPENDENCY.finditer(text): _framework(c, path, match, 'gemspec')
    if (text := c.text('Gemfile')) is not None:
        if (match := re.search(r'''^\s*ruby\s+['"]([^'"]+)['"]''', text, re.M)):
            _ruby(c, 'pinned', 'gemfile', 'Gemfile', match[0], match[1])
        for match in DEPENDENCY.finditer(text): _framework(c, 'Gemfile', match, 'gemfile')
    if (text := c.text('Gemfile.lock')) is not None:
        if (match := re.search(r'^RUBY VERSION\n\s+ruby (\S+)', text, re.M)):
            _ruby(c, 'pinned', 'lockfile', 'Gemfile.lock', match[0].splitlines()[-1].strip(), match[1])
        if (match := re.search(r'^BUNDLED WITH\n\s+(\S+)', text, re.M)):
            try:
                version = parse_version(match[1])
                c.add('build_tool', 'bundler', 'image', 'pinned', 'lockfile', 'Gemfile.lock', match[0].splitlines()[-1].strip(), series(version[:1]), listed=version)
            except VersionSyntaxError:
                c.unparsed('build_tool', 'bundler', 'image', 'Gemfile.lock', 'BUNDLED WITH', f'bundler {match[1]!r}')
        for framework in FRAMEWORKS:
            if (match := re.search(rf'^    {re.escape(framework)} \((\d+(?:\.\d+){{0,7}})\)$', text, re.M)):
                version = parse_version(match[1])
                c.add('test_framework', framework, 'registry', 'pinned', 'lockfile', 'Gemfile.lock', match[0].strip(), exactly(version), listed=version)
    if 'Gemfile' in c.files and not any(d.name == 'bundler' for d in c.declarations):
        c.add('build_tool', 'bundler', 'image', 'constraint', 'gemfile', 'Gemfile', '', ANY)
    if (text := c.text('.ruby-version')) is not None:
        first = next((l.strip() for l in text.splitlines() if l.strip()), '')
        _ruby(c, 'pinned', 'version-file', '.ruby-version', first, first)
    for path, value, source in ci_versions(c, CI_KEYS, ('rvm', 'ruby')):
        _ruby(c, 'tested', source, path, value, value)
