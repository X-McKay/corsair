"""SPEC-0042: build metadata to runtime requirement, and selection against the runtime matrix (offline)."""
from pathlib import Path

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
        'name': 'junit5', 'language': 'java', 'versions': '>=5.13', 'runner': 'x', 'images': ['temurin-17-maven'],
        'qualification': {'records': ['SPEC-0039'], 'report': 'x'}}]})
    assert select(java17, with_runner).status == 'supported'
    # SPEC-0045 rows, staged here until the live gate passes (a row is added only with passing evidence).
    staged = Matrix.model_validate({**matrix.model_dump(), 'images': [*matrix.model_dump()['images'], STAGED_JDK8],
                                    'frameworks': [*matrix.model_dump()['frameworks'], *STAGED_JUNIT]})
    assert select(java17, staged).image_id == 'temurin-17-maven'
    java8 = detect({'pom.xml': PARENT}, 'java')  # source 1.8 with JUnit 4.12
    selection = select(java8, staged)
    assert selection.status == 'supported' and selection.image_id == 'temurin-8-maven'
    # JUnit 4 before 4.12 has no Vintage discovery (SPEC-0041); the JDK alone is not enough.
    old_junit = select(detect({'pom.xml': PARENT.replace(b'4.12', b'4.8.2')}, 'java'), staged)
    assert old_junit.status == 'unsupported' and [n.name for n in old_junit.needs] == ['junit4']
    # The environment agent's `junit4` ready result is admitted by the JDK 8 selection, and only there.
    from corsair.agents.environment.contracts import ReadyEnvironment
    from corsair.nodes.runtime.environment import check_ready
    prepared = {'temurin-8-maven': 'docker.io/library/corsair-java8@sha256:' + '0' * 64}
    ready = lambda framework: ReadyEnvironment.model_construct(toolchain_id='temurin-8-maven',
                                                               toolchain_image=prepared['temurin-8-maven'], framework=framework)
    check_ready(ready('junit4'), selection, prepared)
    with pytest.raises(ValueError, match='not one the selection admitted'):
        check_ready(ready('junit5'), selection, prepared)


STAGED_JDK8 = {'id': 'temurin-8-maven', 'language': 'java',
               'base_image': 'docker.io/library/maven@sha256:f2cb52730ea0bde9dc8ba20e5e539d000dcdd7ab9e498d70c301fe04fbddb656',
               'image_source': 'deploy/qualification/toolchains/java8', 'runtime': {'name': 'jdk', 'version': '8.0.504'},
               'tools': {'maven': '3.10.0'}, 'selector': {}, 'qualification': {'records': ['SPEC-0045'], 'report': 'x'}}
STAGED_JUNIT = [{'name': 'junit4', 'language': 'java', 'versions': '==4.13.2 || ==4.12', 'runner': 'x', 'images': ['temurin-8-maven'],
                 'qualification': {'records': ['SPEC-0045'], 'report': 'x'}},
                {'name': 'junit5', 'language': 'java', 'versions': '==5.14.4', 'runner': 'x', 'images': ['temurin-17-maven'],
                 'qualification': {'records': ['SPEC-0045'], 'report': 'x'}}]



# SPEC-0056 image row, staged here until its live gate passes; runtime and make are what the image measured.
STAGED_PERL526 = {'id': 'perl-5.26-make', 'language': 'perl',
                  'base_image': 'docker.io/library/perl@sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7',
                  'image_source': 'deploy/qualification/toolchains/perl526', 'runtime': {'name': 'perl', 'version': '5.26.3'},
                  'tools': {'make': '4.2.1'}, 'selector': {}, 'qualification': {'records': ['SPEC-0056'], 'report': 'x'}}


def test_perl526_row_meets_runtime_and_make_and_waits_for_a_tap_runner():
    fixture = Path(__file__).resolve().parents[2] / 'deploy/qualification/toolchains/perl526/Makefile.PL'
    requirement = detect({'Makefile.PL': fixture.read_bytes()}, 'perl')
    matrix = load().model_dump()
    staged = Matrix.model_validate({**matrix, 'images': [*matrix['images'], STAGED_PERL526]})
    # No Corsair runner and report parser for TAP yet, so no framework row: the image alone does not run a case.
    selection = select(requirement, staged)
    assert selection.status == 'unsupported' and [n.name for n in selection.needs] == ['tap-harness']
    assert [check.name for check in selection.rejected[0].unmet] == ['tap-harness']
    runner = {'name': 'tap-harness', 'language': 'perl', 'versions': '==3.38', 'runner': 'x', 'images': ['perl-5.26-make'],
              'qualification': {'records': ['SPEC-0056'], 'report': 'x'}}
    selection = select(requirement, Matrix.model_validate({**staged.model_dump(), 'frameworks': [*matrix['frameworks'], runner]}))
    assert selection.status == 'supported' and selection.image_id == 'perl-5.26-make'
    # A project that needs a newer Perl is not routed to 5.26.
    newer = detect({'Makefile.PL': fixture.read_bytes().replace(b"'5.026'", b"'5.028'")}, 'perl')
    assert select(newer, staged).status == 'unsupported' and 'perl' in [n.name for n in select(newer, staged).needs]

def test_matrix_refuses_selector_rows_and_duplicates():
    data = load().model_dump()
    data['images'][0]['selector'] = {'JAVA_HOME': '/opt/jdk8'}
    with pytest.raises(ValueError, match='selector'): Matrix.model_validate(data)
    data = load().model_dump()
    data['images'] = [*data['images'], data['images'][0]]
    with pytest.raises(ValueError, match='duplicate'): Matrix.model_validate(data)


def pom(body: str) -> bytes:
    return f'<project><modelVersion>4.0.0</modelVersion><groupId>g</groupId><artifactId>a</artifactId><version>1</version>{body}</project>'.encode()


COMPILER = '<plugin><artifactId>maven-compiler-plugin</artifactId><configuration><release>17</release></configuration></plugin>'


def test_review_findings_java():
    # Plugin configuration beats the property default; the toolchains plugin's own version is not a JDK.
    both = pom('<properties><maven.compiler.source>1.8</maven.compiler.source></properties>'
               f'<build><plugins>{COMPILER}<plugin><artifactId>maven-toolchains-plugin</artifactId><version>3.1.0</version>'
               '<configuration><toolchains><jdk><version>17</version></jdk></toolchains></configuration></plugin></plugins></build>')
    assert component(detect({'pom.xml': both}, 'java'), 'runtime', 'jdk').allowed == '17.*'
    # Only the java line of a multi-tool version file counts.
    tools = detect({'pom.xml': pom(''), '.tool-versions': b'nodejs 18.12.0\njava temurin-11.0.2\n'}, 'java')
    assert component(tools, 'runtime', 'jdk').allowed == '11.*'
    # Self-referential properties stay bounded and unresolved.
    blowup = pom('<properties><a>' + '${a}' * 64 + '</a><maven.compiler.release>${a}</maven.compiler.release></properties>')
    assert not component(detect({'pom.xml': blowup}, 'java'), 'runtime', 'jdk').declared
    # An unresolved input makes selection undetermined even when the rest would match.
    child = pom(f'<parent><groupId>x</groupId><artifactId>p</artifactId><version>1</version></parent>'
                f'<build><plugins>{COMPILER}</plugins></build><dependencies><dependency><groupId>org.junit.jupiter</groupId>'
                '<artifactId>junit-jupiter</artifactId><version>5.14.4</version></dependency></dependencies>')
    assert select(detect({'pom.xml': child}, 'java'), load()).status == 'undetermined'


@pytest.mark.parametrize('files', [
    {'pyproject.toml': b'project = "x"\ntool = 3\n'},
    {'setup.py': b'', '.github/workflows/t.yml': b'jobs: [1, 2]\n'},
    {'setup.py': b'', '.github/workflows/t.yml': b'jobs:\n  t:\n    name: test\n    strategy:\n      matrix:\n        python: &a [*a]\n'},
    {'setup.py': b'', '.travis.yml': b'python: ["3.8.1.2.3.4.5.6.7"]\nmatrix: {include: 3}\n'},
])
def test_malformed_python_inputs_do_not_crash(files):
    assert detect(files, 'python').language == 'python'


def test_malformed_other_inputs_do_not_crash():
    assert detect({'Makefile.PL': b'', 'META.json': b'{nope'}, 'perl').language == 'perl'
    assert detect({'package.json': b'{"packageManager": "npm@1.2.3.4.5.6.7.8.9"}'}, 'javascript').language == 'javascript'
    assert detect({'Gemfile': b'', 'Gemfile.lock': b'    minitest (5.1.2.3.4.5.6.7.8.9)\n'}, 'ruby').language == 'ruby'
    assert detect({'pom.xml': pom(''), '.mvn/wrapper/maven-wrapper.properties': b'distributionUrl=x/apache-maven-3.8.1.1.1.1.1.1.1-bin.zip'}, 'java')


def test_review_findings_versions():
    from corsair.nodes.runtime.versions import poetry
    assert str(poetry('~=3.8')) == '>=3.8,<4' and str(poetry('^3.7')) == '>=3.7,<4' and str(poetry('>=3.6,<3.10')) == '>=3.6,<3.10'
    assert npm('>8.0.0').lowest is None
    assert component(detect({'requirements-dev.txt': b'pytest==7.4.0  # pinned\n', 'setup.py': b''}, 'python'),
                     'test_framework', 'pytest').allowed == '==7.4.0'
    ci = b'jobs:\n  t:\n    strategy:\n      matrix:\n        node-version: [16.x, 18.x]\n    steps:\n      - run: npm test\n'
    assert component(detect({'package.json': b'{}', '.github/workflows/t.yml': ci}, 'javascript'), 'runtime', 'node').allowed == '16.* || 18.*'


def test_unread_hard_constraint_is_undetermined_not_supported():
    # Al's review of eac99a2: requires-python '>=3.13rc1' is unread, yet a 3.12.15 pin used to select CPython 3.12.15.
    files = {'pyproject.toml': b'[project]\nrequires-python = ">=3.13rc1"\noptional-dependencies = {test = ["pytest>=9,<10"]}\n',
             '.python-version': b'3.12.15\n'}
    selection = select(detect(files, 'python'), load())
    assert selection.status == 'undetermined' and 'pyproject.toml' in selection.missing[0]
    # An unread tested alternative (a CI PyPy or dev job) does not block.
    ci = b'jobs:\n  test:\n    strategy:\n      matrix:\n        python: ["3.12", "pypy-3.10", "3.13-dev"]\n    steps:\n      - run: pytest\n'
    tested = detect({'pyproject.toml': b'[project]\noptional-dependencies = {test = ["pytest>=9,<10"]}\n',
                     '.github/workflows/t.yml': ci}, 'python')
    assert component(tested, 'runtime', 'cpython').unparsed and select(tested, load()).status == 'supported'
    # An unread framework constraint cannot be the qualified runner when the runtime fits.
    framework = {'pyproject.toml': b'[project]\nrequires-python = ">=3.9"\noptional-dependencies = {test = ["pytest>=9.0rc1"]}\n',
                 'pytest.ini': b''}
    selection = select(detect(framework, 'python'), load())
    assert selection.status == 'undetermined' and selection.missing[0].startswith('pytest test framework declaration not understood')


def test_poetry_lock_reads_project_metadata_not_first_package():
    lock = (b'[[package]]\nname = "backports.zoneinfo"\nversion = "0.2.1"\npython-versions = ">=3.6,<3.10"\n\n'
            b'[metadata]\nlock-version = "2.0"\npython-versions = ">=3.8"\ncontent-hash = "x"\n')
    project = b'[tool.poetry.dependencies]\npython = ">=3.8"\n[tool.poetry.dev-dependencies]\npytest = "^9.0"\n'
    requirement = detect({'pyproject.toml': project, 'poetry.lock': lock}, 'python')
    runtime = component(requirement, 'runtime', 'cpython')
    assert runtime.allowed == '>=3.8' and {e.line for e in runtime.evidence if e.path == 'poetry.lock'} == {8}
    assert select(requirement, load()).status == 'supported'


@pytest.mark.parametrize('pipfile', [b'requires = "3.12"\n', b'packages = ["pytest"]\n', b'[requires]\npython_version = 3.12\n'])
def test_malformed_pipfile_structure_is_recorded_not_raised(pipfile):
    requirement = detect({'Pipfile': pipfile, 'pytest.ini': b''}, 'python')
    assert any(u.path == 'Pipfile' for c in requirement.components for u in c.unparsed)
    assert select(requirement, load()).status == 'undetermined'


def test_framework_rows_scoped_to_images():
    # A framework range qualified on one image must not be claimed by another image of the same language.
    data = load().model_dump()
    py312 = data['images'][0]
    py37 = {**py312, 'id': 'cpython-3.7-pytest', 'runtime': {'name': 'cpython', 'version': '3.7.17'}}
    old = {**data['frameworks'][0], 'versions': '>=6.0,<8', 'images': ['cpython-3.7-pytest']}
    new = {**data['frameworks'][0], 'images': ['cpython-3.12-pytest']}
    matrix = Matrix.model_validate({**data, 'images': [py312, py37, *data['images'][1:]], 'frameworks': [new, old]})
    wide = lambda pytest: python_project('>=3.7', pytest)
    assert select(wide('>=9,<10'), matrix).image_id == 'cpython-3.12-pytest'
    assert select(python_project('>=3.7,<3.8', '>=9,<10'), matrix).status == 'unsupported'  # pytest 9 not qualified on 3.7
    assert select(python_project('>=3.7,<3.8', '==6.2.5'), matrix).image_id == 'cpython-3.7-pytest'
    assert select(python_project('>=3.12', '==6.2.5'), matrix).status == 'unsupported'  # pytest 6 not qualified on 3.12
    with pytest.raises(ValueError, match='duplicate framework row'):
        Matrix.model_validate({**data, 'images': [py312, py37], 'frameworks': [new, {**old, 'images': [py312['id'], py37['id']]}]})
    with pytest.raises(ValueError, match='at least 1'):
        Matrix.model_validate({**data, 'frameworks': [{**new, 'images': []}]})
    # Al's re-review of dbbb980: a new image row without its own framework row gets no framework support.
    unscoped = Matrix.model_validate({**data, 'images': [py312, py37, *data['images'][1:]]})
    probe = detect({'pyproject.toml': b'[project]\nrequires-python = ">=3.7,<3.8"\n[tool.pytest.ini_options]\n'}, 'python')
    assert select(probe, unscoped).status == 'unsupported'
    with pytest.raises(ValueError, match='not a python row'):
        Matrix.model_validate({**data, 'frameworks': [{**old, 'images': ['temurin-17-maven']}]})


def test_pipfile_full_version_narrows_the_series():
    # Al's re-review of dbbb980: python_full_version was dropped when python_version was also present.
    pipfile = b'[requires]\npython_version = "3.12"\npython_full_version = "3.12.14"\n[dev-packages]\npytest = ">=9,<10"\n'
    runtime = component(detect({'Pipfile': pipfile}, 'python'), 'runtime', 'cpython')
    assert runtime.allowed == '==3.12.14'
    assert select(detect({'Pipfile': pipfile}, 'python'), load()).status == 'unsupported'  # the image is 3.12.15
    pinned = detect({'Pipfile': pipfile, '.python-version': b'3.12.15\n'}, 'python')
    assert select(pinned, load()).status == 'undetermined'  # conflicting pins
    malformed = detect({'Pipfile': pipfile.replace(b'"3.12.14"', b'3'), '.python-version': b'3.12.15\n'}, 'python')
    assert select(malformed, load()).status == 'undetermined'


def test_present_malformed_values_block_instead_of_disappearing():
    # Al's re-review: a non-string requires-python was dropped and selection reported supported.
    files = {'pyproject.toml': b'[project]\nrequires-python = 313\n', '.python-version': b'3.12.15\n',
             'requirements.txt': b'pytest>=9,<10\n'}
    selection = select(detect(files, 'python'), load())
    assert selection.status == 'undetermined' and 'requires-python is int' in selection.missing[0]
    # Al's re-review: non-object dependencies raised TypeError; they are now recorded against the framework.
    for dependencies in (b'["mocha"]', b'"mocha"'):
        package = b'{"dependencies": %s, "scripts": {"test": "mocha"}, "engines": {"node": ">=8"}}' % dependencies
        requirement = detect({'package.json': package}, 'javascript')
        assert any('dependencies is' in u.reason for c in requirement.components for u in c.unparsed)
    # A non-string framework version is unread, not "any version".
    jest = detect({'package.json': b'{"devDependencies": {"jest": 24}, "scripts": {"test": "jest"}}'}, 'javascript')
    assert not component(jest, 'test_framework', 'jest').declared
    # Poetry's table form of a dependency is read; Perl META structure is checked.
    poetry_table = b'[tool.poetry.dependencies]\npython = ">=3.9"\n[tool.poetry.dev-dependencies]\npytest = {version = "^9.0"}\n'
    assert component(detect({'pyproject.toml': poetry_table}, 'python'), 'test_framework', 'pytest').allowed == '>=9.0,<10'
    meta = detect({'Makefile.PL': b'', 'META.json': b'{"prereqs": {"runtime": [1]}}'}, 'perl')
    assert component(meta, 'runtime', 'perl').unparsed


def test_structurally_malformed_metadata_never_raises():
    # Seeded sweep of valid TOML/JSON/YAML with wrong shapes through detect and select (Al's re-review asked for
    # malformed-structure cases, not only syntax errors). A raise here would abort a whole benchmark batch.
    import json, random
    rng, matrix = random.Random(7), load()
    keys = ['project', 'requires', 'packages', 'dev-packages', 'metadata', 'requires-python', 'python-versions', 'tool', 'poetry',
            'build-system', '_meta', 'engines', 'scripts', 'dependencies', 'devDependencies', 'dev-dependencies', 'packageManager',
            'prereqs', 'runtime', 'jobs', 'matrix', 'strategy', 'include', 'steps', 'with', 'python', 'python-version', 'node_js',
            'perl', 'test', 'pytest', 'jest', 'version', 'python_version', 'python_full_version', 'optional-dependencies', 'node',
            'dependency-groups', 'include-group', 'group', 'uv']
    leaves = [1, 1.5, True, [], ['x'], [1, {}], 'x', '>=3', '3.12']

    def value(depth):
        r = rng.random()
        if depth > 3 or r < 0.35: return rng.choice(leaves)
        if r < 0.45: return [value(depth + 1) for _ in range(rng.randint(1, 2))]
        return {rng.choice(keys): value(depth + 1) for _ in range(rng.randint(1, 3))}

    def toml(v):
        if isinstance(v, bool): return 'true' if v else 'false'
        if isinstance(v, (int, float)): return str(v)
        if isinstance(v, str): return json.dumps(v)
        if isinstance(v, list): return '[' + ', '.join(toml(x) for x in v) + ']'
        return '{' + ', '.join(f'{json.dumps(k)} = {toml(x)}' for k, x in v.items()) + '}'

    targets = [('python', 'setup.py', f) for f in ('pyproject.toml', 'Pipfile', 'poetry.lock', 'uv.lock', 'Pipfile.lock', '.travis.yml',
                                                     '.github/workflows/ci.yml')]
    targets += [('javascript', 'package.json', f) for f in ('package.json', 'appveyor.yml')]
    targets += [('perl', 'Makefile.PL', f) for f in ('META.json', 'META.yml')]
    for _ in range(300):
        doc = {rng.choice(keys): value(1) for _ in range(rng.randint(1, 3))}
        for language, marker, path in targets:
            body = '\n'.join(f'{json.dumps(k)} = {toml(v)}' for k, v in doc.items()) if path in ('pyproject.toml', 'Pipfile', 'poetry.lock', 'uv.lock') \
                else json.dumps(doc)
            requirement = detect({marker: b'{}' if marker == 'package.json' else b'', path: body.encode()}, language)
            if not isinstance(requirement, str): select(requirement, matrix)


def test_tox_expansion_and_oversized_sets_are_bounded():
    # Al's re-review: eight {1,2} groups made 256 versions and raised Component.allowed's length check.
    tox = b'[tox]\nenvlist = py' + b'{1,2}' * 8 + b'\n[testenv]\ncommands = pytest\n'
    selection = select(detect({'tox.ini': tox}, 'python'), load())
    assert selection.status == 'undetermined' and 'envlist expands to more than' in selection.missing[0]
    many = '\n'.join(f'          - "3.{n}"' for n in range(200)).encode()
    ci = b'jobs:\n  test:\n    strategy:\n      matrix:\n        python:\n' + many + b'\n    steps:\n      - run: pytest\n'
    runtime = component(detect({'setup.py': b'', '.github/workflows/t.yml': ci}, 'python'), 'runtime', 'cpython')
    assert not runtime.declared and 'over the 512-character limit' in runtime.unparsed[0].reason


@pytest.mark.parametrize('files', [
    {'pyproject.toml': b'[tool.poetry.dependencies]\npython = "^3.12"\n[tool.poetry.group.dev.dependencies]\npytest = "^7.4"\n[tool.pytest.ini_options]\n'},
    {'pyproject.toml': b'[project]\nrequires-python = ">=3.12"\n[dependency-groups]\ntest = ["pytest>=7,<8"]\ndev = [{include-group = "test"}]\n'},
    {'pyproject.toml': b'[project]\nrequires-python = ">=3.12"\n[tool.uv]\ndev-dependencies = ["pytest>=7,<8"]\n'},
    {'setup.py': b'', '.python-version': b'3.12.15\n', 'test-requirements.txt': b'pytest>=7,<8\n'},
    {'setup.py': b'', '.python-version': b'3.12.15\n', 'dev_requirements.txt': b'pytest>=7,<8\n'},
])
def test_modern_pytest_constraints_are_read(files):
    # Al's re-review: Poetry groups, PEP 735 groups, uv dev lists and *-requirements.txt were missed, so a <8 project
    # was reported supported on the pytest 9 runner.
    assert all(is_build_file(path) for path in files)
    requirement = detect(files, 'python')
    assert parse_set(component(requirement, 'test_framework', 'pytest').allowed).contains(v('7.4'))
    assert select(requirement, load()).status == 'unsupported'


@pytest.mark.parametrize('include', ['["test"]', '{name = "test"}', '1', '"missing"'])
def test_malformed_include_group_is_unparsed_not_raised(include):
    # Al's review of f61e948: a list or table include-group raised TypeError (unhashable) instead of blocking.
    toml = f'[project]\nrequires-python = ">=3.12"\n[dependency-groups]\ntest = ["pytest>=9"]\ndev = [{{include-group = {include}}}]\n'
    requirement = detect({'pyproject.toml': toml.encode()}, 'python')
    assert 'include-group' in component(requirement, 'test_framework', 'pytest').unparsed[0].reason
    assert select(requirement, load()).status == 'undetermined'


def test_poetry_source_without_version_is_unread():
    # Al's f61e948 review nit: a git-sourced pytest has no declared version, so it cannot count as the 9.0 runner.
    toml = b'[tool.poetry.dependencies]\npython = "^3.12"\n[tool.poetry.group.dev.dependencies]\npytest = {git = "https://example.invalid/pytest.git"}\n[tool.pytest.ini_options]\n'
    requirement = detect({'pyproject.toml': toml}, 'python')
    assert 'names no version' in component(requirement, 'test_framework', 'pytest').unparsed[0].reason
    assert select(requirement, load()).status == 'undetermined'


def test_java_unread_pins_and_version_file_names():
    junit = ('<dependencies><dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId>'
             '<version>5.14.0</version></dependency></dependencies>')
    matrix = Matrix.model_validate({**load().model_dump(), 'frameworks': [*load().model_dump()['frameworks'], {
        'name': 'junit5', 'language': 'java', 'versions': '5.14.*', 'runner': 'x', 'images': ['temurin-17-maven'],
        'qualification': {'records': ['SPEC-0039'], 'report': 'x'}}]})
    base = '<properties><maven.compiler.release>17</maven.compiler.release></properties>'
    assert select(detect({'pom.xml': pom(base + junit)}, 'java'), matrix).status == 'supported'
    # Al's re-review: an unreadable or undefined toolchains JDK pin was dropped and 17 was selected.
    for version in ('21-ea', '${tc.jdk}'):
        toolchain = (f'<build><plugins><plugin><artifactId>maven-toolchains-plugin</artifactId><configuration><toolchains>'
                     f'<jdk><version>{version}</version></jdk></toolchains></configuration></plugin></plugins></build>')
        assert select(detect({'pom.xml': pom(base + toolchain + junit)}, 'java'), matrix).status == 'undetermined'
    # A family with one readable and one unresolved version counts as unread.
    engine = junit.replace('</dependencies>', '<dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter-engine'
                           '</artifactId><version>${engine}</version></dependency></dependencies>')
    assert select(detect({'pom.xml': pom(base + engine)}, 'java'), matrix).status == 'undetermined'
    # jenv names: the 64 in a vendor name is not the release; `system` is an unread pin.
    for name, allowed in ((b'openjdk64-17.0.2\n', '17.*'), (b'oracle64-1.8.0.292\n', '8.*')):
        assert component(detect({'pom.xml': pom(''), '.java-version': name}, 'java'), 'runtime', 'jdk').allowed == allowed
    system = component(detect({'pom.xml': pom(''), '.java-version': b'system\n'}, 'java'), 'runtime', 'jdk')
    assert not system.declared and system.unparsed[0].strength == 'pinned'
