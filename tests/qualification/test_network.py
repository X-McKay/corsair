import pytest

from tests.qualification.support import require_platform

pytestmark = pytest.mark.platform


def test_platform_ready(kube):
    require_platform(kube)


def test_ingress_selection_and_rollback(network):
    network.allowed("probe-allowed")
    network.allowed("probe-denied")
    network.policy("ingress.yaml")
    network.denied()
    network.remove_policy("ingress.yaml")
    network.allowed("probe-denied", converge=True)


def test_egress_denial_and_narrow_allow(network):
    network.allowed("probe-allowed")
    network.allowed("probe-denied")
    network.policy("egress-deny.yaml")
    network.denied()
    network.policy("egress-allow.yaml")
    network.allowed("probe-denied", converge=True)
    network.remove_policy("egress-allow.yaml")
    network.remove_policy("egress-deny.yaml")
    network.allowed("probe-denied", converge=True)
