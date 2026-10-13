"""Live-gate options; registered here so root-level runs load them before collection."""


def pytest_addoption(parser):
    parser.addoption("--kubeconfig", help="Explicit owned local kind kubeconfig; no ambient fallback")
    parser.addoption("--context", help="Explicit kind-corsair context")
    parser.addoption("--evidence-dir", help="New host-owned evidence directory")
    parser.addoption("--network-evidence", help="Successful exact-node CNI receipts required by policy qualification")
    parser.addoption("--toolchain", action="append", help="Run only toolchain gates whose images are all named (repeatable)")
    parser.addoption("--temporal-address", help="Operator-owned local fixture service host:port")
    parser.addoption("--temporal-evidence-dir", help="Ignored destination for native histories")
    parser.addoption("--provider-config", help="Explicit LocalModelConfig JSON for live fixture E2E stages")
    parser.addoption("--e2e-live", help="Comma-separated fixture E2E stages to run on the provider")
    parser.addoption("--e2e-runs", help="Live fixture E2E runs after the scripted control (0-6)")
    parser.addoption("--e2e-stage-profiles", help="Optional per-stage provider profiles JSON for live fixture E2E")
