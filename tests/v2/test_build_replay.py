"""Trusted build replay: key and failure rules without Docker, the replay itself in a local toolchain image."""
import hashlib
import uuid

import pytest

from corsair.v2.build import environment_key, recipe_sha256, replay
from corsair.v2.contracts import Case, ExitClass, Finding, Recipe, Revision, Runtime
from corsair.v2.workspace.docker import docker, docker_available

IMAGE = "corsair-python:ebf057997574de59"
needs_docker = pytest.mark.skipif(
    not (docker_available() and docker("image", "inspect", IMAGE).returncode == 0),
    reason=f"docker or {IMAGE} unavailable")

RUNTIME = Runtime(row_id="python312-pytest", image=IMAGE, framework="pytest", skill="pytest",
                  run_template=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "{file}::{name}"),
                  exit_codes={0: ExitClass.PASS, 1: ExitClass.TEST_FAILED, 2: ExitClass.HARNESS_ERROR,
                              3: ExitClass.HARNESS_ERROR, 4: ExitClass.HARNESS_ERROR, 5: ExitClass.NO_TESTS},
                  evidence="image-only")
BASELINE = ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_smoke.py")


def make_case(root, fixed=None) -> Case:
    """A tiny tree; the digest is unique per test so a real replay never hits another test's cache."""
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "calc.py").write_text("def parse(text):\n    return text\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_smoke.py").write_text("from app.calc import parse\n\n\ndef test_smoke():\n"
                                                  "    assert parse('a') == 'a'\n")
    digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    return Case(case_id="test-case", finding=Finding(title="t"),
                revision=Revision(source=str(root), tree_sha256=digest), fixed_revision=fixed)


@pytest.fixture
def cleanup_images():
    tags: list[str] = []
    yield tags
    for tag in tags:
        docker("image", "rm", "--force", tag)


def test_keys_are_stable_and_sensitive():
    recipe = Recipe(baseline_test=BASELINE)
    assert recipe_sha256(recipe) == recipe_sha256(Recipe(baseline_test=BASELINE))
    assert recipe_sha256(recipe) != recipe_sha256(Recipe(baseline_test=BASELINE, network_during_setup=True))
    tree = "a" * 64
    key = environment_key(RUNTIME, recipe_sha256(recipe), tree)
    assert key != environment_key(RUNTIME.model_copy(update={"image": "other"}), recipe_sha256(recipe), tree)
    assert key != environment_key(RUNTIME, recipe_sha256(recipe), "b" * 64)


def test_missing_fixed_revision_is_a_recorded_failure(tmp_path):
    result, environment = replay(make_case(tmp_path), RUNTIME, Recipe(baseline_test=BASELINE), revision="fixed",
                                 artifacts=tmp_path / "artifacts")
    assert environment is None and not result.replayed and "no fixed revision" in result.reason


@needs_docker
def test_replay_commits_an_environment_and_reuses_it(tmp_path, cleanup_images):
    case = make_case(tmp_path / "tree")
    recipe = Recipe(setup=(("python", "-c", "open('built.txt', 'w').write('ok')"),), baseline_test=BASELINE)
    result, environment = replay(case, RUNTIME, recipe, artifacts=tmp_path / "artifacts")
    assert environment is not None, result.reason
    cleanup_images.append(environment.image)
    assert result.replayed and result.baseline_exit_code == 0 and result.cleanup_confirmed
    assert environment.image.startswith("corsair-v2-env:") and environment.tree_sha256 == case.revision.tree_sha256
    log = (tmp_path / "artifacts" / result.log.sha256[:2] / result.log.sha256).read_bytes()
    assert b"1 passed" in log and b"[exit 0]" in log
    shown = docker("run", "--rm", "--network=none", "--entrypoint", "cat", environment.image, "/work/built.txt")
    assert shown.stdout == b"ok"

    again, cached = replay(case, RUNTIME, recipe, artifacts=tmp_path / "artifacts")
    assert cached == environment and again.replayed and "cache hit" in again.reason and again.log == result.log


@needs_docker
def test_failed_baseline_gives_no_environment(tmp_path):
    case = make_case(tmp_path / "tree")
    (tmp_path / "tree" / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert False\n")
    result, environment = replay(case, RUNTIME, Recipe(baseline_test=BASELINE), artifacts=tmp_path / "artifacts")
    assert environment is None and not result.replayed
    assert result.baseline_exit_code == 1 and result.reason == "baseline test exited 1"
    assert result.cleanup_confirmed


@needs_docker
def test_setup_failure_stops_before_the_baseline(tmp_path):
    case = make_case(tmp_path / "tree")
    recipe = Recipe(setup=(("sh", "-c", "exit 3"), ("sh", "-c", "touch never")), baseline_test=BASELINE)
    result, environment = replay(case, RUNTIME, recipe, artifacts=tmp_path / "artifacts")
    assert environment is None and result.reason == "setup step 1 exited 3" and result.baseline_exit_code is None


@needs_docker
def test_network_only_during_setup(tmp_path, cleanup_images):
    case = make_case(tmp_path / "tree")
    has_eth0 = ("sh", "-c", "test -e /sys/class/net/eth0")
    offline = Recipe(setup=(has_eth0,), baseline_test=BASELINE)
    result, environment = replay(case, RUNTIME, offline, artifacts=tmp_path / "artifacts")
    assert environment is None and result.reason == "setup step 1 exited 1"

    online = Recipe(setup=(has_eth0,), network_during_setup=True,
                    baseline_test=("sh", "-c", "test ! -e /sys/class/net/eth0"))
    result, environment = replay(case, RUNTIME, online, artifacts=tmp_path / "artifacts")
    assert environment is not None, result.reason
    cleanup_images.append(environment.image)


def test_a_recipe_never_overwrites_the_revisions_own_files(tmp_path):
    from corsair.v2.contracts import Case, Finding, Recipe, RecipeFile, Revision, Runtime
    from corsair.v2.build import replay
    (tmp_path / "app.py").write_text("x = 1\n")
    case = Case(case_id="c", finding=Finding(title="t"), revision=Revision(source=str(tmp_path), tree_sha256="0" * 64))
    runtime = Runtime(row_id="r", image="unused", framework="f", skill="s", run_template=("true",),
                      exit_codes={0: "pass"}, evidence="image-only")
    recipe = Recipe(files=(RecipeFile(path="app.py", content="x = 2\n"),), baseline_test=("true",))
    result, environment = replay(case, runtime, recipe)
    assert environment is None and not result.replayed and "app.py" in result.reason
