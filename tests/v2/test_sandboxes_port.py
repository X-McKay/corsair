"""One conformance suite for the ``Sandboxes`` port, run against every backend that can honestly run it.

- ``docker``: needs Docker and the runtime matrix's first ``corsair-python`` image; skips otherwise.
- ``openshell``: needs ``CORSAIR_OPENSHELL_CONFIG`` (a live gateway); skips otherwise. ``CORSAIR_OPENSHELL_IMAGE``
  picks the mapped image tag to use (default: the first one in the operator's images map).

The OpenShell host double (``openshell_fake``) is not a backend here: it answers execs from scripts rather than
running them, so passing this suite on it would prove nothing. Its adapter logic is tested in
``test_workspace_openshell.py``.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from corsair.v2.contracts import Environment, Recipe, RecipeFile
from corsair.v2.intake import tree_sha256
from corsair.v2.workspace import Sandboxes, SandboxExists, SandboxSpec, labels
from tests.v2.live_cleanup import record_cleanup, remove_confirmed

MATRIX = Path(__file__).resolve().parents[2] / "deploy/v2/runtime-matrix.yaml"
DOCKER_IMAGE = next(row["image"] for row in yaml.safe_load(MATRIX.read_text())["rows"]
                    if row["image"].startswith("corsair-python:"))
OPENSHELL_CONFIG = os.environ.get("CORSAIR_OPENSHELL_CONFIG")


@dataclass
class Backend:
    sandboxes: Sandboxes
    image: str
    forget_environment: Callable[[str], None]


def _docker() -> Backend:
    from corsair.v2.workspace.docker import DockerSandboxes, docker, docker_available

    if not docker_available() or docker("image", "inspect", DOCKER_IMAGE).returncode != 0:
        pytest.skip(f"docker or {DOCKER_IMAGE} unavailable")

    def forget(tag: str) -> None:
        docker("image", "rm", "--force", tag)

    return Backend(DockerSandboxes(), DOCKER_IMAGE, forget)


def _openshell() -> Backend:
    if not OPENSHELL_CONFIG:
        pytest.skip("CORSAIR_OPENSHELL_CONFIG is not set (no gateway)")
    from corsair.v2.workspace.openshell import OpenShellSandboxes

    live = OpenShellSandboxes.from_config(Path(OPENSHELL_CONFIG))
    # The python image, so the network tests have an HTTPS client; else the operator's choice, else the first.
    image = (next((tag for tag in live.config.images if tag.startswith("corsair-python:")), None)
             or os.environ.get("CORSAIR_OPENSHELL_IMAGE") or next(iter(live.config.images)))

    def forget(tag: str) -> None:
        (live.config.state_dir / "environments" / f"{hashlib.sha256(tag.encode()).hexdigest()[:32]}.json").unlink(
            missing_ok=True)

    return Backend(live, image, forget)


@pytest.fixture(params=[pytest.param("docker"), pytest.param("openshell", marks=pytest.mark.openshell)])
def port(request) -> Iterator[Backend]:
    yield _docker() if request.param == "docker" else _openshell()


@pytest.fixture
def run_id(port) -> Iterator[str]:
    """A fresh run; every sandbox it labelled is removed afterwards and must be confirmed gone."""
    run = f"port-{uuid.uuid4().hex[:10]}"
    yield run
    assert remove_confirmed(port.sandboxes, port.sandboxes.labelled(run)) == []
    assert port.sandboxes.labelled(run) == []


def _spec(port: Backend, run: str, stage: str = "test", network: str = "none", **extra: str) -> SandboxSpec:
    return SandboxSpec(image=port.image, labels=labels(run, stage, **extra), network=network,
                       workdir=port.sandboxes.workdir)


def _sh(port: Backend, name: str, script: str, timeout: float = 60):
    return port.sandboxes.exec_once(name, ["sh", "-c", script], workdir=port.sandboxes.workdir, timeout=timeout)


def test_create_never_adopts(port, run_id):
    spec = _spec(port, run_id)
    name = port.sandboxes.create(spec)
    assert name == spec.name
    with pytest.raises(SandboxExists):
        port.sandboxes.create(spec)


def test_workdir_exists_and_the_command_user_owns_what_it_writes(port, run_id):
    name = port.sandboxes.create(_spec(port, run_id))
    result = _sh(port, name, 'test "$PWD" = "$1" && test -w . && mkdir made && echo "$(stat -c %u made) $(id -u)"'
                             .replace("$1", port.sandboxes.workdir))
    assert result.exit_code == 0, result.stderr
    owner, user = result.stdout.split()
    assert owner == user


def test_copy_tree_in_keeps_symlinks_as_links(port, run_id, tmp_path):
    tree = tmp_path / "tree"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "mod.py").write_text("VALUE = 1\n")
    secret = tmp_path / f"host-only-{uuid.uuid4().hex}"
    secret.write_text("host secret")
    (tree / "link").symlink_to(secret)
    name = port.sandboxes.create(_spec(port, run_id))
    port.sandboxes.copy_tree_in(name, tree, port.sandboxes.workdir)
    result = _sh(port, name, 'cat pkg/mod.py; readlink link; test -e link && echo followed || echo dangling; '
                             'touch pkg/new && echo writable')
    assert result.exit_code == 0, result.stderr
    assert result.stdout.decode().split("\n")[:4] == ["VALUE = 1", str(secret), "dangling", "writable"]


def test_write_file_and_copy_out(port, run_id):
    name = port.sandboxes.create(_spec(port, run_id))
    root = port.sandboxes.workdir
    port.sandboxes.write_file(name, f"{root}/deep/nested/file.txt", b"payload\x00\xff")
    assert _sh(port, name, "ln -s deep/nested/file.txt link && mkdir dir").exit_code == 0
    paths = [f"{root}/{path}" for path in ("deep/nested/file.txt", "missing", "link", "dir")]
    assert port.sandboxes.copy_out(name, paths) == dict(zip(paths, [b"payload\x00\xff", None, None, None]))


def test_exec_once_reports_exit_output_and_timeout(port, run_id):
    name = port.sandboxes.create(_spec(port, run_id))
    result = port.sandboxes.exec_once(name, ["sh", "-c", 'echo "$V"; echo err >&2; exit 3'], workdir=port.sandboxes.workdir,
                                      env={"V": "value"}, timeout=60)
    assert (result.exit_code, result.stdout, result.stderr) == (3, b"value\n", b"err\n")
    assert not (result.timed_out or result.container_failed)
    slow = port.sandboxes.exec_once(name, ["sleep", "60"], workdir=port.sandboxes.workdir, timeout=3)
    assert slow.timed_out and slow.exit_code is None


# One allowed HTTPS GET to a build host, through the sandbox's own tooling: prints the status, or the error.
_GET = ("import sys, urllib.request\n"
        "try:\n"
        "    print(urllib.request.urlopen('https://pypi.org/simple/pip/', timeout=20).status)\n"
        "except Exception as error:\n"
        "    print('failed', type(error).__name__, error)\n")


def test_drop_network_removes_build_egress(port, run_id):
    name = port.sandboxes.create(_spec(port, run_id, network="build"))
    if _sh(port, name, "command -v python3").exit_code != 0:
        pytest.skip(f"{port.image} has no python3 to make the HTTPS request")
    before = port.sandboxes.exec_once(name, ["python3", "-c", _GET], workdir=port.sandboxes.workdir, timeout=60)
    if before.stdout.strip() != b"200":
        if port.sandboxes.provider == "docker":
            pytest.skip(f"this host's Docker bridge does not reach pypi.org: {before.stdout!r}")
        pytest.fail(f"the build policy did not allow GET https://pypi.org: {before.stdout!r} {before.stderr!r}")
    port.sandboxes.drop_network(name)
    after = port.sandboxes.exec_once(name, ["python3", "-c", _GET], workdir=port.sandboxes.workdir, timeout=60)
    assert after.exit_code == 0 and after.stdout.startswith(b"failed"), after.stdout


def test_remove_is_confirmed_and_the_sandbox_is_then_gone(port, run_id):
    name = port.sandboxes.create(_spec(port, run_id))
    image = port.sandboxes.image_id(name)
    assert image is None or "sha256:" in image
    confirmed = port.sandboxes.remove(name)
    record_cleanup(port.sandboxes.provider, name, confirmed)
    assert confirmed is True
    assert port.sandboxes.exec_once(name, ["true"], workdir=port.sandboxes.workdir, timeout=30).container_failed
    assert port.sandboxes.remove(name) is True


def test_labelled_filters_by_run(port, run_id):
    other = f"{run_id}-other"
    mine = port.sandboxes.create(_spec(port, run_id, role="control"))
    theirs = port.sandboxes.create(_spec(port, other, role="control"))
    try:
        listed, others = port.sandboxes.labelled(run_id), port.sandboxes.labelled(other)
        assert len(listed) == 1 and len(others) == 1 and listed != others
        assert set(listed + others) <= set(port.sandboxes.labelled())
        assert mine != theirs
    finally:
        assert remove_confirmed(port.sandboxes, [theirs]) == []


def test_resolve_image_is_provenance_or_none(port):
    resolve = getattr(port.sandboxes, "resolve_image", None)
    if resolve is None:
        pytest.skip("this backend predates Sandboxes.resolve_image")
    assert resolve(f"corsair-unknown:{uuid.uuid4().hex[:8]}") is None
    assert resolve(port.image) is None or "sha256:" in resolve(port.image)


def test_seal_find_and_open_environment_round_trip(port, run_id, tmp_path):
    tree = tmp_path / "rev"
    tree.mkdir()
    (tree / "app.txt").write_text("source\n")
    recipe = Recipe(files=(RecipeFile(path="added.txt", content="from recipe\n"),),
                    setup=(("sh", "-c", "cat app.txt added.txt > built.txt"),),
                    baseline_test=("sh", "-c", "test -f built.txt"))
    digest = hashlib.sha256(json.dumps(recipe.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    tag = f"corsair-v2-env-port-test:{uuid.uuid4().hex[:16]}"
    environment = Environment(image=tag, workdir=port.sandboxes.workdir, runtime_row="port-test",
                              recipe_sha256=digest,
                              tree_sha256=tree_sha256(tree))
    try:
        assert port.sandboxes.find_environment(tag, "key") is None
        built = port.sandboxes.create(_spec(port, run_id, "build"))
        port.sandboxes.copy_tree_in(built, tree, port.sandboxes.workdir)
        port.sandboxes.write_file(built, f"{port.sandboxes.workdir}/added.txt", b"from recipe\n")
        assert port.sandboxes.exec_once(built, recipe.setup[0], workdir=port.sandboxes.workdir, timeout=60).exit_code == 0
        port.sandboxes.seal_environment(built, tag, "key", "c" * 64, recipe=recipe, tree_source=tree,
                                        base_image=port.image)
        assert remove_confirmed(port.sandboxes, [built]) == []
        assert port.sandboxes.find_environment(tag, "key") == "c" * 64
        assert port.sandboxes.find_environment(tag, "other-key") is None
        wanted = labels(run_id, "execute", "control")
        opened = port.sandboxes.open_environment(environment, wanted)
        assert opened == SandboxSpec(image=port.image, labels=wanted).name
        assert port.sandboxes.resolve_image(tag) is not None
        result = port.sandboxes.exec_once(opened, ["cat", "built.txt"], workdir=port.sandboxes.workdir, timeout=60)
        assert result.exit_code == 0 and result.stdout == b"source\nfrom recipe\n"
        with pytest.raises(SandboxExists):
            port.sandboxes.open_environment(environment, wanted)
    finally:
        port.forget_environment(tag)
