import json
import hashlib
from pathlib import Path

import pytest

from tests.qualification.support import Kubectl, NetworkFixture, ROOT, LOCK, require_platform, require_owned_cluster


@pytest.fixture(scope="session")
def kube(request):
    config = request.config
    path = config.getoption("--kubeconfig")
    context = config.getoption("--context")
    evidence_arg = config.getoption("--evidence-dir")
    if not path or not evidence_arg or context != "kind-corsair":
        pytest.fail("Live qualification requires --kubeconfig, --context kind-corsair, --evidence-dir")
    kubeconfig = Path(path).resolve()
    if kubeconfig != ROOT / ".state/kind/kubeconfig":
        pytest.fail("This gate only mutates the explicitly owned local kind cluster")
    if not kubeconfig.is_file() or not (ROOT / ".state/kind/owner.json").is_file():
        pytest.fail("Owned kind state is missing; bootstrap did not finish. Inspect .runs/bootstrap before retrying")
    binary = ROOT / ".tools" / LOCK["platform"] / "kubectl"
    if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != LOCK["kubectl"]["sha256"]:
        pytest.fail("Run make tools for the checksum-verified native kubectl")
    evidence = Path(evidence_arg).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    evidence.chmod(0o700)
    if any(evidence.iterdir()):
        pytest.fail("Evidence directory must be empty; prior results cannot be overwritten")
    (evidence / "runtime-lock.yaml").write_text((ROOT / "deploy/runtime-lock.yaml").read_text())
    client = Kubectl(kubeconfig, context, evidence)
    node = require_owned_cluster(client)
    (evidence / "scope.json").write_text(json.dumps({"scope": "single-node local kind platform qualification", "openshell_gateway_admitted": False, "node_uid": node["metadata"]["uid"]}, indent=2))
    yield client


@pytest.fixture
def network(kube, request):
    require_platform(kube)
    fixture = NetworkFixture(kube, request.node.name)
    request.node.user_properties.append(("evidence", str(fixture.evidence)))
    try:
        fixture.setup()
        yield fixture
    finally:
        fixture.cleanup()
