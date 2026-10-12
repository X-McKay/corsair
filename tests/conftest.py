"""Live-gate options; registered here so root-level runs load them before collection."""


def pytest_addoption(parser):
    parser.addoption("--kubeconfig", help="Explicit owned local kind kubeconfig; no ambient fallback")
    parser.addoption("--context", help="Explicit kind-corsair context")
    parser.addoption("--evidence-dir", help="New host-owned evidence directory")
    parser.addoption("--network-evidence", help="Successful exact-node CNI receipts required by policy qualification")
    parser.addoption("--temporal-address", help="Operator-owned local fixture service host:port")
    parser.addoption("--temporal-evidence-dir", help="Ignored destination for native histories")
