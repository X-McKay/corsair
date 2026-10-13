"""E2E-0 over the OpenShell test workspace (SPEC-0032): every purpose runs in its own fresh sandbox.

The operator supplies the native adapters and one captured snapshot per fixture variant; this module
only maps purposes to variants and declares the sandbox environment the agents are told about. Model-
authored tests execute only inside the sandbox; the host never runs them.
"""
from hashlib import sha256
import json

from corsair.adapters.openshell_workspace import OpenShellTestWorkspace, WorkspaceConfig
from corsair.adapters.pytest_runner import PytestRunnerConfig
from corsair.investigation.frameworks import harness
from corsair.agents.test_planning.contracts import EnvironmentEvidence
from corsair.composition.direct import FixtureCase
from corsair.core.disposition import EnvironmentIdentity
from corsair.ports.artifacts import SourceSnapshot

from .case import REPOSITORY, VARIANTS, fixture_case
from .reviewed import REVIEWED_TEST

PYTHON = "/usr/local/bin/python3.12"
JUNIT = "/tmp/corsair-junit.xml"
WITNESS_RECORD = "/tmp/corsair-witness.json"
# Operator-owned in-sandbox pytest argv: no plugins, config or conftest from the workspace; scratch under /tmp.
PREFIX = ("/usr/bin/env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "PYTHONDONTWRITEBYTECODE=1", "PYTHONPATH=.", PYTHON,
          "-m", "pytest", "-c", "/dev/null", "--rootdir", ".", "--noconftest", "--import-mode=importlib",
          "-p", "no:cacheprovider", "--basetemp", "/tmp/corsair-scratch")
DISCOVER = PREFIX + ("--collect-only", "-q")
TOOLCHAIN = REPOSITORY / "deploy/qualification/toolchains/python"
POLICY = REPOSITORY / "policies/openshell/identity.yaml"


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _pytest_version() -> str:
    pins = dict(line.split(" ")[0].split("==") for line in (TOOLCHAIN / "requirements.txt").read_text().splitlines()
                if line.strip())
    return pins["pytest"]


def sandbox_case(snapshots: dict[str, SourceSnapshot], image_manifest_digest: str, limits: dict) -> FixtureCase:
    """The reviewed fixture issue with the sandbox's environment facts and each revision's captured manifest.

    Identity fields name operator-owned inputs (toolchain image manifest, argv, hash-pinned wheels, sandbox
    policy file, execution limits); they are declarations of what both revisions share, not observations.
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
        image_digest=image_manifest_digest.removeprefix("sha256:"), recipe_sha256=_digest(json.dumps(PREFIX).encode()),
        dependency_inventory_sha256=_digest((TOOLCHAIN / "wheels.json").read_bytes()),
        policy_revision=f"identity.yaml:{_digest(POLICY.read_bytes())[:16]}",
        limits_sha256=_digest(json.dumps(limits, sort_keys=True).encode()))
    return FixtureCase(issue=base.issue, environment=environment, environment_identity=identity,
                       witness_envelope=base.witness_envelope,
                       revision_sources={revision: snapshots[VARIANTS[revision]].manifest.sha256
                                         for revision in ("baseline", "candidate")})


def sandbox_runners(lifecycle, verifier, execution, upload, store, snapshots: dict[str, SourceSnapshot],
                    config: WorkspaceConfig):
    """A runner per purpose whose every run prepares a fresh sandbox from that purpose's captured variant.

    ``verifier`` executes at a fixed directory outside the workspace; ``execution`` at the workspace root.
    """
    workspaces = {variant: OpenShellTestWorkspace(lifecycle, verifier, upload, store, snapshot, config)
                  for variant, snapshot in snapshots.items()}
    runner_config = PytestRunnerConfig(PREFIX, JUNIT, config.remote_root, witness_record_path=WITNESS_RECORD)

    def runner(purpose):
        return harness("pytest").runner(workspaces[VARIANTS[purpose]], execution, store, runner_config)
    return runner
