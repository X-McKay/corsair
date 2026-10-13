"""Java build metadata (Maven POMs with their parents, Gradle scripts, wrappers, CI) to SPEC-0042 declarations.

POMs are parsed as data after refusing any markup declaration. Parent POMs outside the tree come only from the
caller's `parents` mapping (`group:artifact:version` to bytes, for example fetched from the registry during the
dependency phase); a missing parent is reported as unresolved, never guessed. Profiles are not evaluated.
"""
import re
import xml.etree.ElementTree as ET
from typing import Mapping

from corsair.nodes.runtime.declarations import Collector, Declaration, ci_versions, line_of
from corsair.nodes.runtime.versions import (ANY, Interval, VersionSet, VersionSyntaxError, java_feature, maven, parse_version,
                                            series, version_key)

PROPERTY = re.compile(r'\$\{([^}]+)\}')
MAX_PARENT_DEPTH = 8
MAX_POMS = 512
CI_KEYS = ('java', 'jdk', 'java-version', 'java_version', 'java-versions')
JDK_TOKEN = re.compile(r'(?:(?:open|oracle|zulu|adopt|temurin)?jdk[-_]?|java[-_]?|JDK\s*|^)(1\.\d+|\d+)\b', re.I)
FRAMEWORKS = {  # (groupId, artifactId prefix) -> framework family
    ('junit', 'junit'): 'junit4',
    ('org.junit.jupiter', 'junit-jupiter'): 'junit5',
    ('org.junit', 'junit-bom'): 'junit5',
    ('org.testng', 'testng'): 'testng',
}


def min_target(feature: int) -> int:
    """Oldest `-source/-target` a JDK feature release still compiles (javac: 9-11 drop 5, 12-19 drop 6, 20+ drop 7)."""
    return 1 if feature <= 8 else 6 if feature <= 11 else 7 if feature <= 19 else 8


def compiler_jdks(target: int) -> VersionSet:
    """JDK feature releases able to compile a project at `target`: target <= JDK and min_target(JDK) <= target."""
    newest = 8 if target < 6 else 11 if target < 7 else 19 if target < 8 else None
    return VersionSet((Interval((max(target, 1),), True, (newest + 1,) if newest else None, False),))


class Pom:
    def __init__(self, path: str, data: bytes):
        self.path = path
        text = data.decode('utf-8', errors='replace')
        if '<!DOCTYPE' in text or '<!ENTITY' in text: raise ValueError('markup declaration refused')
        self.text = text
        root = ET.fromstring(text)
        for element in root.iter():
            element.tag = element.tag.rsplit('}', 1)[-1]
        self.root = root
        parent = root.find('parent')
        self.parent = tuple((parent.findtext(k) or '').strip() for k in ('groupId', 'artifactId', 'version')) if parent is not None else None
        group = root.findtext('groupId') or (self.parent[0] if self.parent else '')
        self.gav = (group.strip(), (root.findtext('artifactId') or '').strip(), (root.findtext('version') or (self.parent[2] if self.parent else '')).strip())
        props = root.find('properties')
        self.properties = {p.tag: (p.text or '').strip() for p in props} if props is not None else {}

    def plugins(self):
        """(artifactId, plugin element) for build plugins and pluginManagement, profiles excluded."""
        build = self.root.find('build')
        if build is None: return []
        found = list(build.findall('plugins/plugin')) + list(build.findall('pluginManagement/plugins/plugin'))
        return [((p.findtext('artifactId') or '').strip(), p) for p in found]

    def dependencies(self):
        return list(self.root.findall('dependencies/dependency')) + list(self.root.findall('dependencyManagement/dependencies/dependency'))


def _chain(c: Collector, pom: Pom, in_tree: Mapping[tuple, Pom], parents: Mapping[str, bytes]) -> list[Pom]:
    """The POM and its ancestors, nearest first; stops (and records why) at a parent that is not available."""
    chain, current = [pom], pom
    while current.parent and len(chain) <= MAX_PARENT_DEPTH:
        key = ':'.join(current.parent)
        found = in_tree.get(current.parent)
        if found is None and key in parents:
            try:
                found = Pom(f'parent:{key}', parents[key])
            except (ET.ParseError, ValueError) as error:
                c.unresolved.append(f'parent POM {key} refused: {error}')
                break
        if found is None:
            if f'parent POM {key} not available' not in c.unresolved: c.unresolved.append(f'parent POM {key} not available')
            break
        chain.append(found)
        current = found
    return chain


MAX_EXPANDED = 256


def _resolve(value: str, properties: Mapping[str, str]) -> str | None:
    """`${name}` expansion, bounded: at most 8 rounds and 256 characters; a cycle or overflow resolves to None."""
    for _ in range(8):
        if '${' not in value: return value
        value = PROPERTY.sub(lambda m: properties.get(m[1], m[0]), value)
        if len(value) > MAX_EXPANDED: return None
        if all(name not in properties for name in PROPERTY.findall(value)): break
    return None if '${' in value else value


def _cite(c: Collector, pom: Pom, needle: str):
    """(path, line) of a needle in a POM; parents outside the tree are cited by coordinate on line 1."""
    if pom.path.startswith('parent:'): return pom.path, 1
    return pom.path, line_of(pom.text, needle)


def _add(c, kind, name, provider, strength, source, pom, needle, versions, listed=None, reason=''):
    path, line = _cite(c, pom, needle)
    if path.startswith('parent:'):
        c.declarations.append(Declaration(kind, name, provider, strength, source, path, 1, needle[:240], versions, listed, reason))
    else:
        c.add(kind, name, provider, strength, source, path, needle, versions, listed, reason, line=line)


def _maven(c: Collector, parents: Mapping[str, bytes]) -> None:
    poms: dict[str, Pom] = {}
    for path in sorted(p for p in c.files if p == 'pom.xml' or p.endswith('/pom.xml'))[:MAX_POMS]:
        try:
            poms[path] = Pom(path, c.files[path])
        except (ET.ParseError, ValueError) as error:
            c.unparsed('build_tool', 'maven', 'image', path, '', f'POM refused: {error}')
    root = poms.get('pom.xml')
    if root is None: return
    in_tree = {pom.gav: pom for pom in poms.values()}
    c.add('build_tool', 'maven', 'image', 'constraint', 'pom', 'pom.xml', '<project', ANY)
    chain = _chain(c, root, in_tree, parents)
    properties: dict[str, str] = {}
    for pom in reversed(chain): properties.update(pom.properties)
    properties.update({'project.version': root.gav[2], 'pom.version': root.gav[2], 'project.groupId': root.gav[0]})

    # Bytecode level as Maven computes it: each compiler parameter takes the nearest POM that sets it, the plugin's
    # <configuration> over the `maven.compiler.*` property default within one POM; then release over target over source.
    def parameter(key):
        for pom in chain:
            for artifact, plugin in pom.plugins():
                if artifact == 'maven-compiler-plugin' and (value := plugin.findtext(f'configuration/{key}')):
                    return pom, f'<{key}>{value}', value.strip()
            if f'maven.compiler.{key}' in pom.properties:
                return pom, f'<maven.compiler.{key}>', pom.properties[f'maven.compiler.{key}']
        return None
    level = parameter('release') or parameter('target') or parameter('source')
    if level:
        pom, needle, raw = level
        value = _resolve(raw, properties)
        try:
            feature = java_feature(parse_version(value or ''))[0]
            _add(c, 'runtime', 'jdk', 'image', 'constraint', 'compiler-target', pom, needle, compiler_jdks(feature))
            derived = max(feature, 8)
            _add(c, 'runtime', 'jdk', 'image', 'tested', 'derived', pom, needle, series((derived,)), listed=(derived,))
        except VersionSyntaxError:
            _add(c, 'runtime', 'jdk', 'image', 'constraint', 'unparsed', pom, needle, None,
                 reason=f'compiler level {raw!r} does not resolve' + ('' if value else ' (property undefined in the available POMs)'))

    for pom in chain:
        for artifact, plugin in pom.plugins():
            if artifact == 'maven-enforcer-plugin':
                for rule, name in (('requireJavaVersion', 'jdk'), ('requireMavenVersion', 'maven')):
                    for element in plugin.iter(rule):
                        raw = element.findtext('version')
                        if not raw: continue
                        value = _resolve(raw.strip(), properties)
                        kind = 'runtime' if name == 'jdk' else 'build_tool'
                        try:
                            versions = maven(value or '', normalise=java_feature if name == 'jdk' else (lambda v: v))
                            _add(c, kind, name, 'image', 'constraint', 'enforcer', pom, f'<{rule}>', versions)
                        except VersionSyntaxError:
                            _add(c, kind, name, 'image', 'constraint', 'unparsed', pom, f'<{rule}>', None, reason=f'enforcer version {raw!r} does not resolve')
            if artifact == 'maven-toolchains-plugin':
                for element in plugin.findall('configuration/toolchains/jdk/version'):
                    raw = (element.text or '').strip()
                    value = _resolve(raw, properties) if raw else None
                    try:
                        if not value: raise VersionSyntaxError(f'toolchains JDK version {raw!r} does not resolve')
                        _add(c, 'runtime', 'jdk', 'image', 'pinned', 'toolchains', pom, '<toolchains>',
                             maven(value, java_feature) if value.startswith(('[', '(')) else series(java_feature(parse_version(value))),
                             listed=java_feature(parse_version(value)) if not value.startswith(('[', '(')) else None)
                    except VersionSyntaxError as error:
                        _add(c, 'runtime', 'jdk', 'image', 'pinned', 'unparsed', pom, '<toolchains>', None,
                             reason=f'toolchains JDK version {raw!r} not read: {error}'[:240])

    # Test frameworks: the root POM and its ancestors decide (dependencyManagement included); only when they name
    # none do reactor modules count, as alternatives (modules may pin different versions). POMs under `src/`
    # are templates (archetype resources), not modules.
    def frameworks(poms_in_scope, local_properties):
        found: dict[str, list] = {}
        for pom in poms_in_scope:
            local = dict(local_properties)
            local.update(pom.properties)
            for dependency in pom.dependencies():
                group = (dependency.findtext('groupId') or '').strip()
                artifact = (dependency.findtext('artifactId') or '').strip()
                family = next((f for (g, a), f in FRAMEWORKS.items() if group == g and artifact.startswith(a)), None)
                if family is None: continue
                raw = (dependency.findtext('version') or '').strip()
                value = _resolve(raw, local) if raw else None
                try:
                    version = parse_version(value) if value else None
                except VersionSyntaxError:
                    version = None
                if family == 'junit4' and version and version[0] < 4: family = 'junit3'  # junit:junit 3.x is JUnit 3
                found.setdefault(family, []).append((pom, artifact, raw, version))
        return found

    found = frameworks(chain, properties)
    if not found:
        found = frameworks([p for path, p in poms.items() if path != 'pom.xml' and '/src/' not in f'/{path}'], properties)
    for family, items in found.items():
        versions = [v for *_, v in items if v is not None]
        pom, artifact, raw, _ = items[0]
        if versions:
            union = VersionSet(())
            for v in versions: union = union.union(series(v))
            _add(c, 'test_framework', family, 'registry', 'constraint', 'dependency', pom, f'<artifactId>{artifact}', union,
                 listed=max(versions, key=version_key))
            for unread_pom, unread_artifact, unread_raw, _ in (i for i in items if i[2] and i[3] is None):
                _add(c, 'test_framework', family, 'registry', 'constraint', 'unparsed', unread_pom, f'<artifactId>{unread_artifact}',
                     None, reason=f'{unread_artifact} version {unread_raw!r} does not resolve')
        elif all(not r for _, _, r, _ in items):
            _add(c, 'test_framework', family, 'registry', 'constraint', 'dependency', pom, f'<artifactId>{artifact}', ANY)
        else:
            _add(c, 'test_framework', family, 'registry', 'constraint', 'unparsed', pom, f'<artifactId>{artifact}', None,
                 reason=f'version {raw!r} does not resolve')

    # Surefire: the nearest POM in the chain that pins it wins, as in Maven's own inheritance.
    surefire = next(((pom, plugin.findtext('version')) for pom in chain for artifact, plugin in pom.plugins()
                     if artifact == 'maven-surefire-plugin' and plugin.findtext('version')), None)
    if surefire:
        pom, raw = surefire
        value = _resolve(raw.strip(), properties)
        try:
            _add(c, 'build_tool', 'surefire', 'registry', 'pinned', 'plugin', pom, '<artifactId>maven-surefire-plugin',
                 series(parse_version(value or '')), listed=parse_version(value or ''))
        except VersionSyntaxError:
            _add(c, 'build_tool', 'surefire', 'registry', 'pinned', 'unparsed', pom, '<artifactId>maven-surefire-plugin', None,
                 reason=f'surefire version {raw!r} does not resolve')


def _wrappers(c: Collector) -> None:
    for path, name, pattern in (('.mvn/wrapper/maven-wrapper.properties', 'maven', r'apache-maven-(\d+(?:\.\d+)*)-bin'),
                                ('gradle/wrapper/gradle-wrapper.properties', 'gradle', r'gradle-(\d+(?:\.\d+)*)-(?:bin|all)')):
        if (text := c.text(path)) is not None:
            match = re.search(r'distributionUrl\s*=\s*\S*?' + pattern, text)
            try:
                parse_version(match[1]) if match else None
            except VersionSyntaxError:
                match = None
            if match:
                version = parse_version(match[1])
                c.add('build_tool', name, 'image', 'pinned', 'wrapper', path, 'distributionUrl', series(version), listed=version)
            else:
                c.unparsed('build_tool', name, 'image', path, 'distributionUrl', 'wrapper distribution not recognised')


GRADLE_LEVEL = re.compile(r'''(sourceCompatibility|targetCompatibility|languageVersion)\s*(?:=|\.set\()?\s*(?:JavaVersion\.VERSION_|JavaLanguageVersion\.of\(|['"])?(1[._]\d+|\d+)''')
GRADLE_DEP = re.compile(r'''['"](junit:junit|org\.junit\.jupiter:junit-jupiter[\w-]*|org\.testng:testng):(\d[\w.\-]*)['"]''')


def _gradle(c: Collector) -> None:
    for path in ('build.gradle', 'build.gradle.kts'):
        if (text := c.text(path)) is None: continue
        c.add('build_tool', 'gradle', 'image', 'constraint', 'build-script', path, '', ANY)
        for match in GRADLE_LEVEL.finditer(text):
            feature = java_feature(parse_version(match[2].replace('_', '.')))[0]
            if match[1] == 'languageVersion':
                c.add('runtime', 'jdk', 'image', 'pinned', 'toolchain', path, match[0], series((feature,)), listed=(feature,))
            else:
                c.add('runtime', 'jdk', 'image', 'constraint', 'compiler-target', path, match[0], compiler_jdks(feature))
                c.add('runtime', 'jdk', 'image', 'tested', 'derived', path, match[0], series((max(feature, 8),)), listed=(max(feature, 8),))
        for match in GRADLE_DEP.finditer(text):
            family = 'junit4' if match[1] == 'junit:junit' else 'testng' if 'testng' in match[1] else 'junit5'
            try:
                c.add('test_framework', family, 'registry', 'constraint', 'dependency', path, match[0], series(parse_version(match[2])), listed=parse_version(match[2]))
            except VersionSyntaxError:
                c.unparsed('test_framework', family, 'registry', path, match[0], 'version not numeric')


def _jdk_value(raw: str) -> int | None:
    match = JDK_TOKEN.search(raw.strip())
    if not match: return None
    return java_feature(parse_version(match[1]))[0]


def _ci(c: Collector) -> None:
    for path, value, source in ci_versions(c, CI_KEYS, ('jdk',)):
        feature = _jdk_value(value)
        if feature is None:
            c.unparsed('runtime', 'jdk', 'image', path, value, f'not a JDK release: {value!r}', strength='tested')
        else:
            c.add('runtime', 'jdk', 'image', 'tested', source, path, value, series((feature,)), listed=(feature,))
    if (text := c.text('Jenkinsfile')) is not None:
        found = False
        for match in re.finditer(r'''jdkVersions\s*:\s*\[([^\]]*)\]|jdk\s*:\s*['"]?(\d+)|tool\s+name\s*:\s*['"]JDK\s*(1\.\d+|\d+)''', text):
            for raw in (match[1].split(',') if match[1] else [match[2] or match[3]]):
                raw = raw.strip().strip('\'"')
                if raw and raw != 'null' and (feature := _jdk_value(raw)) is not None:
                    c.add('runtime', 'jdk', 'image', 'tested', 'ci', 'Jenkinsfile', match[0], series((feature,)), listed=(feature,))
                    found = True
        if not found and 'buildPlugin' in text:
            c.unparsed('runtime', 'jdk', 'image', 'Jenkinsfile', 'buildPlugin', 'buildPlugin() without jdkVersions uses the shared library default', strength='tested')
    for path in ('.java-version', '.sdkmanrc', '.tool-versions'):
        if (text := c.text(path)) is not None:
            if path == '.java-version':
                values = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith('#')][:1]
            else:
                values = [m[1].strip() for m in re.finditer(r'^\s*java\s*[=\s]\s*(\S+)', text, re.M)]
            for value in values:
                feature = _version_file_jdk(value)
                if feature is None:
                    c.unparsed('runtime', 'jdk', 'image', path, value, f'not a JDK release: {value[:40]!r}', strength='pinned')
                else:
                    c.add('runtime', 'jdk', 'image', 'pinned', 'version-file', path, value, series((feature,)), listed=(feature,))


def _version_file_jdk(value: str) -> int | None:
    """The JDK feature release in a jenv, SDKMAN or asdf name: `17`, `1.8`, `openjdk64-17.0.2`, `oracle64-1.8.0.292`,
    `17.0.2-tem`, `temurin-17.0.2+8`. The version starts the value or follows `-`/`_`, so a `64` in a vendor name is not
    read as the release; `system` and other names without one are unread."""
    match = re.search(r'java(\d+)(?=\D|$)', value) or re.search(r'(?:^|[-_])(1\.\d+|\d+)(?=[.+_-]|$)', value)
    if not match: return None
    try:
        return java_feature(parse_version(match[1]))[0]
    except VersionSyntaxError:
        return None


def detect(c: Collector, parents: Mapping[str, bytes]) -> None:
    _maven(c, parents)
    _gradle(c)
    _wrappers(c)
    _ci(c)
