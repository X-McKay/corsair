import json
from pathlib import Path

import pytest

from tests.qualification.support import Kubectl, NetworkFixture, ROOT, require_platform


def pytest_addoption(parser):
    parser.addoption("--kubeconfig", help="Explicit owned local kind kubeconfig; no ambient fallback")
    parser.addoption("--context", help="Explicit kind-corsair context")
    parser.addoption("--evidence-dir", help="New host-owned evidence directory")


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
    evidence = Path(evidence_arg).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    evidence.chmod(0o700)
    if any(evidence.iterdir()):
        pytest.fail("Evidence directory must be empty; prior results cannot be overwritten")
    (evidence / "runtime-lock.yaml").write_text((ROOT / "deploy/runtime-lock.yaml").read_text())
    client = Kubectl(kubeconfig, context, evidence)
    server = client.run("config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}").stdout
    if not server.startswith("https://127.0.0.1:"):
        pytest.fail("Qualification requires a localhost-bound kind API")
    nodes = client.get("nodes")["items"]
    if len(nodes) != 1 or nodes[0]["metadata"]["name"] != "corsair-control-plane":
        pytest.fail("Unexpected cluster topology; refusing mutations")
    (evidence / "scope.json").write_text(json.dumps({"scope": "single-node local kind network qualification", "openshell_admitted": False, "node_uid": nodes[0]["metadata"]["uid"]}, indent=2))
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
