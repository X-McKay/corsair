"""SPEC-0069: a runtime range inferred from framework release metadata when the build files declare none (offline)."""
import json

import pytest

from corsair.nodes.runtime.detect import detect
from corsair.nodes.runtime.matrix import Matrix, load, select


def selection(files, language):
    return select(detect(files, language), load())


def test_unpinned_pytest_without_a_runtime_takes_the_newest_image_and_says_it_was_inferred():
    chosen = selection({'requirements.txt': b'pytest\n'}, 'python')
    assert chosen.status == 'supported' and chosen.image_id == 'cpython-3.12-pytest'
    assert chosen.runtime_basis == 'inferred' and any('PyPI requires-python' in line for line in chosen.inferred_from)
    runtime = next(c for c in chosen.checks if c.kind == 'runtime')
    assert runtime.allowed == '>=3.10' and runtime.provided == '3.12.15'
    assert next(c for c in chosen.checks if c.kind == 'test_framework').provided == '9.0.*'


def test_a_framework_range_that_excludes_the_newest_row_selects_the_older_one():
    chosen = selection({'requirements.txt': b'pytest<8\n'}, 'python')
    assert chosen.status == 'supported' and chosen.image_id == 'cpython-3.7-pytest' and chosen.runtime_basis == 'inferred'
    pinned = next(c for c in chosen.checks if c.kind == 'test_framework').provided
    assert '7.4.4' in pinned and '9.0' not in pinned


def test_a_declared_runtime_is_never_replaced_by_inference():
    chosen = selection({'pyproject.toml': b'[project]\nrequires-python = ">=3.12"\ndependencies = ["pytest"]\n'}, 'python')
    assert chosen.status == 'supported' and chosen.runtime_basis == 'declared' and chosen.inferred_from == ()


def test_an_unread_runtime_constraint_blocks_inference():
    chosen = selection({'pyproject.toml': b'[project]\nrequires-python = 313\ndependencies = ["pytest"]\n'}, 'python')
    assert chosen.status == 'undetermined'


def test_framework_metadata_outside_every_image_names_the_runtime_range_it_needs():
    package = json.dumps({'scripts': {'test': 'jest'}, 'devDependencies': {'jest': '^29.7.0'}}).encode()
    chosen = selection({'package.json': package}, 'javascript')
    assert chosen.status == 'unsupported'
    assert {(n.kind, n.name, n.allowed) for n in chosen.needs} == {
        ('runtime', 'node', '>=14.15,<15 || >=16.10,<17 || >=18'), ('test_framework', 'jest', '>=29.7.0,<30')}


def test_a_framework_without_an_inference_row_stays_undetermined():
    package = json.dumps({'scripts': {'test': 'vitest run'}, 'devDependencies': {'vitest': '^2.1.9'}}).encode()
    chosen = selection({'package.json': package}, 'javascript')
    assert chosen.status == 'undetermined' and 'no inference row covers vitest' in chosen.missing[0]


def test_no_framework_keeps_the_runtime_gap_visible():
    chosen = selection({'package.json': json.dumps({'scripts': {'test': 'node --test'}}).encode()}, 'javascript')
    assert chosen.status == 'undetermined'
    assert any('runtime version not declared' in m for m in chosen.missing)
    assert any('test framework not identified' in m for m in chosen.missing)


def test_perl_without_a_version_infers_from_the_core_test_more():
    chosen = selection({'cpanfile': b"requires 'DBI';\n"}, 'perl')
    assert chosen.status == 'supported' and chosen.image_id == 'perl-5.26-make' and chosen.runtime_basis == 'inferred'
    assert chosen.evidence == 'image-only'


def test_an_inference_row_for_a_runtime_no_image_provides_is_refused():
    matrix = load().model_dump()
    matrix['inference'] = [*matrix['inference'], dict(framework='pytest', language='python', versions='9.0.*',
                                                      runtime='pypy', supports='>=7', source='x')]
    with pytest.raises(ValueError, match='no python image row provides'):
        Matrix.model_validate(matrix)


def test_without_inference_rows_selection_is_unchanged():
    matrix = Matrix.model_validate({**load().model_dump(), 'inference': []})
    chosen = select(detect({'requirements.txt': b'pytest\n'}, 'python'), matrix)
    assert chosen.status == 'undetermined' and 'runtime version not declared' in chosen.missing[0]


def test_minitest_without_a_ruby_version_infers_from_the_gem_metadata():
    chosen = selection({'Gemfile': b"source 'https://rubygems.org'\ngem 'minitest', '5.15.0'\n"}, 'ruby')
    assert chosen.status == 'supported' and chosen.image_id == 'ruby-3.1-bundler' and chosen.runtime_basis == 'inferred'
    assert next(c for c in chosen.checks if c.kind == 'runtime').allowed == '>=2.2,<4.0'


def test_when_only_a_declared_tool_rejects_the_inferred_image_the_tool_is_named():
    package = json.dumps({'scripts': {'test': 'jest'}, 'devDependencies': {'jest': '24.9.0'}, 'engines': {'npm': '>=7'}}).encode()
    chosen = selection({'package.json': package}, 'javascript')
    assert chosen.status == 'unsupported'
    assert [(n.kind, n.name) for n in chosen.needs] == [('build_tool', 'npm')]
