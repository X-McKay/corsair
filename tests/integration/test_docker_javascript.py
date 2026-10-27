"""Real-Docker evidence for the JavaScript prototype-pollution recipe.

These exercise the content-tagged corsair-javascript image (just images-gym) and
drivers/javascript/driver.mjs: a control that holds, an adversarial violation on
vulnerable source, a safe variant that holds, an unexpected target exception, absent
relevant coverage, confirmed cleanup, and the callable bound through each code-owned
export form (named property, the ``module.exports`` marker, ``default``).
Marked docker so the suite stays independent; operation ids are per-process unique so
concurrent suites in sibling worktrees never collide on a labelled container.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import docker
import pytest
from docker.errors import DockerException

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.scm.local import prepare_case
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Budget,
    Case,
    EvidenceInput,
    Finding,
    JavaScriptRecipe,
    PlanRevision,
    RunManifest,
    Source,
    Submission,
)
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.integration.sandbox_seconds import assert_sandbox_seconds
from tests.integration.trusted_images import content_image, with_content_images

pytestmark = pytest.mark.docker

JS_KIND = "javascript.prototype_pollution/1"
JS_IMAGE = content_image(JS_KIND)

# Vulnerable: a __proto__ key in the parsed-JSON source reaches Object.prototype.
VULNERABLE = """// Merge user preferences (parsed request JSON) onto the stored defaults.
function mergePreferences(target, source) {
  for (const key of Object.keys(source)) {
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (!target[key] || typeof target[key] !== "object") {
        target[key] = {};
      }
      mergePreferences(target[key], value);
    } else {
      target[key] = value;
    }
  }
  return target;
}

module.exports = { mergePreferences };
"""

# Safe: dangerous keys are skipped, so the same adversarial payload cannot pollute.
SAFE = """// Merge user preferences (parsed request JSON) onto the stored defaults.
const BLOCKED_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function mergePreferences(target, source) {
  for (const key of Object.keys(source)) {
    if (BLOCKED_KEYS.has(key)) continue;
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (!Object.prototype.hasOwnProperty.call(target, key) || typeof target[key] !== "object") {
        target[key] = {};
      }
      mergePreferences(target[key], value);
    } else {
      target[key] = value;
    }
  }
  return target;
}

module.exports = { mergePreferences };
"""

# Throws unconditionally: an unexpected target exception, not an assertion failure.
THROWS = """function mergePreferences(target, source) {
  throw new Error("boom");
}

module.exports = { mergePreferences };
"""

# The finding line sits in a branch that the submitted payloads never execute.
DEAD_BRANCH = """function mergePreferences(target, source) {
  if (source && source.never) {
    target.injected = 1;
  }
  return target;
}

module.exports = { mergePreferences };
"""


# The module export itself is the callable (an anonymous function, so it has no name).
MODULE_EXPORT = """module.exports = function (target, source) {
  for (const key of Object.keys(source)) {
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (!target[key] || typeof target[key] !== "object") {
        target[key] = {};
      }
      module.exports(target[key], value);
    } else {
      target[key] = value;
    }
  }
  return target;
};
"""

# The callable is the export's `default` property (transpiled-ESM style CommonJS).
DEFAULT_EXPORT = VULNERABLE.replace(
    "module.exports = { mergePreferences };",
    'Object.defineProperty(exports, "__esModule", { value: true });\n'
    "exports.default = mergePreferences;",
)


def _docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get(JS_IMAGE)
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires image: {type(exc).__name__}")
        pytest.skip(f"real Docker image unavailable: {type(exc).__name__}")
    return client


def _manifest(image_id: str) -> RunManifest:
    return RunManifest(
        package_version="0.1",
        request_digest="1" * 64,
        config_digest="2" * 64,
        producer_prompt_digest="3" * 64,
        auditor_prompt_digest="4" * 64,
        image_id=image_id,
        models={"producer": "test", "auditor": "test"},
    )


def _submission() -> Submission:
    return Submission(
        control_payload={"theme": {"color": "dark"}},
        exploit_payload={"__proto__": {"polluted": "corsair"}},
        hypothesis="a __proto__ merge source reaches the shared object prototype",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _prepared(
    tmp_path: Path, image_id: str, source_js: str, *, line: int, function: str = "mergePreferences"
):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "merge.js").write_text(source_js, encoding="utf-8")
    recipe = JavaScriptRecipe(
        module_file="src/merge.js",
        function=function,
        fixed_arguments=[{}],
    )
    case = Case(
        case_id="js-docker-case",
        finding=Finding(
            title="prototype pollution",
            description="merge source reaches the prototype",
            file="src/merge.js",
            line=line,
            claim_scope="component",
        ),
        source=Source(path="project"),
        recipe=recipe,
    )
    settings = with_content_images(
        Settings(
            source_root=str(tmp_path),
            artifact_root=str(tmp_path / "artifacts"),
            runtime="runc",
        )
    )
    store = ArtifactStore(tmp_path / "artifacts")
    return settings, store, prepare_case(case, settings, store, _manifest(image_id))


def _operation() -> str:
    return f"js-{uuid.uuid4().hex}"


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def _evaluate(client, tmp_path, source_js, *, line, operation, function="mergePreferences"):
    image_id = DockerSandbox(with_content_images(Settings()), client=client).image_id_for(JS_KIND)
    settings, store, prepared = _prepared(
        tmp_path, image_id, source_js, line=line, function=function
    )
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="run",
            operation_id=operation,
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=30),
        )
    )
    return observation


def test_real_docker_js_vulnerable_control_violation_and_cleanup(tmp_path: Path) -> None:
    client = _docker_client()
    operation = _operation()
    observation = _evaluate(client, tmp_path, VULNERABLE, line=2, operation=operation)

    assert observation.cleanup_confirmed
    assert observation.feedback is None
    assert observation.control is not None and observation.adversarial is not None
    assert observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.control.target_executed
    assert 2 in observation.control.covered_lines
    assert observation.adversarial.outcome.value == "VIOLATION"
    assert observation.adversarial.target_executed
    assert 2 in observation.adversarial.covered_lines
    assert_sandbox_seconds(observation)
    _assert_cleanup(client, operation)


def test_real_docker_js_safe_variant_holds_on_both_roles(tmp_path: Path) -> None:
    client = _docker_client()
    operation = _operation()
    observation = _evaluate(client, tmp_path, SAFE, line=4, operation=operation)

    assert observation.cleanup_confirmed
    assert observation.control is not None and observation.adversarial is not None
    assert observation.control.outcome.value == "PROPERTY_HELD"
    # The dangerous key is skipped, so the adversarial input never pollutes: held.
    assert observation.adversarial.outcome.value == "PROPERTY_HELD"
    _assert_cleanup(client, operation)


def test_real_docker_js_unexpected_exception_is_error(tmp_path: Path) -> None:
    client = _docker_client()
    operation = _operation()
    observation = _evaluate(client, tmp_path, THROWS, line=1, operation=operation)

    assert observation.cleanup_confirmed
    assert observation.control is not None
    # A thrown target error writes no observation marker and is never a positive.
    assert observation.control.outcome.value == "ERROR"
    _assert_cleanup(client, operation)


def test_real_docker_js_absent_relevant_coverage_is_invalid(tmp_path: Path) -> None:
    client = _docker_client()
    operation = _operation()
    # Line 3 is the body of a branch the submitted payloads never take.
    observation = _evaluate(client, tmp_path, DEAD_BRANCH, line=3, operation=operation)

    assert observation.cleanup_confirmed
    assert observation.control is not None
    assert observation.control.outcome.value == "INVALID"
    assert 3 not in observation.control.covered_lines
    _assert_cleanup(client, operation)


@pytest.mark.parametrize(
    ("source_js", "function"),
    [(MODULE_EXPORT, "module.exports"), (DEFAULT_EXPORT, "default")],
    ids=["module-exports-marker", "default-property"],
)
def test_real_docker_js_binds_the_export_marker_callable(
    tmp_path: Path, source_js: str, function: str
) -> None:
    client = _docker_client()
    operation = _operation()
    observation = _evaluate(
        client, tmp_path, source_js, line=2, operation=operation, function=function
    )

    assert observation.cleanup_confirmed
    assert observation.feedback is None
    assert observation.control is not None and observation.adversarial is not None
    # The receipt binds the callable: the control ran its body and held.
    assert observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.control.target_executed
    assert 2 in observation.control.covered_lines
    assert observation.adversarial.outcome.value == "VIOLATION"
    assert observation.adversarial.target_executed
    assert 2 in observation.adversarial.covered_lines
    _assert_cleanup(client, operation)


def test_real_docker_js_module_export_is_never_bound_by_its_name(tmp_path: Path) -> None:
    client = _docker_client()
    operation = _operation()
    # Without the explicit marker the driver does not guess: the named property is
    # absent, so the existing callable-not-found path reports ERROR on the control.
    named = MODULE_EXPORT.replace("module.exports = function (", "module.exports = function merge(")
    observation = _evaluate(client, tmp_path, named, line=2, operation=operation, function="merge")

    assert observation.cleanup_confirmed
    assert observation.control is not None
    assert observation.control.outcome.value == "ERROR"
    assert not observation.control.target_executed
    _assert_cleanup(client, operation)
