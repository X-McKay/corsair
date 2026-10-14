"""Shared evidence uses native runner identity, independent of framework spelling."""
import pytest
from corsair.ports.test_runner import native_test_function


@pytest.mark.parametrize('test_id,function', [
    ('test_case.py::test_security', 'test_security'),
    ('test_case.py::Tests::test_security', 'test_security'),
    ('case.test.js::suite::security', 'security'),
    ('test_case.rb::Module::Tests#test_security', 'test_security'),
    ('module/example.Tests#security', 'security'),
    ('t/case.t#security', 'security'),
])
def test_native_failure_function_is_the_reported_member(test_id, function):
    assert native_test_function(test_id) == function


@pytest.mark.parametrize('test_id', ['unknown', '../case.t#security', 'Tests#bad name'])
def test_unknown_identity_is_not_guessed(test_id):
    with pytest.raises(ValueError):
        native_test_function(test_id)


@pytest.mark.parametrize('baseline,baseline_path,path,name,container,expected', [
    ('old.py::test_existing', 'old.py', 'new.py', 'test_control', None, 'new.py::test_control'),
    ('old.py::Existing::test_existing', 'old.py', 'new.py', 'test_control', 'New', 'new.py::New::test_control'),
    ('old.js::existing', 'old.js', 'new.js', 'control', 'suite', 'new.js::suite::control'),
    ('old.rb::Old#test_existing', 'old.rb', 'new.rb', 'test_control', 'Module::New', 'new.rb::Module::New#test_control'),
    ('t/old.t#existing', 't/old.t', 't/new.t', 'control', None, 't/new.t#control'),
    ('core/example.Old#existing', 'core/src/test/java/example/Old.java', 'core/src/test/java/example/New.java', 'control', None, 'core/example.New#control'),
])
def test_runner_formats_explicit_components(baseline, baseline_path, path, name, container, expected):
    from corsair.ports.test_runner import format_test_id
    assert format_test_id(baseline, path, name, container, baseline_path=baseline_path) == expected


@pytest.mark.parametrize('baseline,baseline_path,path,name,container', [
    ('unknown', 'old.py', 'new.py', 'test_control', None),
    ('old.py::test_existing', 'unrelated.py', 'new.py', 'test_control', None),
    ('old.py::test_existing', 'old.py', 'new.py', 'test_control[value]', None),
    ('old.py::test_existing[value]', 'old.py', 'new.py', 'test_control', None),
    ('old.py::test_existing', 'old.py', 'new.js', 'test_control', None),
    ('old.rb::Old#test_existing', 'old.rb', 'new.rb', 'test_control', None),
    ('t/old.t#existing', 't/old.t', 't/new.t', 'control', 'Unexpected'),
    ('example.Old#existing', 'src/test/java/example/Old.java', 'src/test/java/example/New.java', 'control', 'example.Other'),
    ('old.py::test_existing', 'old.py', 'new.py', 'test_control', 'Nested::Class'),
])
def test_runner_refuses_unsupported_or_ambiguous_components(baseline, baseline_path, path, name, container):
    from corsair.ports.test_runner import format_test_id
    with pytest.raises(ValueError):
        format_test_id(baseline, path, name, container, baseline_path=baseline_path)
