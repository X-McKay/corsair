"""Real host-enforced boundaries, not assertions about unrestricted native fixtures."""

import uuid

import pytest

from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.adapters.sandbox.docker import DockerSandboxes, docker, docker_available
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel
from corsair.domain.verification import Gate, Outcome
from tests.test_kernel import CASE, REFERENCE, ROW

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
needs_image = pytest.mark.skipif(
    not (docker_available() and docker("image", "inspect", ROW.image).returncode == 0),
    reason="Python Docker image unavailable",
)


@pytest.mark.parametrize(
    "operation",
    [
        "open('/work/documents.py', 'w').write('tampered')",
        "__import__('os').chmod('/work/documents.py', 0o777)",
    ],
)
@needs_image
async def test_probe_cannot_rewrite_or_reopen_frozen_source(tmp_path, operation):
    backend = DockerSandboxes()
    kernel = Kernel(
        backend,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        run_id=uuid.uuid4().hex[:12],
        framework=framework(ROW.framework),
    )
    probe = REFERENCE.probe.replace(
        "def run_target(payload: str) -> None:\n",
        "def run_target(payload: str) -> None:\n    " + operation + "\n",
    )
    result = await kernel.evaluate(REFERENCE.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].outcome is Outcome.ERRORED
    assert result.runs[0].exception_type == "PermissionError"
    assert backend.labelled(kernel.run_id) == []


@needs_image
async def test_clean_build_has_network_then_both_twins_are_offline(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(
        backend,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        run_id=uuid.uuid4().hex[:12],
        framework=framework(ROW.framework),
    )
    build = "python -c \"import urllib.request; assert urllib.request.urlopen('https://pypi.org/simple/pytest/', timeout=10).status == 200\""
    image, gate = kernel.build(kernel.case.revision, "vulnerable", build)
    assert gate.passed and image, gate
    from corsair.ports.sandbox import labels

    name = backend.open_environment(image, "/work", labels(kernel.run_id, "probe", "control"))
    try:
        inspect = docker("inspect", "--format", "{{.HostConfig.NetworkMode}} {{.Config.User}}", name)
        assert inspect.stdout.strip() == b"none 1000:1000"
    finally:
        assert backend.remove(name)
    assert backend.labelled(kernel.run_id) == []


@needs_image
async def test_build_cannot_replace_the_reported_target_before_it_is_frozen(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(
        backend,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        run_id=uuid.uuid4().hex[:12],
        framework=framework(ROW.framework),
    )
    submission = REFERENCE.model_copy(update={"build_script": "printf 'fabricated source\\n' > documents.py"})
    result = await kernel.evaluate(submission)
    assert result.gate.stage is Gate.BUILD_REPLAY
    assert "changed" in result.gate.reason and not result.runs
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.parametrize(
    "filename",
    [
        "test_corsair_probe.py",
        "collect_gcov.py",
        "collect_jacoco.py",
        "collect_perl_coverage.pl",
        "corsair-c8.json",
        "corsair_simplecov.rb",
    ],
)
@needs_image
async def test_kernel_support_files_cannot_be_changed_or_unlinked_by_a_probe(tmp_path, filename):
    from corsair.ports.sandbox import labels

    backend = DockerSandboxes()
    kernel = Kernel(
        backend,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        run_id=uuid.uuid4().hex[:12],
        framework=framework(ROW.framework),
    )
    image, gate = kernel.build(kernel.case.revision, "vulnerable", "")
    assert gate.passed
    name = backend.open_environment(image, "/work", labels(kernel.run_id, "probe", "control"))
    try:
        path = f"/work/.corsair/{filename}"
        backend.write_file(name, path, b"kernel owned\n")
        for operation in ['write_text("forged")', "unlink()"]:
            result = backend.exec_once(
                name,
                ["python", "-c", f"from pathlib import Path; Path({path!r}).{operation}"],
                workdir="/work",
            )
            assert result.exit_code != 0 and b"PermissionError" in result.stderr
        assert backend.copy_out(name, [path])[path] == b"kernel owned\n"
    finally:
        assert backend.remove(name)


@needs_image
async def test_build_cannot_change_an_unreported_helper(tmp_path):
    import shutil

    from corsair.domain.case import revision

    case = load_case(CASE)
    source = tmp_path / "source"
    shutil.copytree(case.revision.source, source)
    (source / "helper.py").write_text("def helper(): return 1\n")
    case = case.model_copy(update={"revision": revision(source)})
    backend = DockerSandboxes()
    kernel = Kernel(
        backend,
        ROW,
        case,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        framework=framework(ROW.framework),
    )
    result = await kernel.evaluate(REFERENCE.model_copy(update={"build_script": "echo forged > helper.py"}))
    assert result.gate.stage is Gate.BUILD_REPLAY and not result.runs


@needs_image
async def test_build_cannot_redirect_the_reserved_support_directory(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(
        backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path), framework=framework(ROW.framework)
    )
    result = await kernel.evaluate(
        REFERENCE.model_copy(update={"build_script": "rm -rf .corsair; ln -s /work .corsair"})
    )
    assert result.gate.stage is Gate.BUILD_REPLAY and not result.runs
