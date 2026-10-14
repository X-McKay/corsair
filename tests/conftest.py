"""Live-gate options; registered here so root-level runs load them before collection."""


def pytest_addoption(parser):
    parser.addoption("--kubeconfig", help="Explicit owned local kind kubeconfig; no ambient fallback")
    parser.addoption("--context", help="Explicit kind-corsair context")
    parser.addoption("--evidence-dir", help="New host-owned evidence directory")
