"""Opt-in integration coverage for the official OpenShell v0.1.5 Docker gateway.

Run with ``CORSAIR_OPENSHELL_INTEGRATION=1`` only after setting the explicit local
OpenShell registration and Docker overlay described in the provider test harness.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import pytest
from openshell import SandboxClient
from openshell._proto import openshell_pb2, sandbox_pb2

from benchmarks.polyglot import generate
from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.adapters.sandbox.openshell import BUILD_USER, OpenShellSandboxes
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel
from corsair.domain.policy import terminal_verdict
from corsair.domain.verification import Fix, Label, Submission
from corsair.ports.sandbox import LABEL, SandboxSpec, labels
from corsair.runtime import matrix

CLI = os.environ.get("CORSAIR_OPENSHELL_CLI", "openshell")
BASE_IMAGE = os.environ.get("CORSAIR_OPENSHELL_TEST_IMAGE", "corsair-lite-python:dev")


def _policy() -> dict[str, object]:
    return {
        "network_policies": {
            "packages": {
                "name": "packages",
                "endpoints": [{"host": "registry.example", "port": 443}],
                "binaries": [{"path": "/usr/bin/pip"}],
            }
        }
    }


@pytest.fixture(scope="module", autouse=True)
def configured_gateway() -> None:
    if os.environ.get("CORSAIR_OPENSHELL_INTEGRATION") != "1":
        pytest.skip("set CORSAIR_OPENSHELL_INTEGRATION=1 to use the real OpenShell gateway")
    endpoint = os.environ.get("CORSAIR_OPENSHELL_GATEWAY_ENDPOINT")
    if not endpoint:
        pytest.fail("CORSAIR_OPENSHELL_GATEWAY_ENDPOINT is required when integration is opted in")
    try:
        response = subprocess.run(
            [CLI, "--gateway-endpoint", endpoint, "gateway", "info", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as error:
        pytest.fail(f"OpenShell CLI unavailable after integration opt-in: {error}")
    if response.returncode != 0:
        pytest.fail(f"OpenShell gateway is unavailable after integration opt-in: {response.stderr[-1000:]}")


def gateway_endpoint() -> str:
    endpoint = os.environ["CORSAIR_OPENSHELL_GATEWAY_ENDPOINT"]
    parsed = urlparse(endpoint if "://" in endpoint else f"//{endpoint}")
    assert parsed.hostname
    return f"{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


def backend() -> OpenShellSandboxes:
    return OpenShellSandboxes(
        endpoint=os.environ["CORSAIR_OPENSHELL_GATEWAY_ENDPOINT"], cli=CLI, build_policy=_policy()
    )


@pytest.fixture
def nonroot_workdir_image() -> Iterator[str]:
    """An isolated test derivative; never mutate the configured source runtime image."""
    tag = f"corsair-openshell-it:{uuid.uuid4().hex[:12]}"
    container = subprocess.run(
        ["docker", "create", "--entrypoint", "sh", BASE_IMAGE, "-c", "chown 1001:1001 /work"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    try:
        subprocess.run(["docker", "start", "-a", container], check=True, capture_output=True)
        subprocess.run(
            ["docker", "commit", "--change", f"USER {BUILD_USER}", container, tag],
            check=True,
            capture_output=True,
        )
        yield tag
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
        subprocess.run(["docker", "image", "rm", "-f", tag], capture_output=True, check=False)


@pytest.mark.openshell
def test_gateway_rejects_root_and_adapter_runs_nonroot_with_offline_replacement(
    nonroot_workdir_image: str,
) -> None:
    """A root policy rejection is terminal: the adapter instead sends 1001 and never falls back."""
    root_name = f"root-{uuid.uuid4().hex[:12]}"
    root_policy = sandbox_pb2.SandboxPolicy(
        version=1,
        filesystem=sandbox_pb2.FilesystemPolicy(include_workdir=True),
        process=sandbox_pb2.ProcessPolicy(run_as_user="0", run_as_group="0"),
    )
    root_spec = openshell_pb2.SandboxSpec(
        template=openshell_pb2.SandboxTemplate(image=nonroot_workdir_image, labels={LABEL: "1"}),
        policy=root_policy,
        command=["sleep", "infinity"],
    )
    with SandboxClient(gateway_endpoint(), timeout=30) as client:
        with pytest.raises(Exception, match="run_as_user must be 'sandbox' or a numeric UID/GID"):
            client.create(workspace="default", name=root_name, spec=root_spec, labels={LABEL: "1"})

    backend_ = backend()
    logical_labels = labels(f"openshell-{uuid.uuid4().hex[:8]}", "build")
    logical_name = backend_.create(SandboxSpec(nonroot_workdir_image, labels=logical_labels, network="build"))
    native_name = backend_._refs[logical_name].name
    try:
        assert logical_name != native_name and len(native_name) <= 19
        result = backend_.exec_once(
            logical_name,
            ["python3", "-c", "import os; print(os.getuid()); print(os.getcwd())"],
            workdir="/work",
            timeout=20,
        )
        assert result.exit_code == 0
        assert result.stdout == b"1001\n/work\n"
        backend_.drop_network(logical_name)
        assert backend_._refs[logical_name].current_policy_version >= 1
    finally:
        assert backend_.remove(logical_name)


@pytest.mark.openshell
def test_actual_python_kernel_reference_replay_has_verified_fix_and_cleanup(
    nonroot_workdir_image: str, tmp_path: Path
) -> None:
    """The real gateway completes both fresh offline twins, not merely an SDK lifecycle smoke."""
    paths = generate(tmp_path / "fixtures", ["python"])
    case = load_case(paths[0])
    selected = matrix.select(case)
    assert selected is not None
    submission = Submission.model_validate_json((paths[0] / "reference-submission.json").read_text())
    evaluation = asyncio.run(
        Kernel(
            backend(),
            selected.model_copy(update={"image": nonroot_workdir_image}),
            case,
            artifacts=ArtifactStore(tmp_path / "artifacts"),
            run_id=f"openshell-kernel-{uuid.uuid4().hex[:8]}",
            framework=framework(selected.framework),
        ).evaluate(submission)
    )
    verdict = evaluation.verdict or terminal_verdict(evaluation.gate, 1)

    assert verdict.label is Label.LIKELY_EXPLOITABLE
    assert verdict.fix is Fix.VERIFIED
    assert len(evaluation.runs) == 4
    assert all(run.cleanup_confirmed is True for run in evaluation.runs)
    assert all(run.covered_target is True for run in evaluation.runs)


@pytest.mark.openshell
def test_actual_foreign_build_support_file_blocks_source_sealing(
    nonroot_workdir_image: str, tmp_path: Path
) -> None:
    """A build cannot place importable lookalikes beside the kernel's trusted support files."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "original.py").write_text("value = 1\n")
    backend_ = backend()
    build_name = backend_.create(
        SandboxSpec(
            nonroot_workdir_image, labels=labels(f"openshell-{uuid.uuid4().hex[:8]}", "build"), network="none"
        )
    )
    try:
        backend_.copy_tree_in(build_name, source, "/work")
        created = backend_.exec_once(
            build_name,
            ["sh", "-c", "mkdir /work/.corsair && printf counterfeit > /work/.corsair/pathlib.py"],
            workdir="/work",
            timeout=20,
        )
        assert created.exit_code == 0
        assert backend_.source_unchanged(build_name, source) is False
    finally:
        assert backend_.remove(build_name)


@pytest.mark.openshell
def test_actual_builder_cache_replacement_is_not_prepared_again(nonroot_workdir_image: str) -> None:
    """A model-controlled replacement under /tmp cannot redirect a later archive copy."""
    backend_ = backend()
    build_name = backend_.create(
        SandboxSpec(
            nonroot_workdir_image, labels=labels(f"openshell-{uuid.uuid4().hex[:8]}", "build"), network="none"
        )
    )
    try:
        initial = backend_.exec_once(
            build_name,
            ["sh", "-c", "test -d /tmp/corsair-build && test ! -e /work/home"],
            workdir="/work",
            timeout=20,
        )
        replaced = backend_.exec_once(
            build_name,
            ["sh", "-c", "rm -rf /tmp/corsair-build && ln -s /work /tmp/corsair-build"],
            workdir="/work",
            timeout=20,
        )
        subsequent = backend_.exec_once(
            build_name,
            ["sh", "-c", "test -L /tmp/corsair-build && test ! -e /work/home"],
            workdir="/work",
            timeout=20,
        )
        assert initial.exit_code == replaced.exit_code == subsequent.exit_code == 0
    finally:
        assert backend_.remove(build_name)


@pytest.mark.openshell
def test_actual_offline_probe_cannot_overwrite_sealed_source_or_open_network(
    nonroot_workdir_image: str, tmp_path: Path
) -> None:
    """The /tmp OCI workdir admission workaround never makes immutable /work writable to uid 1000."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "immutable.txt").write_text("original\n")
    backend_ = backend()
    build_name = backend_.create(
        SandboxSpec(
            nonroot_workdir_image, labels=labels(f"openshell-{uuid.uuid4().hex[:8]}", "build"), network="none"
        )
    )
    image = f"corsair-openshell-sealed:{uuid.uuid4().hex[:12]}"
    try:
        backend_.copy_tree_in(build_name, source, "/work")
        backend_.seal_environment(
            build_name, image, "integration-key", "integration-log", writable=["/work/.corsair"]
        )
    finally:
        assert backend_.remove(build_name)

    probe_name = backend_.open_environment(
        image, "/work", labels(f"openshell-{uuid.uuid4().hex[:8]}", "probe", "control")
    )
    try:
        source_write = backend_.exec_once(
            probe_name, ["sh", "-c", "printf compromised > /work/immutable.txt"], workdir="/work", timeout=20
        )
        network = backend_.exec_once(
            probe_name,
            ["python", "-c", "import socket; socket.create_connection(('1.1.1.1', 443), 2)"],
            workdir="/work",
            timeout=20,
        )
        assert source_write.exit_code != 0
        assert network.exit_code != 0
        assert backend_.copy_out(probe_name, ["/work/immutable.txt"])["/work/immutable.txt"] == b"original\n"
    finally:
        assert backend_.remove(probe_name)
        subprocess.run(["docker", "image", "rm", "-f", image], capture_output=True, check=False)
