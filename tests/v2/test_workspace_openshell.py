"""The OpenShell backend: offline adapter-logic tests on the host double (``openshell_fake``), and live tests that
run only with ``CORSAIR_OPENSHELL_CONFIG`` (PydanticAI's own workspace conformance suite against a real gateway)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import uuid
from pathlib import Path

import grpc
import pytest
import yaml
from openshell import DeletionOutcome
from openshell._proto import openshell_pb2
from pydantic_ai.workspaces import (
    WorkspaceError,
    WorkspaceOutputLimitError,
    WorkspaceRef,
    WorkspaceTimeoutError,
    WorkspaceUnavailableError,
)
from pydantic_ai.workspaces.conformance import WorkspaceBackendSuite

from corsair.v2.contracts import Environment, Recipe, RecipeFile
from corsair.v2.intake import tree_sha256
from corsair.v2.workspace import SandboxExists, SandboxSpec, labels
from corsair.v2.workspace import openshell as backend
from corsair.v2.workspace.openshell import WORKDIR
from corsair.v2.workspace.openshell import (
    OpenShellConfig,
    OpenShellSandboxes,
    OpenShellWorkspace,
    label_value,
    native_labels,
    native_name,
)
from tests.v2.live_cleanup import record_cleanup, remove_confirmed
from tests.v2.openshell_fake import ERROR, FakeGateway, FakeRpcError, Outcome

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ROOT / "policies/openshell/v2"
IMAGE = "corsair-python:61a3e8db1afb1726"
DIGEST_REF = "docker.io/library/corsair-python@sha256:" + "a" * 64
LIVE_CONFIG = os.environ.get("CORSAIR_OPENSHELL_CONFIG")
PROVIDER_NAME = "openshell"


def write_config(tmp_path: Path, **changes) -> Path:
    cli = tmp_path / "openshell"
    cli.write_bytes(b"pinned cli bytes")
    images = tmp_path / "images.json"
    images.write_text(json.dumps({IMAGE: DIGEST_REF}))
    for name in ("ca.pem", "cert.pem", "key.pem"):
        (tmp_path / name).write_text("not used offline")
    config = {"endpoint": "gateway.test:8443", "ca": str(tmp_path / "ca.pem"), "cert": str(tmp_path / "cert.pem"),
              "key": str(tmp_path / "key.pem"), "workspace": "corsair-test", "gateway": "corsair",
              "cli": {"path": str(cli), "sha256": hashlib.sha256(cli.read_bytes()).hexdigest()},
              "cli_env": {"HOME": str(tmp_path)}, "images": str(images),
              "policies": {"none": str(POLICIES / "none.yaml"), "build": str(POLICIES / "build.yaml")},
              "state_dir": str(tmp_path / "state"), "limits": {"ready_seconds": 180, "delete_seconds": 60}}
    config.update(changes)
    path = tmp_path / "openshell.json"
    path.write_text(json.dumps(config))
    return path


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def sandboxes(tmp_path, gateway) -> OpenShellSandboxes:
    return OpenShellSandboxes(OpenShellConfig.from_json(write_config(tmp_path)), gateway, cli=gateway.cli,
                              clock=gateway.clock)


def spec(network="none", **extra) -> SandboxSpec:
    return SandboxSpec(image=IMAGE, labels=labels("run-1", "execute", "control", case="org/repo:CVE#1", **extra), workdir=WORKDIR,
                       network=network)


def documents() -> dict[str, dict]:
    return {kind: yaml.safe_load((POLICIES / f"{kind}.yaml").read_text()) for kind in ("none", "build")}


# --- configuration and policy documents ----------------------------------------------------------------------------


def test_config_loads_the_operator_schema(tmp_path):
    config = OpenShellConfig.from_json(write_config(tmp_path))
    assert config.images == {IMAGE: DIGEST_REF} and config.ready_seconds == 180 and config.gateway == "corsair"
    assert config.policies["none"]["network_policies"] == {}


@pytest.mark.parametrize("change", [
    {"extra": 1}, {"endpoint": "no-port"}, {"ca": "relative/ca.pem"}, {"state_dir": "/a/../b"},
    {"cli": {"path": "/x"}}, {"cli": {"path": "/x", "sha256": "short"}}, {"cli_env": {"A": 1}},
    {"limits": {"ready_seconds": 0, "delete_seconds": 60}}, {"limits": {"ready_seconds": 1.5, "delete_seconds": 60}},
    {"policies": {"none": str(POLICIES / "build.yaml"), "build": str(POLICIES / "build.yaml")}},
    {"policies": {"none": str(POLICIES / "none.yaml")}},
])
def test_config_is_validated_strictly(tmp_path, change):
    with pytest.raises((ValueError, KeyError)):
        OpenShellConfig.from_json(write_config(tmp_path, **change))


@pytest.mark.parametrize("ref", ["corsair-python:61a3", "docker.io/library/x@sha256:abc",
                                 "ghcr.io/x/y@sha256:" + "a" * 64])
def test_an_image_must_map_to_a_digest_pinned_ref(tmp_path, ref):
    path = write_config(tmp_path)
    (tmp_path / "images.json").write_text(json.dumps({IMAGE: ref}))
    with pytest.raises(ValueError):
        OpenShellConfig.from_json(path)


@pytest.mark.parametrize("weaken", ["audit", "wildcard", "port", "landlock", "field", "fs", "post", "protocol",
                                    "rule", "endpoint", "no_rules", "workdir"])
def test_weakened_policies_are_refused(tmp_path, weaken):
    document = documents()["build"]
    endpoint = document["network_policies"]["corsair-build-python"]["endpoints"][0]
    if weaken == "audit":
        endpoint["enforcement"] = "audit"
    elif weaken == "wildcard":
        endpoint["host"] = "*.pythonhosted.org"
    elif weaken == "port":
        endpoint["port"] = 80
    elif weaken == "landlock":
        document["landlock"]["compatibility"] = "best_effort"
    elif weaken == "field":
        document["providers"] = ["github"]
    elif weaken == "post":
        endpoint["rules"].append({"allow": {"method": "POST", "path": "/**"}})
    elif weaken == "protocol":
        endpoint["protocol"] = "tcp"
    elif weaken == "rule":
        document["network_policies"]["corsair-build-python"] = ["not", "a", "mapping"]
    elif weaken == "endpoint":
        document["network_policies"]["corsair-build-python"]["endpoints"].append("pypi.org")
    elif weaken == "no_rules":
        endpoint["rules"] = []
    elif weaken == "workdir":
        document["filesystem_policy"]["include_workdir"] = False
    else:
        document["filesystem_policy"]["read_write"].append("/etc")
    (tmp_path / "build.yaml").write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError):
        OpenShellConfig.from_json(write_config(tmp_path, policies={"none": str(POLICIES / "none.yaml"),
                                                                   "build": str(tmp_path / "build.yaml")}))


def test_loaded_readback_ignores_empty_fields_but_not_unrequested_authority():
    none = documents()["none"]
    assert backend.loads_requested(none | {"network_middlewares": {}, "process": {"run_as_user": "sandbox"}}, none)
    assert backend.loads_requested({k: v for k, v in none.items() if k != "network_policies"}, none)
    assert not backend.loads_requested(none | {"network_middlewares": {"m": {"name": "m"}}}, none)
    assert not backend.loads_requested(none | {"something_new": ["x"]}, none)
    assert not backend.loads_requested(none | {"network_policies": {"x": {}}}, none)


def test_policy_documents_match_the_runtime_matrix():
    matrix = yaml.safe_load((ROOT / "deploy/v2/runtime-matrix.yaml").read_text())
    wanted = {host for row in matrix["rows"] for host in row.get("build_network_hosts", ())}
    none, build = documents().values()
    granted = {endpoint["host"] for rule in build["network_policies"].values() for endpoint in rule["endpoints"]}
    assert granted == wanted
    assert all(rule["allow"]["method"] == "GET" for policy in build["network_policies"].values()
               for endpoint in policy["endpoints"] for rule in endpoint["rules"])
    assert none["network_policies"] == {} and {key: value for key, value in build.items()
                                               if key != "network_policies"} == {
        key: value for key, value in none.items() if key != "network_policies"}
    assert none["filesystem_policy"]["include_workdir"] is True and "/tmp" in none["filesystem_policy"]["read_write"]
    assert "/work" not in none["filesystem_policy"]["read_write"]


# --- names and labels ------------------------------------------------------------------------------------------------


def test_names_and_labels_are_valid_deterministic_and_distinct():
    port_name = spec().name
    name = native_name(port_name)
    assert name == native_name(port_name) == native_name(name) and len(name) <= 19
    assert name.replace("-", "").isalnum() and name[0].isalpha() and name.islower()
    for long_name in (port_name, "corsair-v2-" + "x" * 80, "Upper_and.dots", "a" * 20, "9starts-with-a-digit"):
        short = native_name(long_name)
        assert len(short) <= backend.NAME_LIMIT == 19 and native_name(short) == short and short.startswith("cv2-")
    assert native_name("cv2-0123456789abc") == "cv2-0123456789abc" and native_name("short") == "short"
    assert native_name(SandboxSpec(image=IMAGE, labels=labels("run-2", "execute", "control")).name) != name
    for raw in ("org/repo:CVE-1#2", "x" * 100, "-leading", "::"):
        value = label_value(raw)
        assert len(value) <= 63 and value == label_value(raw) and value[0].isalnum() and value[-1].isalnum()
    assert label_value("a:b") != label_value("a/b") and label_value("run-1") == "run-1"
    with pytest.raises(ValueError):
        native_labels({"bad key!": "x"})


# --- create -----------------------------------------------------------------------------------------------------------


def test_create_pins_the_image_labels_policy_and_workdir(sandboxes, gateway):
    wanted = spec()
    assert sandboxes.create(wanted) == wanted.name
    box = gateway.sandboxes[native_name(wanted.name)]
    assert box.spec.template.image == DIGEST_REF
    assert box.spec.restart_policy == openshell_pb2.SANDBOX_RESTART_POLICY_NEVER
    assert list(box.spec.policy.filesystem.read_write) == documents()["none"]["filesystem_policy"]["read_write"]
    assert box.spec.policy.landlock.compatibility == "hard_requirement" and not box.spec.policy.network_policies
    assert not box.spec.providers and not box.spec.environment
    assert box.labels == native_labels(wanted.labels, wanted.name) and box.labels["corsair.v2"] == "1"
    assert box.labels[backend.NAME_LABEL] == label_value(wanted.name) and len(box.name) <= 19
    assert box.labels["corsair.v2.case"] == label_value("org/repo:CVE#1")
    assert box.revisions == [documents()["none"]]
    order = [call[0] if call[0] != "cli" else call[1][:2] for call in gateway.calls]
    assert order.index("create") < order.index("wait_ready") < order.index(("policy", "set"))
    mkdir = gateway.execs[-1]
    assert mkdir.command[-1] == "/sandbox" and "mkdir -p" in mkdir.command[2] and mkdir.no_login_shell


def test_build_network_gets_the_build_policy(sandboxes, gateway):
    sandboxes.create(spec("build"))
    assert gateway.sandboxes[native_name(spec("build").name)].revisions == [documents()["build"]]


def test_an_unmapped_image_fails_before_any_create(sandboxes, gateway):
    with pytest.raises(WorkspaceError, match="no digest-pinned mapping"):
        sandboxes.create(SandboxSpec(image="corsair-unknown:1", labels=labels("r", "s"), workdir=WORKDIR))
    assert gateway.calls == []


@pytest.mark.parametrize("workdir", ["/srv", "/work"])
def test_a_workdir_outside_the_policy_is_refused(sandboxes, gateway, workdir):
    # The toolchain images run as uid 10001 with no /work; only the native workdir and /tmp are writable.
    with pytest.raises(WorkspaceError, match="not writable"):
        sandboxes.create(SandboxSpec(image=IMAGE, labels=labels("r", "s"), workdir=workdir))
    assert gateway.calls == [] and sandboxes.workdir == WORKDIR == "/sandbox"


def test_tmp_is_a_writable_workdir_too(sandboxes, gateway):
    sandboxes.create(SandboxSpec(image=IMAGE, labels=labels("r", "s"), workdir="/tmp/work"))
    assert gateway.execs[-1].command[-1] == "/tmp/work"


def test_an_existing_identity_raises_sandbox_exists_and_is_left_alone(sandboxes, gateway):
    sandboxes.create(spec())
    gateway.calls.clear()
    with pytest.raises(SandboxExists):
        sandboxes.create(spec())
    assert [call[0] for call in gateway.calls] == ["create"]


def test_an_uncertain_create_is_an_error_not_an_absence(sandboxes, gateway):
    gateway.create_error = FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    with pytest.raises(WorkspaceError, match="may exist"):
        sandboxes.create(spec())


@pytest.mark.parametrize("fault", ["status", "document", "error_phase"])
def test_a_policy_or_readiness_not_observed_fails_create(sandboxes, gateway, fault):
    if fault == "status":
        gateway.policy_status = "pending"
    elif fault == "document":
        gateway.policy_override = documents()["build"]
    else:
        gateway.ready_phase = ERROR
    with pytest.raises(WorkspaceError):
        sandboxes.create(spec())


def test_the_cli_hash_is_cached_by_path_mtime_and_size(sandboxes, gateway, tmp_path):
    cli = tmp_path / "openshell"
    sandboxes.create(spec())
    info = cli.stat()
    cli.write_bytes(b"pinned cli BYTES")  # Same size; with the old mtime the verified identity is unchanged.
    os.utime(cli, ns=(info.st_atime_ns, info.st_mtime_ns))
    sandboxes.drop_network(spec().name)
    os.utime(cli, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
    with pytest.raises(WorkspaceError, match="pinned sha256"):
        sandboxes.drop_network(spec().name)


def test_from_config_shares_one_instance_per_config_path_until_it_is_rewritten(tmp_path):
    path = write_config(tmp_path)
    made = [OpenShellSandboxes.from_config(path)]
    try:
        assert OpenShellSandboxes.from_config(tmp_path / "." / path.name) is made[0]
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        made.append(OpenShellSandboxes.from_config(path))
        assert made[1] is not made[0]
    finally:
        for key in [key for key in backend._INSTANCES if key[0] == path.resolve()]:
            backend._INSTANCES.pop(key)
        for instance in made:
            instance.client.close()


def test_the_cli_is_checked_against_its_pin_before_every_call(sandboxes, gateway, tmp_path):
    (tmp_path / "openshell").write_bytes(b"tampered")
    with pytest.raises(WorkspaceError, match="pinned sha256"):
        sandboxes.create(spec())
    assert not any(call[0] == "cli" for call in gateway.calls)


# --- exec ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def made(sandboxes, gateway) -> str:
    name = sandboxes.create(spec())
    gateway.execs.clear()
    gateway.calls.clear()
    return name


def test_exec_once_reports_the_exit_and_runs_once(sandboxes, gateway, made):
    gateway.handler = lambda call: Outcome(3, b"out", b"err")
    result = sandboxes.exec_once(made, ["false"], workdir="/sandbox", env={"A": "1"}, timeout=10)
    assert (result.exit_code, result.stdout, result.stderr, result.timed_out) == (3, b"out", b"err", False)
    assert len(gateway.execs) == 1 and gateway.execs[0].env == {"A": "1"} and gateway.execs[0].timeout_seconds == 10


def test_gateway_exit_124_is_a_timeout_only_once_the_timeout_elapsed(sandboxes, gateway, made):
    gateway.handler = lambda call: Outcome(124, b"partial", elapsed=10)
    timed = sandboxes.exec_once(made, ["sleep", "60"], workdir="/sandbox", timeout=10)
    assert timed.timed_out and timed.exit_code is None and timed.stdout == b"partial"
    gateway.handler = lambda call: Outcome(124, elapsed=0.1)
    assert sandboxes.exec_once(made, ["sh", "-c", "exit 124"], workdir="/sandbox", timeout=10).exit_code == 124


def test_exec_without_a_timeout_is_still_bounded(sandboxes, gateway, made):
    sandboxes.exec_once(made, ["true"], workdir="/sandbox")
    assert gateway.execs[0].timeout_seconds == backend.EXEC_DEFAULT_TIMEOUT_S


@pytest.mark.parametrize("fault", ["transport", "gone", "deadline"])
def test_exec_failure_after_dispatch_is_a_fact_never_a_retry(sandboxes, gateway, made, fault):
    gateway.handler = {
        "transport": lambda call: Outcome(None, b"x", error=FakeRpcError(grpc.StatusCode.UNAVAILABLE)),
        "gone": lambda call: Outcome(137, gone=True),
        "deadline": lambda call: Outcome(None, error=FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED)),
    }[fault]
    result = sandboxes.exec_once(made, ["run"], workdir="/sandbox", timeout=5)
    assert result.exit_code is None and len(gateway.execs) == 1
    assert (result.timed_out, result.container_failed) == ((True, False) if fault == "deadline" else (False, True))


@pytest.mark.parametrize("fault", ["missing", "not_ready", "replaced"])
def test_exec_refuses_before_dispatch_when_the_sandbox_is_not_ours_and_ready(sandboxes, gateway, made, fault):
    name = native_name(made)
    if fault == "missing":
        del gateway.sandboxes[name]
    elif fault == "not_ready":
        gateway.sandboxes[name].phase = ERROR
    else:
        gateway.replace(name)
    result = sandboxes.exec_once(made, ["run"], workdir="/sandbox", timeout=5)
    assert result.container_failed and gateway.execs == []


def test_exec_output_is_bounded(sandboxes, gateway, made, monkeypatch):
    monkeypatch.setattr(backend, "MAX_OUTPUT_BYTES", 10_000)
    gateway.handler = lambda call: Outcome(0, b"y" * 50_000)
    result = sandboxes.exec_once(made, ["yes"], workdir="/sandbox", timeout=5)
    assert result.exit_code == 0 and len(result.stdout) == 10_000 and b"truncated" in result.stderr


# --- files -----------------------------------------------------------------------------------------------------------


def _members(stdin_chunks: list[bytes]) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(b"".join(stdin_chunks))) as archive:
        return {member.name: member for member in archive.getmembers()}


def test_copy_tree_in_sends_symlinks_as_links_in_bounded_chunks(sandboxes, gateway, made, tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "STDIN_CHUNK_BYTES", 1024)
    tree = tmp_path / "tree"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "mod.py").write_text("VALUE = 1\n" * 300)
    secret = tmp_path / "host-secret"
    secret.write_text("host only")
    (tree / "link").symlink_to(secret)
    (tree / "linkdir").symlink_to(tmp_path)
    sandboxes.copy_tree_in(made, tree, "/sandbox")
    chunks = [call.stdin for call in gateway.execs if call.command[2] == 'cat > "$1"']
    assert len(chunks) > 1 and all(len(chunk) <= 1024 for chunk in chunks)
    members = _members(chunks)
    assert set(members) == {"pkg", "pkg/mod.py", "link", "linkdir"}
    assert members["link"].issym() and members["link"].linkname == str(secret)
    assert members["linkdir"].issym() and b"host only" not in b"".join(chunks)
    extract = gateway.execs[-1].command
    assert "tar -x" in extract[2] and "--no-same-owner" in extract[2] and extract[-1] == "/sandbox"


def test_copy_tree_in_refuses_an_oversized_tree_before_reading_it(sandboxes, made, tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "MAX_TRANSFER_BYTES", 1000)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.bin").write_bytes(b"a" * 600)
    (tree / "b.bin").write_bytes(b"b" * 600)
    opened: list[Path] = []
    real_open = Path.open
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: opened.append(self) or real_open(self, *a, **k))
    with pytest.raises(WorkspaceError, match="transfer bound"):
        sandboxes.copy_tree_in(made, tree, "/sandbox")
    assert tree / "b.bin" not in opened


def test_copy_tree_in_refuses_special_files(sandboxes, made, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    os.mkfifo(tree / "pipe")
    with pytest.raises(WorkspaceError, match="not a file"):
        sandboxes.copy_tree_in(made, tree, "/sandbox")


def test_write_file_and_copy_out(sandboxes, gateway, made):
    sandboxes.write_file(made, "/sandbox/tests/test_x.py", b"print(1)\n")
    assert gateway.execs[-1].stdin == b"print(1)\n" and gateway.execs[-1].command[-1] == "/sandbox/tests/test_x.py"
    gateway.handler = lambda call: (Outcome(0, b"data") if call.command[-1] == "/sandbox/a"
                                    else Outcome(backend.MISSING_EXIT))
    assert sandboxes.copy_out(made, ["/sandbox/a", "/sandbox/missing"]) == {"/sandbox/a": b"data", "/sandbox/missing": None}
    gateway.handler = lambda call: Outcome(None, error=FakeRpcError(grpc.StatusCode.UNAVAILABLE))
    with pytest.raises(WorkspaceError):
        sandboxes.copy_out(made, ["/sandbox/a"])


# --- network, provenance, removal and listing ------------------------------------------------------------------------


def test_drop_network_sets_none_and_observes_it_loaded(sandboxes, gateway):
    name = sandboxes.create(spec("build"))
    sandboxes.drop_network(name)
    assert gateway.sandboxes[native_name(name)].revisions == [documents()["build"], documents()["none"]]
    gateway.policy_status = "failed"
    with pytest.raises(WorkspaceError):
        sandboxes.drop_network(name)


def test_image_id_is_the_digest_ref_while_the_original_sandbox_holds_the_name(sandboxes, gateway, made):
    assert sandboxes.image_id(made) == DIGEST_REF
    gateway.shown_image = "docker.io/library/other@sha256:" + "b" * 64
    assert sandboxes.image_id(made) is None
    gateway.shown_image = None
    gateway.replace(native_name(made))
    assert sandboxes.image_id(made) is None
    assert sandboxes.resolve_image(IMAGE) == DIGEST_REF and sandboxes.resolve_image("unmapped:1") is None


def test_remove_confirms_absence_of_the_original_id(sandboxes, gateway, made):
    assert sandboxes.remove(made)
    calls = [call for call in gateway.calls if call[0] in ("delete", "wait_deleted")]
    assert calls[0] == ("delete", native_name(made)) and calls[1][2] == "sandbox-id-1"
    assert native_name(made) not in gateway.sandboxes and sandboxes.remove(made)
    assert not (sandboxes.config.state_dir / "sandboxes" / f"{native_name(made)}.json").exists()


@pytest.mark.parametrize("fault", ["replaced", "outcome", "other_id", "survives", "unreachable"])
def test_remove_returns_false_on_anything_uncertain(sandboxes, gateway, made, fault):
    name = native_name(made)
    if fault == "replaced":
        gateway.replace(name)
    elif fault == "outcome":
        gateway.delete_outcome = DeletionOutcome.UNSPECIFIED
    elif fault == "other_id":
        gateway.delete_id = "someone-else"
    elif fault == "survives":
        gateway.survives_delete = True
    else:
        def unreachable(*args, **kwargs):
            raise FakeRpcError(grpc.StatusCode.UNAVAILABLE)

        gateway.get = unreachable
    assert sandboxes.remove(made) is False
    if fault in ("replaced", "unreachable"):
        assert not any(call[0] == "delete" for call in gateway.calls)


def test_labelled_filters_by_sanitized_run(sandboxes, gateway):
    first = sandboxes.create(SandboxSpec(image=IMAGE, labels=labels("case:1#a", "build"), workdir=WORKDIR))
    sandboxes.create(SandboxSpec(image=IMAGE, labels=labels("run-2", "build"), workdir=WORKDIR))
    assert sandboxes.labelled("case:1#a") == [native_name(first)]
    assert len(sandboxes.labelled()) == 2
    assert gateway.calls[-1] == ("list_all", "corsair.v2=1")


# --- environments ----------------------------------------------------------------------------------------------------


def _environment(tmp_path: Path, recipe: Recipe) -> tuple[Environment, Path]:
    tree = tmp_path / "rev"
    tree.mkdir(exist_ok=True)
    (tree / "app.py").write_text("x = 1\n")
    digest = hashlib.sha256(json.dumps(recipe.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    return Environment(image="corsair-v2-env:abc", workdir=WORKDIR, runtime_row="pytest-cpython312", recipe_sha256=digest,
                       tree_sha256=tree_sha256(tree)), tree


RECIPE = Recipe(files=(RecipeFile(path="tests/test_smoke.py", content="def test_ok(): pass\n"),),
                setup=(("pip", "install", "-e", "."), ("python", "-c", "print(1)")), network_during_setup=True,
                baseline_test=("python", "-m", "pytest", "tests/test_smoke.py"))


def test_seal_find_and_open_replay_the_recipe_in_order(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    assert sandboxes.find_environment(environment.image, "key") is None
    sandboxes.seal_environment("built", environment.image, "key", "f" * 64, recipe=RECIPE, tree_source=tree,
                               base_image=IMAGE)
    assert sandboxes.find_environment(environment.image, "key") == "f" * 64
    assert sandboxes.find_environment(environment.image, "other") is None
    wanted = labels("run-1", "execute", "exploit")
    gateway.calls.clear()
    name = sandboxes.open_environment(environment, wanted)
    assert name == SandboxSpec(image=IMAGE, labels=wanted).name
    box = gateway.sandboxes[native_name(name)]
    assert box.revisions == [documents()["build"], documents()["none"]]
    commands = [call.command for call in gateway.execs]
    replayed = [command for command in commands if command[0] in ("pip", "python")]
    assert replayed == [list(step) for step in RECIPE.setup] + [list(RECIPE.baseline_test)]
    baseline = gateway.execs[commands.index(list(RECIPE.baseline_test))]
    assert baseline.timeout_seconds == 600
    written = [call.command[-1] for call in gateway.execs if 'cat > "$1"' in call.command[2:3]
               or "mkdir -p \"$(dirname" in call.command[2]]
    assert "/sandbox/tests/test_smoke.py" in written
    index = {key: commands.index(next(c for c in commands if match(c))) for key, match in {
        "extract": lambda c: "tar -x" in c[2], "file": lambda c: c[-1] == "/sandbox/tests/test_smoke.py",
        "setup": lambda c: c[0] == "pip"}.items()}
    assert index["extract"] < index["file"] < index["setup"]
    sets = gateway.policy_sets()
    setup_calls = [i for i, call in enumerate(gateway.calls) if call[0] == "exec_stream" and call[2][0] == "python"]
    assert len(sets) == 2 and setup_calls[0] < gateway.calls.index(sets[1]) < setup_calls[1]
    log = (sandboxes.config.state_dir / "environments" / "opens" / f"{native_name(name)}.log").read_bytes()
    assert b"$ pip install -e ." in log and b"$ python -m pytest tests/test_smoke.py" in log


def test_an_offline_recipe_never_gets_the_build_policy(sandboxes, gateway, tmp_path):
    offline = RECIPE.model_copy(update={"network_during_setup": False})
    environment, tree = _environment(tmp_path, offline)
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=offline, tree_source=tree, base_image=IMAGE)
    name = sandboxes.open_environment(environment, labels("run-1", "execute", "control"))
    assert gateway.sandboxes[native_name(name)].revisions == [documents()["none"]]


def test_a_failed_replay_removes_its_sandbox_and_names_the_step(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=RECIPE, tree_source=tree, base_image=IMAGE)
    gateway.handler = lambda call: Outcome(1, stderr=b"boom") if call.command[0] == "python" else Outcome()
    with pytest.raises(WorkspaceError, match="setup step 2"):
        sandboxes.open_environment(environment, labels("run-1", "execute", "control"))
    assert gateway.sandboxes == {} and [c for c in gateway.execs if c.command[0] == "python"].__len__() == 1


def test_a_failed_baseline_on_open_names_it_and_keeps_the_log(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=RECIPE, tree_source=tree, base_image=IMAGE)
    gateway.handler = lambda call: Outcome(1, b"1 failed") if call.command[:3] == ["python", "-m", "pytest"] \
        else Outcome()
    wanted = labels("run-1", "execute", "control")
    with pytest.raises(WorkspaceError, match="baseline test") as failed:
        sandboxes.open_environment(environment, wanted)
    opened = native_name(SandboxSpec(image=IMAGE, labels=wanted).name)
    log = sandboxes.config.state_dir / "environments" / "opens" / f"{opened}.log"
    assert hashlib.sha256(log.read_bytes()).hexdigest() in str(failed.value) and b"1 failed" in log.read_bytes()
    assert gateway.sandboxes == {}


def test_seal_keeps_replay_timeouts_and_resolves_the_environment_tag(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    assert sandboxes.resolve_image(environment.image) is None
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=RECIPE, tree_source=tree, base_image=IMAGE,
                               setup_timeout=77, baseline_timeout=33)
    assert sandboxes.resolve_image(environment.image) == DIGEST_REF
    sandboxes.open_environment(environment, labels("run-1", "execute", "control"))
    timeouts = {tuple(call.command): call.timeout_seconds for call in gateway.execs}
    assert timeouts[tuple(RECIPE.setup[0])] == 77 and timeouts[tuple(RECIPE.baseline_test)] == 33


@pytest.mark.parametrize("change", ["edited", "removed"])
def test_find_environment_forgets_a_tree_that_can_no_longer_be_opened(sandboxes, tmp_path, change):
    environment, tree = _environment(tmp_path, RECIPE)
    sandboxes.seal_environment("b", environment.image, "k", "log", recipe=RECIPE, tree_source=tree, base_image=IMAGE)
    assert sandboxes.find_environment(environment.image, "k") == "log"
    if change == "edited":
        (tree / "app.py").write_text("x = 3\n")
    else:
        (tree / "app.py").unlink()
        tree.rmdir()
    assert sandboxes.find_environment(environment.image, "k") is None


def test_open_refuses_a_base_image_that_resolves_differently(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=RECIPE, tree_source=tree, base_image=IMAGE)
    sandboxes.config.images[IMAGE] = "docker.io/library/corsair-python@sha256:" + "b" * 64
    gateway.calls.clear()
    with pytest.raises(WorkspaceError, match="no longer resolves"):
        sandboxes.open_environment(environment, labels("run-1", "execute", "control"))
    assert gateway.calls == []


def test_open_refuses_a_changed_tree_or_a_held_identity(sandboxes, gateway, tmp_path):
    environment, tree = _environment(tmp_path, RECIPE)
    sandboxes.seal_environment("b", environment.image, "k", "", recipe=RECIPE, tree_source=tree, base_image=IMAGE)
    wanted = labels("run-1", "execute", "control")
    sandboxes.create(SandboxSpec(image=IMAGE, labels=wanted, workdir=WORKDIR))
    with pytest.raises(SandboxExists):
        sandboxes.open_environment(environment, wanted)
    assert native_name(SandboxSpec(image=IMAGE, labels=wanted).name) in gateway.sandboxes
    (tree / "app.py").write_text("x = 2\n")
    with pytest.raises(WorkspaceError, match="changed"):
        sandboxes.open_environment(environment, labels("run-1", "execute", "exploit"))


# --- the agent workspace ---------------------------------------------------------------------------------------------


def test_building_the_workspace_does_no_io(sandboxes, gateway):
    workspace = sandboxes.agent_workspace(IMAGE, labels("run-1", "build", "builder"))
    assert isinstance(workspace, OpenShellWorkspace) and workspace.ref is None and gateway.calls == []
    assert workspace.spec.network == "build" and workspace.spec.workdir == WORKDIR
    with pytest.raises(ValueError):
        OpenShellWorkspace(sandboxes, spec(), ref=WorkspaceRef(provider="docker", id="x"))


@pytest.mark.anyio
async def test_workspace_creates_lazily_and_runs_commands(sandboxes, gateway):
    workspace = sandboxes.agent_workspace(IMAGE, labels("run-1", "build", "builder"))
    gateway.handler = lambda call: Outcome(0, b"hi\n") if call.command[-1] == "hi" else Outcome()
    assert await workspace.working_dir() == "/sandbox"
    assert workspace.ref == WorkspaceRef(provider="openshell", id=native_name(workspace.spec.name))
    result = await workspace.run(["echo", "hi"], env={"K": "v"})
    assert result.exit_code == 0 and result.stdout == "hi\n"
    assert gateway.execs[-1].command[:2] == ["sh", "-c"] and gateway.execs[-1].command[-2:] == ["echo", "hi"]
    with pytest.raises(TypeError):
        await workspace.run("echo hi")
    with pytest.raises(TypeError):
        await workspace.run(["echo"], shell=True)
    assert gateway.sandboxes[workspace.name].revisions == [documents()["build"]]


@pytest.mark.anyio
async def test_workspace_maps_deadline_transport_and_the_default_limit(sandboxes, gateway):
    workspace = sandboxes.agent_workspace(IMAGE, labels("run-1", "build", "builder"))
    await workspace.working_dir()
    gateway.handler = lambda call: (Outcome(None, b"so far", error=FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED))
                                    if call.command[-1] == "slow" else Outcome())
    with pytest.raises(WorkspaceTimeoutError) as timed:
        await workspace.run(["slow"], timeout=5)
    assert timed.value.stdout == "so far" and "kill -9" in gateway.execs[-1].command[2]
    gateway.handler = lambda call: (Outcome(None, error=FakeRpcError(grpc.StatusCode.UNAVAILABLE))
                                    if call.command[-1] == "flaky" else Outcome())
    with pytest.raises(WorkspaceError, match="delivery uncertain") as failed:
        await workspace.run(["flaky"])
    assert not isinstance(failed.value, (WorkspaceTimeoutError, WorkspaceUnavailableError))
    gateway.handler = lambda call: (Outcome(124, elapsed=backend.EXEC_DEFAULT_TIMEOUT_S)
                                    if call.command[-1] == "forever" else Outcome())
    with pytest.raises(WorkspaceTimeoutError):
        await workspace.run(["forever"])
    gateway.handler = lambda call: Outcome(124, elapsed=1) if call.command[-1] == "own124" else Outcome()
    assert (await workspace.run(["own124"])).exit_code == 124


@pytest.mark.anyio
async def test_workspace_maps_timeout_overflow_and_loss(sandboxes, gateway, monkeypatch):
    workspace = sandboxes.agent_workspace(IMAGE, labels("run-1", "build", "builder"))
    await workspace.working_dir()
    gateway.handler = lambda call: Outcome(124, b"part", elapsed=2) if call.command[-1] == "slow" else Outcome()
    with pytest.raises(WorkspaceTimeoutError) as timed:
        await workspace.run(["slow"], timeout=2)
    assert timed.value.stdout == "part"
    assert any("kill -9" in call.command[2] for call in gateway.execs)
    monkeypatch.setattr(backend, "MAX_OUTPUT_BYTES", 100)
    gateway.handler = lambda call: Outcome(0, b"z" * 10_000)
    with pytest.raises(WorkspaceOutputLimitError):
        await workspace.run(["loud"])
    monkeypatch.setattr(backend, "MAX_OUTPUT_BYTES", 32 * 1024 * 1024)
    gateway.handler = lambda call: Outcome(137, gone=True)
    with pytest.raises(WorkspaceUnavailableError):
        await workspace.run(["die"])


@pytest.mark.anyio
async def test_workspace_adopts_its_own_identity_and_attach_never_creates(sandboxes, gateway):
    wanted = labels("run-1", "build", "builder")
    first = sandboxes.agent_workspace(IMAGE, wanted)
    await first.working_dir()
    again = sandboxes.agent_workspace(IMAGE, wanted)
    await again.working_dir()
    assert again.ref == first.ref and len(gateway.sandboxes) == 1
    missing = OpenShellWorkspace(sandboxes, spec(), ref=WorkspaceRef(provider="openshell", id="corsair-v2-gone"))
    gateway.calls.clear()
    with pytest.raises(WorkspaceUnavailableError):
        await missing.working_dir()
    assert not any(call[0] == "create" for call in gateway.calls)
    assert await first.destroy() and gateway.sandboxes == {}


# --- live: a real gateway ------------------------------------------------------------------------------------------


needs_gateway = pytest.mark.skipif(not LIVE_CONFIG, reason="CORSAIR_OPENSHELL_CONFIG is not set (no gateway)")


def _live() -> OpenShellSandboxes:
    return OpenShellSandboxes.from_config(Path(LIVE_CONFIG or ""))


def _live_spec() -> SandboxSpec:
    image = next(iter(OpenShellConfig.from_json(Path(LIVE_CONFIG or "")).images))
    return SandboxSpec(image=image, labels=labels(f"test-{uuid.uuid4().hex[:10]}", "conformance"), network="build",
                       workdir=WORKDIR)


@pytest.mark.openshell
@needs_gateway
class TestOpenShellWorkspaceConformance(WorkspaceBackendSuite):
    @pytest.fixture
    def backend(self):
        live = _live()
        workspace = OpenShellWorkspace(live, _live_spec())
        yield workspace
        assert remove_confirmed(live, [workspace.name]) == []

    @pytest.fixture
    def fresh_backend(self):
        live, made = _live(), []

        def build() -> OpenShellWorkspace:
            made.append(OpenShellWorkspace(live, _live_spec()))
            return made[-1]

        yield build
        assert remove_confirmed(live, [workspace.name for workspace in made]) == []

    @pytest.fixture
    def attach_backend(self):
        live = _live()
        return lambda ref: OpenShellWorkspace(live, _live_spec(), ref=ref)

    @pytest.fixture
    def destroy_environment(self):
        async def destroy(workspace: OpenShellWorkspace) -> None:
            confirmed = await workspace.destroy()
            record_cleanup(PROVIDER_NAME, workspace.name, confirmed)
            assert confirmed

        return destroy



def test_live_cleanup_is_recorded_and_unconfirmed_names_are_returned(sandboxes, gateway, tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    monkeypatch.setenv("CORSAIR_EVIDENCE_DIR", str(evidence))
    kept, gone = sandboxes.create(spec()), sandboxes.create(spec(extra_label="x"))
    gateway.replace(native_name(kept))
    assert remove_confirmed(sandboxes, [kept, gone]) == [kept]
    lines = [json.loads(line) for line in (evidence / "cleanup.jsonl").read_text().splitlines()]
    assert lines == [{"backend": "openshell", "name": kept, "confirmed": False},
                     {"backend": "openshell", "name": gone, "confirmed": True}]
