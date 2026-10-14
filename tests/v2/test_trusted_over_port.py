"""Trusted replay, probe execution and the reconciler over the ``Sandboxes`` port, with a recording host double.

No Docker or OpenShell: these pin what trusted code asks of any backend (order, network, sealing, ownership of
cleanup), which is what makes the backends interchangeable. Each backend's own behaviour is in its own suite."""
from pathlib import Path

import pytest

from corsair import execute, reconcile
from corsair.build import replay
from corsair.contracts import Environment, Outcome, Recipe
from corsair.workspace import sandboxes
from corsair.workspace.port import Exec, SandboxExists, Sandboxes, sandbox_name
from tests.v2.test_build_replay import BASELINE, RUNTIME, make_case
from tests.v2.test_execute import draft, frozen


class Recording:
    """A host double: records every call, answers from ``exits`` (argv[0] -> exit code) and fixed marker output."""

    provider = "recording"
    workdir = "/work"

    def __init__(self, *, exits=None, exists=False, sealed=None, markers=b"start\nend\n---\nholds"):
        self.calls: list[tuple] = []
        self.exits, self.exists, self.sealed, self.markers = exits or {}, exists, sealed, markers

    def _note(self, *call):
        self.calls.append(call)

    def create(self, spec):
        self._note("create", spec.image, spec.network, spec.workdir)
        if self.exists:
            raise SandboxExists(spec.name)
        return spec.name

    def copy_tree_in(self, name, source, destination):
        self._note("copy_tree_in", destination)

    def write_file(self, name, path, data):
        self._note("write_file", path)

    def copy_out(self, name, paths):
        return {path: None for path in paths}

    def exec_once(self, name, argv, *, workdir, env=None, timeout=None):
        self._note("exec", tuple(argv), workdir, tuple(sorted(env or {})))
        if argv[:2] == ["sh", "-c"] and "head -c" in argv[2]:
            return Exec(0, self.markers, b"")
        return Exec(self.exits.get(argv[0], 0), b"", b"")

    def drop_network(self, name):
        self._note("drop_network")

    def image_id(self, name):
        return "sha256:" + "1" * 64

    def resolve_image(self, reference):
        return None

    def remove(self, name):
        self._note("remove", name)
        return True

    def labelled(self, run_id=None):
        return ["a", "b"]

    def find_environment(self, tag, key):
        return self.sealed

    def seal_environment(self, name, tag, key, log_sha256, *, recipe, tree_source, base_image, setup_timeout=None,
                         baseline_timeout=None):
        self._note("seal", tag, base_image)
        self.sealed_timeouts = (setup_timeout, baseline_timeout)

    def open_environment(self, environment, sandbox_labels):
        self._note("open_environment", environment.image)
        if self.exists:
            raise SandboxExists("held")
        return sandbox_name(sandbox_labels)

    def agent_workspace(self, image, sandbox_labels):
        raise NotImplementedError


def kinds(fake):
    return [call[0] for call in fake.calls]


def test_the_double_and_both_real_backends_satisfy_the_port():
    assert isinstance(Recording(), Sandboxes) and isinstance(sandboxes("docker"), Sandboxes)


def test_backend_selection_is_explicit(monkeypatch):
    monkeypatch.delenv("CORSAIR_WORKSPACE", raising=False)
    assert sandboxes().provider == "docker"
    monkeypatch.setenv("CORSAIR_WORKSPACE", "podman")
    with pytest.raises(ValueError, match="unknown CORSAIR_WORKSPACE"):
        sandboxes()
    monkeypatch.setenv("CORSAIR_WORKSPACE", "openshell")
    monkeypatch.delenv("CORSAIR_OPENSHELL_CONFIG", raising=False)
    with pytest.raises(ValueError, match="CORSAIR_OPENSHELL_CONFIG"):
        sandboxes()


def test_replay_drops_network_before_the_baseline_then_seals_and_removes(tmp_path):
    fake = Recording()
    recipe = Recipe(setup=(("pip", "install", "-e", "."),), network_during_setup=True, baseline_test=BASELINE)
    built, environment = replay(make_case(tmp_path / "tree"), RUNTIME, recipe, artifacts=tmp_path / "a",
                                backend=fake)
    assert built.replayed and built.cleanup_confirmed and environment is not None
    assert kinds(fake) == ["create", "copy_tree_in", "exec", "drop_network", "exec", "seal", "remove"]
    assert fake.calls[0][2] == "build" and fake.calls[5] == ("seal", environment.image, RUNTIME.image)


def test_replay_works_in_the_backends_workdir_and_seals_its_timeouts(tmp_path):
    fake = Recording()
    fake.workdir = "/sandbox"
    recipe = Recipe(setup=(("pip", "install", "-e", "."),), baseline_test=BASELINE)
    built, environment = replay(make_case(tmp_path / "tree"), RUNTIME, recipe, artifacts=tmp_path / "a",
                                backend=fake, setup_timeout=12, baseline_timeout=34)
    assert built.replayed and environment is not None and environment.workdir == "/sandbox"
    assert fake.calls[0][3] == "/sandbox" and fake.calls[1] == ("copy_tree_in", "/sandbox")
    assert all(call[2] == "/sandbox" for call in fake.calls if call[0] == "exec")
    assert fake.sealed_timeouts == (12, 34)
    _, named = replay(make_case(tmp_path / "tree2"), RUNTIME, recipe, artifacts=tmp_path / "a", backend=Recording(),
                      workdir="/elsewhere")
    assert named is not None and named.workdir == "/elsewhere"


def test_a_failed_baseline_is_never_sealed(tmp_path):
    fake = Recording(exits={"python": 1})
    built, environment = replay(make_case(tmp_path / "tree"), RUNTIME, Recipe(baseline_test=BASELINE),
                                artifacts=tmp_path / "a", backend=fake)
    assert environment is None and built.reason == "baseline test exited 1" and "seal" not in kinds(fake)
    assert fake.calls[0][2] == "none" and "drop_network" not in kinds(fake) and kinds(fake)[-1] == "remove"


def test_a_sealed_environment_is_reused_without_a_sandbox(tmp_path):
    fake = Recording(sealed="")
    built, environment = replay(make_case(tmp_path / "tree"), RUNTIME, Recipe(baseline_test=BASELINE),
                                artifacts=tmp_path / "a", backend=fake)
    assert built.replayed and built.reason.startswith("exact-environment cache hit") and fake.calls == []


def test_a_held_identity_is_neither_reused_nor_removed(tmp_path):
    fake = Recording(exists=True)
    built, _ = replay(make_case(tmp_path / "tree"), RUNTIME, Recipe(baseline_test=BASELINE),
                      artifacts=tmp_path / "a", backend=fake)
    assert built.reason.startswith("infra: SandboxExists") and built.cleanup_confirmed is None
    assert "remove" not in kinds(fake)
    environment = Environment(image="env:1", runtime_row=RUNTIME.row_id, recipe_sha256="a" * 64,
                              tree_sha256="b" * 64)
    seen = execute.observe(environment, RUNTIME, draft("control", "True"), revision="vulnerable", run_id="r",
                           timeout=5, backend=fake)
    assert seen.cleanup_confirmed is None and b"infra: SandboxExists" in seen.output


def test_a_probe_runs_once_in_an_opened_environment_with_marker_dir_and_token(tmp_path):
    fake = Recording()
    environment = Environment(image="env:1", runtime_row=RUNTIME.row_id, recipe_sha256="a" * 64,
                              tree_sha256="b" * 64)
    seen = execute.observe(environment, RUNTIME, draft("exploit", "True"), revision="vulnerable", run_id="r",
                           timeout=5, backend=fake)
    assert kinds(fake) == ["open_environment", "write_file", "exec", "exec", "exec", "remove"]
    run = fake.calls[3]
    assert run[1][0] == "python" and run[3] == (execute.MARKER_ENV, execute.TOKEN_ENV)
    assert seen.facts.start_marker and seen.facts.end_marker and seen.facts.check_marker == "holds"
    assert seen.image_id == "sha256:" + "1" * 64 and seen.cleanup_confirmed
    patch = frozen(draft("control", "True", test_file="tests/corsair/test_control.py"), draft("exploit", "True"))
    assert execute.classify(seen.facts) is Outcome.PASSED and patch.sha256


def test_the_reconciler_sweeps_the_given_backend():
    fake = Recording()
    assert reconcile.sweep("r", backend=fake) == reconcile.Sweep(("a", "b"), ())


def test_replay_uses_the_configured_backend_when_none_is_passed(tmp_path, monkeypatch):
    fake = Recording(sealed="")
    monkeypatch.setattr("corsair.build.configured", lambda: fake)
    built, _ = replay(make_case(Path(tmp_path) / "tree"), RUNTIME, Recipe(baseline_test=BASELINE),
                      artifacts=tmp_path / "a")
    assert built.replayed
