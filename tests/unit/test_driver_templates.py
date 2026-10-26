"""Pure-helper behavior of the trusted in-image driver, exercised without a container.

These cover template selection and job admission only. The real control/violation/
exception/coverage behavior is a Docker integration concern (test_docker_python_command_sentinel).
"""

from __future__ import annotations

import pytest

from corsair.adapters.sandboxing.drivers.python import driver


def _job(kind: str) -> dict:
    return {
        "schema_version": "corsair.driver-job/1",
        "operation_id": "op",
        "role": "control",
        "source_digest": "a" * 64,
        "submission_digest": "b" * 64,
        "recipe": {"kind": kind, "module_file": "app.py"},
        "payload": "x",
    }


def test_every_recipe_kind_has_exactly_one_template() -> None:
    assert set(driver.TEST_TEMPLATES) == {
        "python.secret_disclosure/1",
        "python.command_sentinel/1",
    }
    # The retained alias still points at the initial disclosure template.
    assert driver.TEST_TEMPLATES["python.secret_disclosure/1"] == driver.TEST_SOURCE


def test_templates_are_distinct_and_carry_their_own_assertion() -> None:
    disclosure = driver.TEST_TEMPLATES["python.secret_disclosure/1"]
    sentinel = driver.TEST_TEMPLATES["python.command_sentinel/1"]
    assert disclosure != sentinel
    assert "disclosed the private fixture" in disclosure
    assert "created the operator sentinel file" in sentinel
    # Both share the common invocation helpers.
    for template in (disclosure, sentinel):
        assert "def _invoke():" in template
        assert "def test_operator_owned_recipe_assertions():" in template


def test_sentinel_marker_is_an_admitted_violation_marker() -> None:
    assert "sentinel_created" in driver.VIOLATION_MARKERS
    assert "disclosure" in driver.VIOLATION_MARKERS


def test_safe_job_accepts_both_known_recipe_kinds() -> None:
    for kind in driver.TEST_TEMPLATES:
        assert driver._safe_job(_job(kind))["recipe"]["kind"] == kind


def test_safe_job_rejects_an_unknown_recipe_kind() -> None:
    with pytest.raises(ValueError, match="unsupported recipe kind"):
        driver._safe_job(_job("python.unknown/9"))


def test_safe_job_rejects_a_recipe_without_a_kind() -> None:
    job = _job("python.command_sentinel/1")
    del job["recipe"]["kind"]
    with pytest.raises(ValueError, match="unsupported recipe kind"):
        driver._safe_job(job)
