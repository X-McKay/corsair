"""Real-Docker qualification of the Perl html-injection recipe (CWE-79).

A separate language file (its own ``docker`` marker scope) so the Python and Perl suites
stay independent. The positive case runs the frozen corpus row; the remaining cases use
small inline modules to exercise the violation, unexpected-exception, invalid-control,
and absent-coverage gates and to confirm cleanup against the immutable container id.
"""

from __future__ import annotations

import hashlib
import os
import time
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
    PerlRecipe,
    PlanRevision,
    RunManifest,
    Source,
    Submission,
    digest,
)
from corsair.policies.verdicts import fix_status
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.integration.sandbox_seconds import assert_sandbox_seconds
from tests.integration.trusted_images import content_image

pytestmark = pytest.mark.docker

# Set CORSAIR_TEST_PERL_IMAGE to qualify a differently tagged scratch build of the driver.
PERL_KIND = "perl.html_injection/1"
PERL_IMAGE = os.environ.get("CORSAIR_TEST_PERL_IMAGE") or content_image(PERL_KIND)
CORPUS = Path("evals/datasets/corpus/infosec-harness/perl/xss")


def _docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires daemon: {type(exc).__name__}")
        pytest.skip(f"real Docker unavailable: {type(exc).__name__}")
    try:
        client.images.get(PERL_IMAGE)
    except DockerException as exc:
        if os.getenv("CORSAIR_TEST_DOCKER") == "1":
            pytest.fail(f"explicit real Docker test requires image: {type(exc).__name__}")
        name = type(exc).__name__
        pytest.skip(f"real Docker image unavailable; build with just images-gym: {name}")
    return client


def _image_id(client: docker.DockerClient) -> str:
    settings = Settings(images={PERL_KIND: PERL_IMAGE})
    return DockerSandbox(settings, client=client).image_id_for(PERL_KIND)


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
        control_payload="hello",
        exploit_payload="<script>alert(1)</script>",
        hypothesis="unescaped interpolation injects markup",
        plan=PlanRevision(revision=1, objective="verify", next_steps=["run"], reason="test"),
    )


def _settings(tmp_path: Path, source_root: Path) -> tuple[Settings, ArtifactStore]:
    settings = Settings(
        source_root=str(source_root),
        artifact_root=str(tmp_path / "artifacts"),
        images={PERL_KIND: PERL_IMAGE},
        runtime="runc",
    )
    return settings, ArtifactStore(tmp_path / "artifacts")


def _recipe(**update: object) -> PerlRecipe:
    fields: dict[str, object] = {
        "module_file": "lib/Renderer.pm",
        "package": "Renderer",
        "function": "render",
        "fixed_args": [],
        "expected_control": "<div class='comment'>hello</div>",
        "baseline_markup_chars": 4,
        "allowed_exceptions": [],
    }
    fields.update(update)
    return PerlRecipe.model_validate(fields)


def _inline_prepared(
    tmp_path: Path, image_id: str, body: str, *, line: int = 10, **recipe_update: object
):
    root = tmp_path / "tree"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "Renderer.pm").write_text(body, encoding="utf-8")
    settings, store = _settings(tmp_path, root)
    case = Case(
        case_id="perl-inline",
        finding=Finding(title="xss", description="render sink", file="lib/Renderer.pm", line=line),
        source=Source(path="."),
        recipe=_recipe(**recipe_update),
    )
    return settings, store, prepare_case(case, settings, store, _manifest(image_id))


def _assert_cleanup(client: docker.DockerClient, operation_id: str) -> None:
    containers = client.containers.list(
        all=True,
        filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
    )
    assert containers == []


def test_real_docker_perl_corpus_row_demonstrates_and_fix_verifies(tmp_path: Path) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    source_root = CORPUS.resolve()

    # Vulnerable revision (xss/b): control holds and the exploit injects markup.
    settings, store = _settings(tmp_path / "vuln", source_root)
    case = Case(
        case_id="perl-xss-b",
        finding=Finding(title="xss", description="render sink", file="lib/Renderer.pm", line=10),
        source=Source(path="b"),
        fixed_source=Source(path="a"),
        recipe=_recipe(),
    )
    prepared = prepare_case(case, settings, store, _manifest(image_id))
    sandbox = DockerSandbox(settings, client=client, store=store)
    verifier = EvidenceVerifier(settings, store, sandbox)

    started = time.monotonic()
    observation = verifier.evaluate(
        EvidenceInput(
            run_id="perl-vuln",
            operation_id="perl-docker-vulnerable",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    elapsed = time.monotonic() - started
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "VIOLATION"
    # The finding's sink line is executed in both runs.
    assert 10 in observation.control.covered_lines
    assert 10 in observation.adversarial.covered_lines
    assert_sandbox_seconds(observation)
    _assert_cleanup(client, "perl-docker-vulnerable")
    # Two containers (control + adversarial). A test-side sanity ceiling, not the kernel's
    # per-role probe deadline (Budget.probe_timeout_seconds above); slower hosts were seen
    # at ~22 s for the pair, so keep generous headroom against CI jitter.
    assert elapsed < 60

    # Fixed revision (xss/a): the exploit no longer reproduces, so the fix is verified.
    fixed_settings, fixed_store = _settings(tmp_path / "fixed", source_root)
    fixed_prepared = prepare_case(case, fixed_settings, fixed_store, _manifest(image_id))
    fixed_verifier = EvidenceVerifier(
        fixed_settings, fixed_store, DockerSandbox(fixed_settings, client=client, store=fixed_store)
    )
    fixed_observation = fixed_verifier.evaluate(
        EvidenceInput(
            run_id="perl-fixed",
            operation_id="perl-docker-fixed",
            prepared=fixed_prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
            fixed=True,
        )
    )
    assert fixed_observation.cleanup_confirmed is True
    assert fixed_observation.control and fixed_observation.control.outcome.value == "PROPERTY_HELD"
    assert (
        fixed_observation.adversarial
        and fixed_observation.adversarial.outcome.value == "PROPERTY_HELD"
    )
    assert fix_status(fixed_observation).value == "DEMONSTRATION_BLOCKED"
    _assert_cleanup(client, "perl-docker-fixed")


# Module line 10 is the sink `return` in these inline trees.
_ESCAPING = (
    "package Renderer;\nuse strict;\nuse warnings;\n\n"
    "my %E = ('&' => '&amp;', '<' => '&lt;', '>' => '&gt;');\n\n"
    "# comment\nsub render {\n    my ($text) = @_;\n"
    "    $text =~ s/([&<>])/$E{$1}/g;\n"
    '    return "<div class=\'comment\'>" . $text . "</div>";\n}\n\n1;\n'
)
_VULNERABLE = (
    "package Renderer;\nuse strict;\nuse warnings;\n\n\n\n# comment\nsub render {\n"
    '    my ($text) = @_;\n    return "<div class=\'comment\'>" . $text . "</div>";\n}\n\n1;\n'
)
# Safe render that returns undef (no output at all) for markup input. No HTML is
# produced, so this must never establish an injection.
_UNDEF_ON_MARKUP = (
    "package Renderer;\nuse strict;\nuse warnings;\n\n\n\n# comment\nsub render {\n"
    "    my ($text) = @_;\n    return undef if $text =~ /[<>]/;\n"
    '    return "<div class=\'comment\'>" . $text . "</div>";\n}\n\n1;\n'
)
_DIES = (
    "package Renderer;\nuse strict;\nuse warnings;\n\n\n\n# comment\nsub render {\n"
    '    my ($text) = @_;\n    die "boom\\n";\n}\n\n1;\n'
)


@pytest.mark.parametrize(
    "body,line,recipe_update,role,expected",
    [
        # Vulnerable render: the exploit payload injects raw tags -> VIOLATION.
        (_VULNERABLE, 10, {}, "adversarial", "VIOLATION"),
        # Escaping render: control holds and the exploit is neutralized -> HELD.
        (_ESCAPING, 11, {}, "adversarial", "PROPERTY_HELD"),
        # Undefined adversarial output is not injected markup -> HELD, never VIOLATION.
        (_UNDEF_ON_MARKUP, 10, {}, "adversarial", "PROPERTY_HELD"),
        # The same renderer still preserves the exact benign control.
        (_UNDEF_ON_MARKUP, 10, {}, "control", "PROPERTY_HELD"),
        # Unexpected die with no allowed exception -> ERROR, never a positive.
        (_DIES, 10, {}, "adversarial", "ERROR"),
        # A control that does not preserve the expected benign output -> INVALID.
        (_VULNERABLE, 10, {"expected_control": "<div>other</div>"}, "control", "INVALID"),
    ],
)
def test_role_outcomes(tmp_path, body, line, recipe_update, role, expected) -> None:
    client = _docker_client()
    image_id = _image_id(client)
    settings, store, prepared = _inline_prepared(
        tmp_path, image_id, body, line=line, **recipe_update
    )
    sandbox = DockerSandbox(settings, client=client, store=store)
    # Distinct per parametrized body so cases with the same role/outcome never share an id.
    body_tag = hashlib.sha256(body.encode()).hexdigest()[:8]
    operation = f"perl-role-{role}-{expected}-{body_tag}"
    raw_ref = sandbox.execute_role(
        prepared,
        _submission(),
        role,
        Budget(probe_timeout_seconds=20),
        operation_id=operation,
    )
    verifier = EvidenceVerifier(settings, store, sandbox)
    native, _valid = verifier._validate_raw(
        raw_ref,
        expected_operation=operation,
        expected_role=role,
        expected_source=prepared.source.sha256,
        expected_submission=digest(_submission()),
        prepared=prepared,
        fixed=False,
    )
    assert native.outcome.value == expected
    _assert_cleanup(client, operation)


def test_undefined_adversarial_output_never_demonstrates_injection(tmp_path: Path) -> None:
    """A renderer that returns undef for markup input produced no HTML: no VIOLATION."""
    client = _docker_client()
    settings, store, prepared = _inline_prepared(
        tmp_path, _image_id(client), _UNDEF_ON_MARKUP, line=10
    )
    sandbox = DockerSandbox(settings, client=client, store=store)
    observation = EvidenceVerifier(settings, store, sandbox).evaluate(
        EvidenceInput(
            run_id="perl-undef",
            operation_id="perl-docker-undef",
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=20),
        )
    )
    assert observation.cleanup_confirmed is True
    assert observation.control and observation.control.outcome.value == "PROPERTY_HELD"
    assert observation.adversarial and observation.adversarial.outcome.value == "PROPERTY_HELD"
    assert 10 in observation.adversarial.covered_lines
    _assert_cleanup(client, "perl-docker-undef")


def test_absent_target_coverage_is_invalid(tmp_path: Path) -> None:
    """A finding line that is never executed cannot be a relevant coverage demonstration."""
    client = _docker_client()
    image_id = _image_id(client)
    # Line 1 (the `package` statement) is compiled, not executed as a traced statement.
    settings, store, prepared = _inline_prepared(tmp_path, image_id, _VULNERABLE, line=1)
    sandbox = DockerSandbox(settings, client=client, store=store)
    raw_ref = sandbox.execute_role(
        prepared,
        _submission(),
        "adversarial",
        Budget(probe_timeout_seconds=20),
        operation_id="perl-absent",
    )
    verifier = EvidenceVerifier(settings, store, sandbox)
    native, valid = verifier._validate_raw(
        raw_ref,
        expected_operation="perl-absent",
        expected_role="adversarial",
        expected_source=prepared.source.sha256,
        expected_submission=digest(_submission()),
        prepared=prepared,
        fixed=False,
    )
    assert valid is False
    assert native.outcome.value == "INVALID"
    _assert_cleanup(client, "perl-absent")
