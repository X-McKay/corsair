"""SPEC-0042: build metadata to runtime requirement, and selection against the runtime matrix (offline)."""
import pytest

from corsair.nodes.runtime.detect import detect, is_build_file
from corsair.nodes.runtime.matrix import Matrix, load, select
from corsair.nodes.runtime.versions import (gem, maven, npm, parse_set, parse_version, pep440, perl, java_feature,
                                            VersionSyntaxError)


def v(text):
    return parse_version(text)


@pytest.mark.parametrize('spec, inside, outside', [
    ('>=3.6, !=3.7.*, <4', ['3.6', '3.8.1', '3.12'], ['3.5', '3.7.4', '4.0']),
    ('~=3.8', ['3.8', '3.12'], ['3.7', '4.0']),
    ('==3.9.*', ['3.9.0', '3.9.18'], ['3.10']),
])
def test_pep440(spec, inside, outside):
    versions = pep440(spec)
    assert all(versions.contains(v(x)) for x in inside) and not any(versions.contains(v(x)) for x in outside)


@pytest.mark.parametrize('spec, inside, outside', [
    ('^24.8.0', ['24.8.0', '24.9.1'], ['25.0.0', '24.7.9']),
    ('^0.4.5', ['0.4.9'], ['0.5.0']),
    ('~1.2.3', ['1.2.9'], ['1.3.0']),
    ('>=4.0', ['4.0.0', '22.1.0'], ['0.12.0']),
    ('>= 6 <10 || 12.x', ['6.1.0', '12.4.0'], ['10.0.0', '13.0.0']),
    ('1.2 - 2.3', ['1.2.0', '2.3.9'], ['2.4.0']),
    ('*', ['0.1.0'], []),
])
def test_npm(spec, inside, outside):
    versions = npm(spec)
    assert all(versions.contains(v(x)) for x in inside) and not any(versions.contains(v(x)) for x in outside)


def test_gem_maven_perl_java_naming():
    assert gem(['~> 2.5']).contains(v('2.9')) and not gem(['~> 2.5']).contains(v('3.0'))
    assert gem(['~> 2.5.1']).contains(v('2.5.9')) and not gem(['~> 2.5.1']).contains(v('2.6'))
    assert maven('[1.8,)', java_feature).contains(v('17')) and not maven('[1.8,)', java_feature).contains(v('7'))
    assert maven('(,11],[17,21)').contains(v('11')) and not maven('(,11],[17,21)').contains(v('12'))
    assert maven('1.8', java_feature).contains(v('21'))  # enforcer: a bare version is a minimum
    assert perl('5.008001') == (5, 8, 1) and perl('5.00503') == (5, 5, 30) and perl('v5.10') == (5, 10)
    assert java_feature(v('1.8')) == (8,) and java_feature(v('17.0.2')) == (17,)
    with pytest.raises(VersionSyntaxError): pep440('>=3.6rc1')


@pytest.mark.parametrize('spec', ['>=3.6, !=3.7.*, <4', '==3.9.*', '^1.2.3 || 4.x'])
def test_canonical_round_trip(spec):
    versions = npm(spec) if '^' in spec else pep440(spec)
    assert parse_set(str(versions)) == versions


def files(**named):
    return {path.replace('__', '/').replace('_dot_', '.'): text.encode() for path, text in named.items()}


def component(requirement, kind, name):
    found = requirement.component(kind, name)
    assert len(found) == 1, requirement.components
    return found[0]


WORKFLOW = """
name: tests
on: push
jobs:
  test:
    strategy:
      matrix:
        python: ['3.8', '3.9', 3.10, 'pypy-3.9', '3.12-dev']
    steps:
      - uses: actions/setup-python@v5
        with: {python-version: '${{ matrix.python }}'}
      - run: tox -e py
  publish:
    steps:
      - uses: actions/setup-python@v5
        with: {python-version: '3.13'}
      - run: python -m build
"""


def test_python_ci_outranks_classifiers_and_keeps_310():
    requirement = detect({
        'setup.cfg': b'[metadata]\nclassifiers =\n    Programming Language :: Python :: 3.7\n    Programming Language :: Python :: 3.8\n'
                     b'[options]\npython_requires = >=3.7\n[tool:pytest]\n',
        '.github/workflows/tests.yml': WORKFLOW.encode(),
    }, 'python')
    runtime = component(requirement, 'runtime', 'cpython')
    assert runtime.allowed == '3.8.* || 3.9.* || 3.10.*' and runtime.preferred == '3.10'
    assert {u.reason for u in runtime.unparsed} == {"not a CPython release: 'pypy-3.9'", "not a CPython release: '3.12-dev'"}
    assert '3.13' not in runtime.allowed  # the publish job runs nothing test-like
    assert component(requirement, 'test_framework', 'pytest').declared


def test_setup_py_is_parsed_not_run_and_tox_expands():
    requirement = detect({
        'setup.py': b"import os\nos.system('exit 1')\nsetup(python_requires='>=3.5', tests_require=['pytest>=6,<7'])\n",
        'tox.ini': b'[tox]\nenvlist = py3{6,7}-django, py38\n[testenv]\ncommands = pytest\n',
    }, 'python')
    assert component(requirement, 'runtime', 'cpython').allowed == '3.6.* || 3.7.* || 3.8.*'
    assert component(requirement, 'test_framework', 'pytest').allowed == '6.*'


PARENT = b"""<project><modelVersion>4.0.0</modelVersion><groupId>org.example</groupId><artifactId>parent</artifactId>
<version>3</version><properties><maven.compiler.source>1.8</maven.compiler.source><junit.version>4.12</junit.version></properties>
<dependencyManagement><dependencies><dependency><groupId>junit</groupId><artifactId>junit</artifactId>
<version>${junit.version}</version></dependency></dependencies></dependencyManagement></project>"""
CHILD = b"""<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<parent><groupId>org.example</groupId><artifactId>parent</artifactId><version>3</version></parent>
<artifactId>child</artifactId><build><plugins><plugin><artifactId>maven-enforcer-plugin</artifactId><executions><execution>
<configuration><rules><requireJavaVersion><version>[1.8,)</version></requireJavaVersion></rules></configuration>
</execution></executions></plugin></plugins></build></project>"""


def test_maven_inherits_from_supplied_parent():
    requirement = detect({'pom.xml': CHILD}, 'java', parents={'org.example:parent:3': PARENT})
    assert component(requirement, 'runtime', 'jdk').allowed == '8.*'
    assert component(requirement, 'test_framework', 'junit4').allowed == '4.12.*'
    assert requirement.unresolved == ()


def test_maven_missing_parent_is_unresolved_not_guessed():
    requirement = detect({'pom.xml': CHILD}, 'java')
    assert requirement.unresolved == ('parent POM org.example:parent:3 not available',)
    assert component(requirement, 'runtime', 'jdk').allowed == '>=8'  # the enforcer alone
    selection = select(requirement, load())
    assert selection.status == 'undetermined' and 'test framework not identified' in selection.missing


def test_maven_refuses_markup_declarations_and_junit3():
    doctype = b'<!DOCTYPE x [<!ENTITY a "b">]><project><artifactId>a</artifactId></project>'
    requirement = detect({'pom.xml': doctype, 'other/pom.xml': CHILD}, 'java')
    assert any('markup declaration refused' in u.reason for c in requirement.components for u in c.unparsed)
    junit3 = PARENT.replace(b'4.12', b'3.8.2')
    assert detect({'pom.xml': junit3}, 'java').component('test_framework', 'junit3')


def test_java_ci_jdks_and_compiler_level():
    pom = PARENT.replace(b'1.8', b'1.7')
    travis = b'language: java\njdk:\n  - openjdk7\n  - oraclejdk8\n  - openjdk11\n'
    runtime = component(detect({'pom.xml': pom, '.travis.yml': travis}, 'java'), 'runtime', 'jdk')
    # JDK 11 is tested in CI and still compiles target 7, so it stays; JDK 20+ could not compile it.
    assert runtime.allowed == '7.* || 8.* || 11.*' and runtime.preferred == '11'


def test_javascript_engines_pins_lockfile_and_framework():
    package = b'{"engines": {"node": ">=8"}, "scripts": {"test": "npm run unit", "unit": "jest --ci"}, "devDependencies": {"jest": "^24.8.0"}}'
    requirement = detect({'package.json': package, '.nvmrc': b'v10\n', 'package-lock.json': b'{"lockfileVersion": 1}'}, 'javascript')
    assert component(requirement, 'runtime', 'node').allowed == '10.*'
    assert component(requirement, 'build_tool', 'npm').allowed == '>=5,<7'
    assert component(requirement, 'test_framework', 'jest').allowed == '>=24.8.0,<25'
    custom = detect({'package.json': b'{"scripts": {"test": "node test.js"}}'}, 'javascript')
    assert select(custom, load()).status == 'undetermined'


def test_ruby_gemspec_lock_and_ci():
    requirement = detect({
        'x.gemspec': b"s.required_ruby_version = Gem::Requirement.new('>= 2.5.0')\ns.add_development_dependency('minitest', '~> 5.14')\n",
        'Gemfile': b"source 'https://rubygems.org'\ngemspec\n",
        'Gemfile.lock': b'GEM\n  specs:\n    minitest (5.14.4)\n\nBUNDLED WITH\n   2.3.14\n',
        '.github/workflows/test.yml': b"jobs:\n  t:\n    strategy:\n      matrix:\n        ruby: ['2.7', '3.0', 'jruby']\n    steps:\n      - run: bundle exec rake test\n",
    }, 'ruby')
    assert component(requirement, 'runtime', 'ruby').allowed == '2.7.* || 3.0.*'
    assert component(requirement, 'test_framework', 'minitest').allowed == '==5.14.4'
    assert component(requirement, 'build_tool', 'bundler').preferred == '2.3.14'


def test_perl_decimal_minimum_and_ci():
    requirement = detect({'Makefile.PL': b"use 5.008_001;\nWriteMakefile(MIN_PERL_VERSION => '5.008001');\n",
                          '.travis.yml': b'language: perl\nperl:\n  - "5.30"\n  - "5.8"\n  - blead\n'}, 'perl')
    runtime = component(requirement, 'runtime', 'perl')
    assert runtime.allowed == '>=5.8.1,<5.9 || 5.30.*' and runtime.preferred == '5.30'
    assert component(requirement, 'test_framework', 'tap-harness').declared


def test_language_choice():
    both = {'package.json': b'{}', 'Gemfile': b''}
    assert 'several ecosystems' in detect(both)
    assert detect({'README.md': b''}) == 'no build files recognised at the project root'
    assert detect(both, 'ruby').language == 'ruby'
    assert is_build_file('a/b/pom.xml') and not is_build_file('node_modules/x/package.json') and not is_build_file('src/x.py')


def python_project(requires, pytest='>=7'):
    return detect({'pyproject.toml': f'[project]\nrequires-python = "{requires}"\noptional-dependencies = {{test = ["pytest{pytest}"]}}\n'.encode()}, 'python')


def test_selection_supported_unsupported_conflict():
    matrix = load()
    supported = select(python_project('>=3.9'), matrix)
    assert supported.status == 'supported' and supported.image_id == 'cpython-3.12-pytest'
    old = select(python_project('>=3.7,<3.12'), matrix)
    assert old.status == 'unsupported' and [(n.name, n.allowed) for n in old.needs] == [('cpython', '>=3.7,<3.12')]
    old_pytest = select(python_project('>=3.9', '==6.2.5'), matrix)
    assert old_pytest.status == 'unsupported' and [n.name for n in old_pytest.needs] == ['pytest']
    conflict = detect({'pyproject.toml': b'[project]\nrequires-python = ">=3.10"\n', '.python-version': b'3.8.12\n',
                       'pytest.ini': b''}, 'python')
    assert select(conflict, matrix).status == 'undetermined'
    java17 = detect({'pom.xml': PARENT.replace(b'1.8', b'17').replace(b'junit</groupId><artifactId>junit',
                                                                         b'org.junit.jupiter</groupId><artifactId>junit-jupiter').replace(b'4.12', b'5.14.4')}, 'java')
    selection = select(java17, matrix)
    assert selection.status == 'unsupported' and [n.name for n in selection.needs] == ['junit5']  # no Maven runner row yet
    with_runner = Matrix.model_validate({**matrix.model_dump(), 'frameworks': [*matrix.model_dump()['frameworks'], {
        'name': 'junit5', 'language': 'java', 'versions': '>=5.13', 'runner': 'x',
        'qualification': {'records': ['SPEC-0039'], 'report': 'x'}}]})
    assert select(java17, with_runner).status == 'supported'


def test_matrix_refuses_selector_rows_and_duplicates():
    data = load().model_dump()
    data['images'][0]['selector'] = {'JAVA_HOME': '/opt/jdk8'}
    with pytest.raises(ValueError, match='selector'): Matrix.model_validate(data)
    data = load().model_dump()
    data['images'] = [*data['images'], data['images'][0]]
    with pytest.raises(ValueError, match='duplicate'): Matrix.model_validate(data)
