"""Explicit native service selection; no implicit service startup or downloads."""

import pytest


def pytest_addoption(parser):
    parser.addoption("--temporal-address", help="Operator-owned local fixture service host:port")
    parser.addoption("--temporal-evidence-dir", help="Ignored destination for native histories")


@pytest.fixture
def temporal_address(request):
    address = request.config.getoption("--temporal-address")
    if not address:
        pytest.skip("Native Temporal checks require an explicitly owned service")
    if not request.config.getoption("--temporal-evidence-dir"):
        pytest.fail("Native checks require --temporal-evidence-dir")
    return address
