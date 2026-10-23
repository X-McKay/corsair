from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import grpc
import pytest
import yaml

from corsair.adapters.sandbox import docker as native
from corsair.adapters.sandbox.openshell import (
    _WORKLOAD_ID_LABEL,
    _WORKLOAD_ROLE_LABEL,
    BUILD_UID,
    BUILD_USER,
    PROBE_UID,
    PROBE_USER,
    OpenShellSandboxes,
)
from corsair.ports.sandbox import LABEL, Exec, SandboxExists, SandboxSpec, labels


class RpcFailure(Exception):
    def __init__(self, status: grpc.StatusCode):
        self._status = status

    def code(self):
        return self._status


class Client:
    def __init__(self, *, create_error: Exception | None = None):
        self.create_error = create_error
        self.calls: list[tuple[str, object]] = []
        self.closed = 0
        self.current = None
        self.replacement = None

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        if self.create_error:
            raise self.create_error
        self.current = ref(kwargs["name"], kwargs["labels"], "created", version=1)
        return self.current

    def wait_ready(self, name, **kwargs):
        self.calls.append(("wait_ready", (name, kwargs)))
        return self.current

    def exec(self, *args, **kwargs):
        self.calls.append(("exec", (args, kwargs)))
        return SimpleNamespace(exit_code=0, stdout="out", stderr="err")

    def get(self, name, **kwargs):
        self.calls.append(("get", (name, kwargs)))
        if self.replacement is not None and len([call for call in self.calls if call[0] == "get"]) > 1:
            return self.replacement
        if self.current is None:
            raise RpcFailure(grpc.StatusCode.NOT_FOUND)
        return self.current

    def list_all(self, **kwargs):
        self.calls.append(("list_all", kwargs))
        return [self.current] if self.current else []

    def delete(self, name, **kwargs):
        self.calls.append(("delete", (name, kwargs)))
        return SimpleNamespace(sandbox_id=self.current.id if self.current else None)

    def wait_deleted(self, name, **kwargs):
        self.calls.append(("wait_deleted", (name, kwargs)))

    def close(self):
        self.closed += 1


def ref(name: str, resource_labels: dict[str, str], identity: str, version: int = 1):
    return SimpleNamespace(
        name=name,
        id=identity,
        labels=dict(resource_labels),
        current_policy_version=version,
    )


def reviewed_policy() -> dict[str, object]:
    return {
        "network_policies": {
            "packages": {
                "name": "packages",
                "endpoints": [{"host": "registry.example", "port": 443}],
                "binaries": [{"path": "/usr/bin/pip"}],
            }
        }
    }


def runner(calls: list[list[str]], *, policy: list[dict[str, object]] | None = None):
    def run(args, **kwargs):
        calls.append(list(args))
        if args[-3:] == ["info", "-o", "json"]:
            return subprocess.CompletedProcess(args, 0, '{"compute_drivers":[{"name":"docker"}]}', "")
        if "policy" in args:
            policy_file = Path(args[args.index("--policy") + 1])
            if policy is not None:
                policy.append(yaml.safe_load(policy_file.read_text()))
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    return run


def adapter(client: Client, calls: list[list[str]], **kwargs) -> OpenShellSandboxes:
    return OpenShellSandboxes(
        client=client, command_runner=runner(calls), build_policy=reviewed_policy(), **kwargs
    )


def test_sdk_create_request_is_explicit_and_policy_binds_nonroot_build_identity(monkeypatch):
    client, calls = Client(), []
    backend = adapter(client, calls)
    spec = SandboxSpec("example@sha256:abc", labels=labels("run", "build"), network="build")
    monkeypatch.setattr(backend, "_workload", lambda name, **kwargs: "native-workload")
    prepared: list[str] = []
    monkeypatch.setattr(backend, "_prepare_builder_paths", lambda name: prepared.append(name))

    assert backend.create(spec) == spec.name
    request = next(value for kind, value in client.calls if kind == "create")
    assert request["workspace"] == "default"
    assert request["name"] == backend._gateway_name(spec.name)
    assert len(request["name"]) <= 19
    sdk_spec = request["spec"]
    assert sdk_spec.template.image == spec.image
    assert sdk_spec.template.labels[LABEL] == "1"
    assert sdk_spec.template.labels["corsair.lite.run"] == "run"
    assert sdk_spec.template.resources.fields["limits"].struct_value.fields["cpu"].string_value == "2"
    assert sdk_spec.template.resources.fields["limits"].struct_value.fields["memory"].string_value == "4Gi"
    assert sdk_spec.policy.filesystem.include_workdir
    assert set(sdk_spec.policy.filesystem.read_only) >= {"/usr", "/bin", "/lib", "/etc", "/opt"}
    assert set(sdk_spec.policy.filesystem.read_write) >= {"/work", "/tmp"}
    assert sdk_spec.policy.landlock.compatibility == "hard_requirement"
    assert sdk_spec.policy.process.run_as_user == str(BUILD_UID)
    assert sdk_spec.policy.process.run_as_group == str(BUILD_UID)
    assert sdk_spec.policy.network_policies["packages"].binaries[0].path == "/usr/bin/pip"
    assert list(sdk_spec.command) == ["sleep", "infinity"]
    assert [kind for kind, _ in client.calls].count("create") == 1
    assert [kind for kind, _ in client.calls].count("wait_ready") == 1
    assert prepared == [spec.name]
    assert client.closed == 0  # an injected SDK client remains caller-owned


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://user:secret@127.0.0.1:18084",
        "http://127.0.0.1:18084/?token=secret",
        "http://127.0.0.1:18084/#secret",
    ),
)
def test_direct_endpoint_rejects_userinfo_query_and_fragment(endpoint):
    with pytest.raises(ValueError, match="userinfo"):
        OpenShellSandboxes(endpoint=endpoint)


def test_existing_and_uncertain_create_are_held_not_adopted_or_retried(monkeypatch):
    spec = SandboxSpec("image", labels=labels("run", "build"), network="build")
    calls: list[list[str]] = []
    held = Client(create_error=RpcFailure(grpc.StatusCode.ALREADY_EXISTS))
    with pytest.raises(SandboxExists):
        adapter(held, calls).create(spec)
    assert [kind for kind, _ in held.calls] == ["create"]

    uncertain = Client(create_error=RpcFailure(grpc.StatusCode.DEADLINE_EXCEEDED))
    uncertain.current = ref(spec.name, {LABEL: "1", **spec.labels}, "possibly-created")
    backend = adapter(uncertain, calls)
    with pytest.raises(SandboxExists):
        backend.create(spec)
    assert [kind for kind, _ in uncertain.calls] == ["create", "get"]
    assert backend.remove(spec.name) is False


def test_long_logical_name_maps_to_stable_gateway_name_and_held_collision_is_not_adopted(monkeypatch):
    client, calls = Client(), []
    backend = adapter(client, calls)
    spec = SandboxSpec("image", labels=labels("r" * 48, "build", "producer"), network="build")
    assert len(spec.name) > 19
    monkeypatch.setattr(backend, "_workload", lambda *_args, **_kwargs: "workload")
    monkeypatch.setattr(backend, "_prepare_builder_paths", lambda _name: None)

    assert backend.create(spec) == spec.name
    native_name = backend._gateway_name(spec.name)
    assert client.current.name == native_name
    assert backend._refs[spec.name].name == native_name
    assert len(native_name) == 19 and native_name == backend._gateway_name(spec.name)

    collision = adapter(Client(), [])
    collision._refs["different-logical-name"] = ref(native_name, {LABEL: "1"}, "held")
    monkeypatch.setattr(collision, "_gateway_name", lambda _logical: native_name)
    with pytest.raises(SandboxExists, match="collides"):
        collision.create(SandboxSpec("image", labels=labels("different", "build"), network="build"))


def test_sdk_exec_timeout_is_an_observation_and_is_never_retried():
    client, calls = Client(), []
    backend = adapter(client, calls)
    client.current = ref("native-known", {LABEL: "1"}, "id")
    backend._refs["known"] = client.current
    backend._labels["known"] = {LABEL: "1"}
    backend._users["known"] = PROBE_USER
    client.exec = lambda *args, **kwargs: (_ for _ in ()).throw(RpcFailure(grpc.StatusCode.DEADLINE_EXCEEDED))

    result = backend.exec_once("known", ["false"], workdir="/work", timeout=0.1)
    assert result == Exec(None, b"", b"", timed_out=True)
    assert [kind for kind, _ in client.calls].count(
        "exec"
    ) == 0  # replacement lambda is deliberately not a mock call


def test_builder_exec_uses_sdk_with_standard_nonroot_toolchain_environment(monkeypatch):
    client, calls = Client(), []
    backend = adapter(client, calls)
    backend._refs["build"] = client.current = ref("c-native-build", {LABEL: "1"}, "id")
    backend._labels["build"] = {LABEL: "1"}
    backend._users["build"] = BUILD_USER
    prepared: list[str] = []
    monkeypatch.setattr(backend, "_prepare_builder_paths", lambda name: prepared.append(name))

    result = backend.exec_once(
        "build", ["bash", "script.sh"], workdir="/work", env={"EXTRA": "1", "PYTHONPATH": "/caller/path"}
    )

    assert result == Exec(0, b"out", b"err")
    assert prepared == []  # creation, not a model command, prepares the privileged cache boundary
    _kind, (argv, kwargs) = next(call for call in client.calls if call[0] == "exec")
    assert argv[0] == "c-native-build"
    assert kwargs["env"] == {
        "HOME": "/tmp/corsair-build/home",
        "PIP_TARGET": "/tmp/corsair-build/python",
        "PYTHONPATH": "/tmp/corsair-build/python:/caller/path",
        "npm_config_cache": "/tmp/corsair-build/npm",
        "npm_config_prefix": "/tmp/corsair-build/npm",
        "GRADLE_USER_HOME": "/tmp/corsair-build/gradle",
        "MAVEN_USER_HOME": "/tmp/corsair-build/maven",
        "MAVEN_OPTS": "-Dmaven.repo.local=/tmp/corsair-build/m2",
        "GEM_HOME": "/tmp/corsair-build/gems",
        "GEM_PATH": "/tmp/corsair-build/gems:/usr/local/bundle",
        "BUNDLE_APP_CONFIG": "/tmp/corsair-build/bundle/config",
        "BUNDLE_USER_CACHE": "/tmp/corsair-build/bundle",
        "PERL_LOCAL_LIB_ROOT": "/tmp/corsair-build/perl5",
        "PERL_MB_OPT": "--install_base /tmp/corsair-build/perl5",
        "PERL_MM_OPT": "INSTALL_BASE=/tmp/corsair-build/perl5",
        "PERL5LIB": "/tmp/corsair-build/perl5/lib/perl5",
        "EXTRA": "1",
    }


def test_probe_pythonpath_includes_builder_target_without_replacing_framework_path():
    backend = adapter(Client(), [])
    backend._users["probe"] = PROBE_USER

    assert backend._command_environment("probe", {"PYTHONPATH": "/work:/work/.corsair", "EXTRA": "1"}) == {
        "PYTHONPATH": "/tmp/corsair-build/python:/work:/work/.corsair",
        "EXTRA": "1",
    }


def test_builder_cache_is_prepared_once_in_tmp_before_any_model_command(monkeypatch):
    backend = adapter(Client(), [])
    copied: list[tuple[str, Path, str]] = []
    monkeypatch.setattr(backend, "_workload", lambda *_args, **_kwargs: "workload")

    def copy_tree_in(workload: str, source: Path, destination: str) -> None:
        copied.append((workload, source, destination))
        directories = [path for path in source.rglob("*") if path.is_dir()]
        assert {path.relative_to(source).as_posix() for path in directories} >= {
            "corsair-build",
            "corsair-build/python",
            "corsair-build/npm",
            "corsair-build/perl5/lib/perl5",
        }
        assert all(path.stat().st_mode & 0o777 == 0o755 for path in directories)

    monkeypatch.setattr(backend._native, "copy_tree_in", copy_tree_in)
    backend._prepare_builder_paths("build")
    # A build can subsequently replace /tmp/corsair-build with a symlink, so a second
    # preparation must not archive-copy privileged host files through that destination.
    backend._prepare_builder_paths("build")

    assert [(workload, destination) for workload, _source, destination in copied] == [("workload", "/tmp")]


def test_write_file_requires_a_canonical_support_descendant(monkeypatch):
    backend = adapter(Client(), [])
    copied: list[tuple[str, Path, str]] = []
    monkeypatch.setattr(backend, "_workload", lambda *_args, **_kwargs: "workload")
    monkeypatch.setattr(backend._native, "copy_tree_in", lambda *args: copied.append(args))

    for path in ("/work/.corsair", "/work/.corsair/./build.sh", "/work/.corsair/../outside"):
        with pytest.raises(Exception, match="support"):
            backend.write_file("build", path, b"x")

    backend.write_file("build", "/work/.corsair/build.sh", b"trusted")
    assert copied[0][0] == "workload" and copied[0][2] == "/work"
    assert backend._trusted_support["build"] == {"build.sh"}


def test_source_unchanged_rejects_foreign_support_before_manifest_injection(monkeypatch, tmp_path):
    backend = adapter(Client(), [])
    backend._users["build"] = BUILD_USER
    backend._trusted_support["build"] = {"build.sh"}
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(backend, "_workload", lambda *_args, **_kwargs: "workload")

    def trusted_exec(*args, **kwargs):
        calls.append(args)
        assert kwargs["trusted"] is True
        return Exec(1, b"", b"foreign pathlib.py")

    monkeypatch.setattr(backend._native, "exec_once", trusted_exec)
    monkeypatch.setattr(
        backend._native,
        "copy_tree_in",
        lambda *_args: pytest.fail("foreign support must be rejected before manifest injection"),
    )

    assert backend.source_unchanged("build", tmp_path) is False
    assert calls[0][1][:3] == ["python", "-I", "-c"]
    assert calls[0][1][4] == '["build.sh"]'
    assert "actual != expected" in calls[0][1][3]
    assert "S_ISREG" in calls[0][1][3]


def test_native_mapping_uses_only_verified_workload_and_enforces_outer_fence(monkeypatch, tmp_path):
    client, calls = Client(), []
    backend = adapter(client, calls)
    name = "gateway-name"
    backend._refs[name] = ref(name, {LABEL: "1", "x": "y"}, "sdk-id")
    backend._labels[name] = {LABEL: "1", "x": "y"}
    backend._users[name] = BUILD_USER
    client.current = backend._refs[name]
    inspect = {
        "Id": "immutable-workload-id",
        "Config": {
            "User": BUILD_USER,
            "Labels": {LABEL: "1", "x": "y", _WORKLOAD_ID_LABEL: "sdk-id", _WORKLOAD_ROLE_LABEL: "sandbox"},
        },
        "HostConfig": {
            "NetworkMode": "none",
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": 256,
            "Memory": 4 * 1024**3,
            "NanoCpus": 2_000_000_000,
        },
    }

    def docker(*args, **kwargs):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, b"native-workload\n", b"")
        assert args[:2] == ("inspect", "--format")
        return subprocess.CompletedProcess(args, 0, json.dumps(inspect).encode(), b"")

    copied = []
    monkeypatch.setattr(native, "docker", docker)
    monkeypatch.setattr(backend._native, "copy_tree_in", lambda *args: copied.append(args))
    backend.copy_tree_in(name, tmp_path, "/work")
    assert copied[0][0] == "immutable-workload-id"
    assert backend._native._owners["immutable-workload-id"] == (BUILD_UID, BUILD_UID)

    backend._workloads.clear()
    inspect["HostConfig"]["NetworkMode"] = "bridge"
    with pytest.raises(Exception, match="isolation"):
        backend.copy_tree_in(name, tmp_path, "/work")

    inspect["HostConfig"]["NetworkMode"] = "none"
    backend._workloads[name] = "immutable-workload-id"
    inspect["Id"] = "attacker-replacement-id"
    with pytest.raises(Exception, match="container identity changed"):
        backend.copy_tree_in(name, tmp_path, "/work")


def test_open_environment_uses_sdk_probe_policy_not_docker_create(monkeypatch):
    client, calls = Client(), []
    backend = adapter(client, calls)
    labels_ = labels("run", "probe", "control")
    monkeypatch.setattr(backend, "_workload", lambda name, **kwargs: "native-probe")

    name = backend.open_environment("cached:image", "/work", labels_)
    request = next(value for kind, value in client.calls if kind == "create")
    assert name == SandboxSpec("cached:image", labels=labels_).name
    assert request["name"] == backend._gateway_name(name)
    assert request["spec"].policy.process.run_as_user == str(PROBE_UID)
    assert request["spec"].policy.process.run_as_group == str(PROBE_UID)
    assert not request["spec"].policy.network_policies
    assert request["spec"].policy.filesystem.include_workdir


def test_policy_set_removes_egress_and_confirms_new_active_version():
    client, calls = Client(), []
    policies: list[dict[str, object]] = []
    backend = OpenShellSandboxes(
        client=client, command_runner=runner(calls, policy=policies), build_policy=reviewed_policy()
    )
    name = "build"
    client.current = ref(name, {LABEL: "1"}, "id", version=4)
    backend._refs[name] = client.current
    backend._labels[name] = {LABEL: "1"}
    observed = 0

    def policy_get(*_args, **_kwargs):
        nonlocal observed
        observed += 1
        return ref(name, {LABEL: "1"}, "id", version=4 if observed == 1 else 5)

    client.get = policy_get

    backend.drop_network(name)
    assert policies == [
        {
            "version": 1,
            "filesystem_policy": {
                "include_workdir": True,
                "read_only": [
                    "/usr",
                    "/bin",
                    "/lib",
                    "/lib64",
                    "/proc",
                    "/dev/urandom",
                    "/app",
                    "/etc",
                    "/opt",
                    "/var/log",
                ],
                "read_write": ["/work", "/tmp", "/dev/null"],
            },
            "landlock": {"compatibility": "hard_requirement"},
            "process": {"run_as_user": str(BUILD_UID), "run_as_group": str(BUILD_UID)},
        }
    ]
    command = next(command for command in calls if "policy" in command)
    assert "--wait" in command and command[command.index("--timeout") + 1] == "60"


def test_cleanup_refuses_same_name_replacement_and_reconciler_marks_exact_ref():
    client, calls = Client(), []
    backend = adapter(client, calls)
    name = "held"
    original = ref(name, {LABEL: "1"}, "original")
    client.current, client.replacement = original, ref(name, {LABEL: "1"}, "replacement")
    backend._refs[name] = original
    backend._labels[name] = {LABEL: "1"}

    assert backend.remove(name) is False
    assert backend._refs[name].id == "original"

    client.replacement = None
    client.current = ref("other", {LABEL: "1", "corsair.lite.run": "r"}, "listed")
    assert backend.labelled("r") == ["other"]
    assert backend._refs["other"].id == "listed"


def test_default_client_is_lazy_and_closed_per_operation(monkeypatch):
    made: list[Client] = []
    calls: list[list[str]] = []

    def factory():
        client = Client()
        client.current = ref("listed", {LABEL: "1"}, "id")
        made.append(client)
        return client

    backend = OpenShellSandboxes(
        client_factory=factory, command_runner=runner(calls), build_policy=reviewed_policy()
    )
    assert not made
    assert backend.labelled() == ["listed"]
    assert len(made) == 1 and made[0].closed == 1


def test_cache_identity_reads_reviewed_policy_only_when_requested(tmp_path):
    missing = tmp_path / "reviewed-policy.yaml"
    backend = OpenShellSandboxes(build_policy_path=missing)
    assert backend._policy_hash is None
    with pytest.raises(Exception, match="cannot read reviewed"):
        _ = backend.cache_identity
