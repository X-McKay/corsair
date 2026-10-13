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
