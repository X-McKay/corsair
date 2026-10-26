"""Pytest plugin registration for Corsair's opt-in Temporal test fixtures."""

import os
import sys

import pytest

from scripts.check_toolchain import native_library_gap

pytest_plugins = ("tests.workflow.temporal",)


def pytest_configure() -> None:
    """Stop before collection when this interpreter cannot import the locked native wheels."""

    gap = native_library_gap(sys.base_prefix, sys.platform, os.environ.get("LD_LIBRARY_PATH", ""))
    if gap is not None:
        pytest.exit(gap.line(), returncode=pytest.ExitCode.USAGE_ERROR)
