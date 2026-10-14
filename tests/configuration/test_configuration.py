"""Static isolation guardrails; these never qualify live enforcement."""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_local_cluster_does_not_use_default_kind_networking():
    config = yaml.safe_load((ROOT / "deploy/kind/cluster.yaml").read_text())
    assert config["networking"]["disableDefaultCNI"] is True
    assert config["networking"]["apiServerAddress"] == "127.0.0.1"
    assert config["networking"]["podSubnet"] == "192.168.0.0/16"
    assert config["nodes"] == [{"role": "control-plane"}]


def test_runtime_and_workload_pins_are_immutable():
    lock = yaml.safe_load((ROOT / "deploy/runtime-lock.yaml").read_text())
    digest = r"sha256:[0-9a-f]{64}"
    assert re.search("@" + digest + "$", lock["kubernetes"]["node_image"])
    for tool in ("kind", "kubectl", "calico"):
        assert re.fullmatch(r"[0-9a-f]{64}", lock[tool]["sha256"])
        assert lock[tool]["version"] in lock[tool]["url"]
    for pin in lock["calico"]["images"].values():
        assert re.fullmatch(digest, pin)
    for spec in lock["fixtures"].values():
        assert re.fullmatch(digest, spec["digest"])


def test_fixture_pods_have_no_credentials_or_host_access():
    lock = yaml.safe_load((ROOT / "deploy/runtime-lock.yaml").read_text())
    documents = list(yaml.safe_load_all((ROOT / "deploy/qualification/fixtures.yaml").read_text()))
    pods = [d for d in documents if d["kind"] == "Pod"]
    assert len(pods) == 3
    for pod in pods:
        spec = pod["spec"]
        assert spec["automountServiceAccountToken"] is False
        assert not spec.get("hostNetwork") and not spec.get("hostPID") and not spec.get("volumes")
        assert spec["securityContext"]["runAsNonRoot"] is True
        assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        for container in spec["containers"]:
            assert container["image"] in lock["fixtures"]
            security = container["securityContext"]
            assert security["allowPrivilegeEscalation"] is False
            assert security["readOnlyRootFilesystem"] is True
            assert security["capabilities"]["drop"] == ["ALL"]
            assert not security.get("privileged")
            assert container["resources"]["limits"]


def test_network_allows_are_namespace_local_and_port_scoped():
    for filename, direction, peer in (("ingress.yaml", "ingress", "from"), ("egress-allow.yaml", "egress", "to")):
        spec = yaml.safe_load((ROOT / "deploy/qualification" / filename).read_text())["spec"]
        assert spec["policyTypes"] == [direction.capitalize()]
        rule = spec[direction][0]
        assert rule["ports"] == [{"protocol": "TCP", "port": 5678}]
        assert len(rule[peer]) == 1
        assert list(rule[peer][0]) == ["podSelector"]
        assert rule[peer][0]["podSelector"]["matchLabels"]["app"] == "corsair-qualification"
    deny = yaml.safe_load((ROOT / "deploy/qualification/egress-deny.yaml").read_text())["spec"]
    assert deny["policyTypes"] == ["Egress"] and deny["egress"] == []
