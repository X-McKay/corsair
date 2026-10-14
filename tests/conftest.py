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
    parser.addoption("--test-shard", help="Run only shard k/n of the collected tests (CI splits the offline suite)")


def shard(items, spec):
    """Items of shard `k/n` (1-based): every n-th item from the k-th, so each shard gets a similar mix and together
    the n shards are exactly the collection. Every shard collects the same tests in the same order."""
    index, count = (int(part) for part in spec.split("/"))
    if not 1 <= index <= count:
        raise ValueError(f"--test-shard must be k/n with 1 <= k <= n, not {spec!r}")
    return items[index - 1::count]


def pytest_collection_modifyitems(config, items):
    """CI splits the offline suite over parallel jobs with --test-shard k/n; without it every test runs. An option,
    not an environment variable, so the pytest subprocesses some tests start never inherit it."""
    spec = config.getoption("--test-shard")
    if not spec:
        return
    keep = {id(item) for item in shard(items, spec)}
    config.hook.pytest_deselected(items=[item for item in items if id(item) not in keep])
    items[:] = [item for item in items if id(item) in keep]
