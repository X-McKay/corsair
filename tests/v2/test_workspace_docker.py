"""The Docker workspace against PydanticAI's own backend conformance suite, plus its config rules (no Docker)."""
import uuid

import pytest
from pydantic_ai.workspaces import Workspace, WorkspaceRef, WorkspaceUnavailableError
from pydantic_ai.workspaces.conformance import WorkspaceBackendSuite

from corsair.workspace import DockerConfig, DockerWorkspace, labels
from corsair.workspace.docker import docker, docker_available, remove, run_args

IMAGE = "corsair-python:ebf057997574de59"


def _image_present() -> bool:
    return docker_available() and docker("image", "inspect", IMAGE).returncode == 0


needs_docker = pytest.mark.skipif(not _image_present(), reason=f"docker or {IMAGE} unavailable")


def _config(**changes) -> DockerConfig:
    return DockerConfig(image=IMAGE, labels=labels(f"test-{uuid.uuid4().hex[:10]}", "conformance"), **changes)


def test_config_is_hardened_offline_and_named_by_labels():
    config = DockerConfig(image="img", labels=labels("run1", "build", "builder"))
    args = run_args(config)
    assert "--cap-drop=ALL" in args and "--security-opt=no-new-privileges" in args and "--network=none" in args
    assert args[args.index("--name") + 1] == config.name
    assert config.name == DockerConfig(image="other", labels=labels("run1", "build", "builder")).name
    assert config.name != DockerConfig(image="img", labels=labels("run2", "build", "builder")).name
    assert config.name.startswith("corsair-v2-run1-build-builder-")
    with pytest.raises(ValueError):
        DockerConfig(image="img", network="host")
    with pytest.raises(ValueError):
        DockerConfig(image="img", workdir="work/../x")


def test_building_does_no_io():
    backend = DockerWorkspace(DockerConfig(image="no-such-image-is-touched"))
    assert backend.ref is None


@needs_docker
class TestDockerWorkspaceConformance(WorkspaceBackendSuite):
    @pytest.fixture
    def backend(self):
        backend = DockerWorkspace(_config())
        yield backend
        remove(backend.name)

    @pytest.fixture
    def fresh_backend(self):
        made: list[DockerWorkspace] = []

        def build() -> DockerWorkspace:
            made.append(DockerWorkspace(_config()))
            return made[-1]

        yield build
        for backend in made:
            remove(backend.name)

    @pytest.fixture
    def attach_backend(self):
        return lambda ref: DockerWorkspace(DockerConfig(image=IMAGE), ref=ref)

    @pytest.fixture
    def destroy_environment(self):
        async def destroy(backend: DockerWorkspace) -> None:
            assert await backend.destroy()

        return destroy


@needs_docker
@pytest.mark.anyio
async def test_attach_to_a_missing_container_is_unavailable_and_never_creates():
    ref = WorkspaceRef(provider="docker", id=f"corsair-v2-missing-{uuid.uuid4().hex[:8]}")
    with pytest.raises(WorkspaceUnavailableError):
        await DockerWorkspace(DockerConfig(image=IMAGE), ref=ref).working_dir()
    assert docker("inspect", ref.id).returncode != 0


@needs_docker
@pytest.mark.anyio
async def test_copy_in_and_out_and_container_is_hardened(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("VALUE = 1\n")
    backend = DockerWorkspace(_config())
    try:
        await backend.copy_in(tmp_path)
        result = await backend.run(["sh", "-c", "id -u; cat pkg/mod.py; touch pkg/new && echo writable"])
        assert result.stdout.split("\n")[1:3] == ["VALUE = 1", "writable"]
        assert result.stdout.split("\n")[0] != "0"
        out = await backend.copy_out(["/work/pkg/mod.py", "/work/absent"])
        assert out == {"/work/pkg/mod.py": b"VALUE = 1\n", "/work/absent": None}
        inspected = docker("inspect", "--format", "{{.HostConfig.NetworkMode}} {{.HostConfig.CapDrop}} "
                           "{{index .Config.Labels \"corsair.v2\"}}", backend.name).stdout.decode()
        assert inspected.split() == ["none", "[ALL]", "1"]
        # The run ending never destroys the environment; only the owner does.
        assert await Workspace(backend).exists("/work/pkg/mod.py")
    finally:
        assert await backend.destroy()
