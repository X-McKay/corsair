"""Bounded native gateway qualification; shared admission fixture for 1C."""
import pytest
from tests.qualification.gateway import gateway


@pytest.mark.gateway
def test_gateway_tls_and_generated_identity(gateway):
    assert gateway['endpoint'].startswith('127.0.0.1:')
