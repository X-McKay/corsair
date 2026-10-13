"""E2E-0 under plain Docker: unqualified, risk accepted, for iterating without a kind/OpenShell cluster.

Every runner call is a fresh container of the operator's local CPython 3.12 toolchain image (the
`cpython-3.12-pytest` matrix row, built by `make toolchain-images TOOLCHAINS=python`) through the shared image-only
harness (`corsair.adapters.docker_image.DockerCase`): no network, all capabilities dropped, no new privileges, the
variant's source copied in fresh and the patch written next to it. A live author's tests run there, never on the
host, under the same pytest argv and witness probe as the OpenShell route. Plain Docker is not the qualified
sandbox: no OpenShell policy, gateway or admission stands behind it, so its evidence names the route and says it is
unqualified, and only the OpenShell route (`make qualify-fixture-e2e`) qualifies a result.
"""
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path

from corsair.adapters.docker_image import WORK, DockerCase, docker
from corsair.adapters.pytest_runner import PytestRunnerConfig
from corsair.agents.test_planning.contracts import EnvironmentEvidence
from corsair.composition.direct import FixtureCase
from corsair.core.disposition import EnvironmentIdentity
from corsair.investigation.frameworks import harness

from .case import FIXTURE, VARIANTS, fixture_case
from .reviewed import REVIEWED_TEST
from .sandbox import DISCOVER, JUNIT, PREFIX, TOOLCHAIN, WITNESS_RECORD, _pytest_version

ROW = "cpython-3.12-pytest"
SCRATCH = "/tmp/corsair-scratch"  # PREFIX's --basetemp
POLICY = "docker-offline-cap-drop-all"
ROUTE = {"route": "docker", "qualification": "unqualified",
         "basis": "plain Docker, risk accepted: --network=none, --cap-drop=ALL, no-new-privileges; no OpenShell "
                  "policy, gateway or admission"}


def _digest(value: str | bytes) -> str:
    return sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def source_label(variant: str) -> str:
    """What a variant's container is prepared from: the digest of its one source file, standing in for a commit."""
    return _digest((FIXTURE / variant / "documents.py").read_bytes())


def limits(timeout: int) -> dict:
    return {"network": "none", "capabilities": "drop-all", "timeout_seconds": timeout}


def docker_case(image: str, timeout: int) -> FixtureCase:
    """The reviewed fixture issue with the Docker route's environment facts; `image` is the local config id.

    Identity fields are declarations of what both revisions share (the image Docker runs, the argv, the image's
    hash-pinned wheels, the container flags), not sandbox observations. Each revision's source is the digest the
    Docker workspace records for the variant it copied.
    """
    base = fixture_case()
    environment = EnvironmentEvidence(
        language="Python", runtime="CPython 3.12", framework=f"pytest {_pytest_version()}",
        discovery_command=DISCOVER, approved_test_paths=(REVIEWED_TEST,), baseline_test=base.environment.baseline_test,
        scratch_location="The per-test pytest tmp_path directory under the operator's --basetemp; "
                         "fixtures must not be created elsewhere",
        observation_facilities=base.environment.observation_facilities,
        witness_facilities=base.environment.witness_facilities)
    identity = EnvironmentIdentity(
        image_digest=image.removeprefix("sha256:"), recipe_sha256=_digest(json.dumps(PREFIX)),
        dependency_inventory_sha256=_digest((TOOLCHAIN / "wheels.json").read_bytes()), policy_revision=POLICY,
        limits_sha256=_digest(json.dumps(limits(timeout), sort_keys=True)))
    return FixtureCase(issue=base.issue, environment=environment, environment_identity=identity,
                       witness_envelope=base.witness_envelope,
                       revision_sources={revision: _digest(source_label(VARIANTS[revision]))
                                         for revision in ("baseline", "candidate")})


def docker_runners(image: str, root: Path, store, stack: ExitStack, timeout: int):
    """A runner per call whose container holds a fresh copy of that purpose's variant; removed when `stack` closes.

    `root` is a new private directory for each variant's read-only tree and each container's preparation log."""
    trees = {}
    for variant in set(VARIANTS.values()):
        tree = root / "trees" / variant
        tree.mkdir(parents=True)
        (tree / "documents.py").write_bytes((FIXTURE / variant / "documents.py").read_bytes())
        trees[variant] = tree.resolve()
    config = PytestRunnerConfig(PREFIX, JUNIT, WORK, witness_record_path=WITNESS_RECORD)
    calls = []

    def runner(purpose):
        calls.append(purpose)
        logs = root / "runs" / f"{len(calls)}-{purpose}"
        logs.mkdir(parents=True)
        variant = VARIANTS[purpose]
        case = stack.enter_context(DockerCase(image, trees[variant], source_label(variant), timeout,
                                              kind="fixture-e2e", docker=docker, evidence=logs,
                                              scratch=(SCRATCH, JUNIT, WITNESS_RECORD)))
        return harness("pytest").runner(case, case, store, config)
    return runner
