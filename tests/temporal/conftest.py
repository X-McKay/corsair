"""Explicit native service selection; no implicit service startup or downloads."""

import pytest


@pytest.fixture
def temporal_address(request):
    address = request.config.getoption("--temporal-address")
    if not address:
        pytest.skip("Native Temporal checks require an explicitly owned service")
    if not request.config.getoption("--temporal-evidence-dir"):
        pytest.fail("Native checks require --temporal-evidence-dir")
    return address
