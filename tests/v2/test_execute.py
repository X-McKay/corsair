"""Trusted probe execution: template, exit map, token and blinding rules without Docker; a real pytest probe pair
end to end in the local toolchain image; and the reconciler."""
import hashlib
import uuid

import pytest

from corsair import execute
from corsair.build import replay
from corsair.contracts import Environment, ExitClass, FrozenPatch, Outcome, ProbeDraft, ProbeFacts, Recipe
from corsair.reconcile import sweep
from corsair.workspace.docker import DockerConfig, create, docker, labels
from tests.v2.test_build_replay import BASELINE, RUNTIME, make_case, needs_docker

SYNTAX_RUNTIME = RUNTIME.model_copy(update={"syntax_check": (
    "/usr/bin/env", "PYTHONPYCACHEPREFIX=/tmp/corsair-pycache", "python3", "-m", "py_compile", "{file}")})


def draft(role: str, holds: str, test_file: str = "tests/corsair/test_probe.py", name: str = "test_probe",
          before: str = "pass") -> ProbeDraft:
    """A probe following the protocol: ``before`` runs after ``start``; ``holds`` is the asserted condition, written
    to ``check`` and asserted with the token."""
    source = ("import os\nfrom app.calc import parse\n\n\n"
              f"def {name}():\n"
              "    marker = os.environ['CORSAIR_MARKER_DIR']\n"
              "    open(marker + '/start', 'w').close()\n"
              f"    {before}\n"
              f"    holds = {holds}\n"
              "    open(marker + '/check', 'w').write('holds' if holds else 'violated')\n"
              "    assert holds, os.environ['CORSAIR_TOKEN']\n"
              "    open(marker + '/end', 'w').close()\n")
    return ProbeDraft(role=role, test_file=test_file, test_name=name, source=source)


def frozen(control: ProbeDraft, exploit: ProbeDraft) -> FrozenPatch:
    digest = hashlib.sha256((control.source + exploit.source).encode()).hexdigest()
    return FrozenPatch(control=control, exploit=exploit, sha256=digest)


def test_template_filling_is_generic():
    probe = draft("control", "True", test_file="src/test/java/org/x/ProbeTest.java", name="probe")
    template = ("run", "{file}", "--class={class}", "-m", "{module}#{name}", "{literal}")
    assert execute.fill_template(template, probe) == [
        "run", "src/test/java/org/x/ProbeTest.java", "--class=ProbeTest", "-m", "src.test.java.org.x.ProbeTest#probe",
        "{literal}"]


def test_exit_codes_map_through_the_row_and_unlisted_is_unknown():
    assert execute.exit_class(RUNTIME, 1) is ExitClass.TEST_FAILED
    assert execute.exit_class(RUNTIME, 5) is ExitClass.NO_TESTS
    assert execute.exit_class(RUNTIME, 137) is ExitClass.UNKNOWN
    assert execute.exit_class(RUNTIME, None) is None


def test_tokens_are_fresh_for_every_run():
    tokens = {execute.new_token() for _ in range(50)}
    assert len(tokens) == 50 and all(len(token) == 32 for token in tokens)


def facts(exit_code, cls, start, end=False, token=False, check=None, timed_out=False):
    return ProbeFacts(exit_code=exit_code, exit_class=cls, timed_out=timed_out, start_marker=start, end_marker=end,
                      token_in_output=token, check_marker=check)


@pytest.mark.parametrize(("seen", "expected"), [
    (facts(5, ExitClass.NO_TESTS, False), ("not_run", "not discovered")),
    (facts(5, ExitClass.NO_TESTS, True, True, False, "holds"), ("not_run", "not discovered")),
    (facts(2, ExitClass.HARNESS_ERROR, False), ("not_run", "harness error")),
    (facts(1, ExitClass.TEST_FAILED, False), ("not_run", "body did not start")),
    (facts(0, ExitClass.PASS, False, True), ("not_run", "body did not start")),
    (facts(1, ExitClass.TEST_FAILED, True), ("errored", "raised before the check marker")),
    (facts(0, ExitClass.PASS, True, True, False, "holds"), ("ok", None)),
    (facts(1, ExitClass.TEST_FAILED, True, False, True, "violated"), ("ok", None)),
    (facts(0, ExitClass.PASS, True, False), ("ok", None)),  # anomalous: discarded like any other outcome
    (facts(2, ExitClass.HARNESS_ERROR, True), ("ok", None)),  # infra after the body started
    (facts(None, None, True, timed_out=True), ("ok", None)),
])
def test_check_run_keeps_only_a_mechanical_class_and_a_fixed_hint(seen, expected):
    assert execute.check_result(seen) == expected


def _environment():
    return Environment(image="img", runtime_row="row", recipe_sha256="a" * 64, tree_sha256="b" * 64)


@pytest.mark.parametrize(("seen", "result"), [
    (facts(1, ExitClass.TEST_FAILED, True), "errored"), (facts(5, ExitClass.NO_TESTS, False), "not_run"),
    (facts(0, ExitClass.PASS, True, True, False, "holds"), "ok"),
    (facts(1, ExitClass.TEST_FAILED, True, False, True, "violated"), "ok"),
    (facts(0, ExitClass.PASS, True, True, True, "holds"), "ok"), (facts(None, None, False), "ok")])
def test_diagnose_never_returns_run_output(monkeypatch, seen, result):
    token = "f" * 32
    output = f"ImportError in tests/corsair/test_probe.py line 3: application said {token} secret".encode()
    syntax = (1, b"tests/corsair/test_probe.py:3: SyntaxError " + b"x" * 10_000)
    observed = execute.Observation(facts=seen, output=output, duration_s=1.0, token=token, cleanup_confirmed=True,
                                   syntax=syntax)
    calls = []
    monkeypatch.setattr(execute, "observe", lambda *a, **kw: calls.append(kw) or observed)
    got, text = execute.diagnose(_environment(), RUNTIME, draft("exploit", "True"))
    assert got == result and calls[0]["syntax_check"] is True and calls[0]["revision"] == "vulnerable"
    if result == "ok":
        assert text is None
    else:
        assert text.startswith(f"check: {result}\nhint: ")
        assert "secret" not in text and token not in text and "ImportError" not in text
        assert "SyntaxError" in text and len(text.encode()) <= execute.SYNTAX_LIMIT + 200


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("execute")
    result, environment = replay(make_case(root / "tree"), RUNTIME, Recipe(baseline_test=BASELINE),
                                 artifacts=root / "artifacts")
    assert environment is not None, result.reason
    yield environment
    docker("image", "rm", "--force", environment.image)


@needs_docker
def test_probe_pair_end_to_end(environment, tmp_path):
    exploit = draft("exploit", "parse('<x>') == '&lt;x&gt;'")
    control = draft("control", "parse('plain') == 'plain'", test_file="tests/corsair/test_control.py")
    patch = frozen(control, exploit)
    run_id = f"test-{uuid.uuid4().hex[:10]}"

    failed = execute.run_probe(environment, RUNTIME, patch, "exploit", run_id=run_id, artifacts=tmp_path)
    assert failed.facts.exit_code == 1 and failed.facts.exit_class is ExitClass.TEST_FAILED
    assert failed.facts.start_marker and not failed.facts.end_marker and failed.facts.token_in_output
    assert failed.facts.check_marker == "violated"
    assert failed.outcome is Outcome.ASSERTION_FAILED and failed.cleanup_confirmed
    assert failed.duration_s is not None and failed.output is not None and failed.patch_sha256 == patch.sha256
    assert failed.tree_sha256 == environment.tree_sha256 and failed.image_digest.startswith("sha256:")

    passed = execute.run_probe(environment, RUNTIME, patch, "control", run_id=run_id, artifacts=tmp_path)
    assert passed.facts.exit_code == 0 and passed.facts.start_marker and passed.facts.end_marker
    assert not passed.facts.token_in_output and passed.facts.check_marker == "holds"
    assert passed.outcome is Outcome.PASSED
    output = (tmp_path / passed.output.sha256[:2] / passed.output.sha256).read_bytes()
    assert b"1 passed" in output

    # A failed control assertion reads like the exploit's: the table is role-agnostic.
    bad_control = draft("control", "parse('plain') == 'other'", test_file="tests/corsair/test_control.py")
    run = execute.run_probe(environment, RUNTIME, frozen(bad_control, exploit), "control", run_id=run_id,
                            artifacts=tmp_path)
    assert run.outcome is Outcome.ASSERTION_FAILED and run.facts.check_marker == "violated"
    assert docker("ps", "-a", "--filter", f"label=corsair.v2.run={run_id}", "--format", "{{.Names}}").stdout == b""


@needs_docker
def test_diagnose_returns_a_class_and_hint_but_never_a_result(environment):
    def check(probe):
        return execute.diagnose(environment, SYNTAX_RUNTIME, probe)

    result, text = check(draft("exploit", "True", before="parse(undefined_name)"))
    assert result == "errored" and "raised before the check marker" in text and "NameError" not in text
    assert "--- syntax check (exit 0) ---" in text
    skipped = ProbeDraft(role="exploit", test_file="tests/corsair/test_skip.py", test_name="test_skip",
                         source="import pytest\n\n\ndef test_skip():  # never reaches CORSAIR_MARKER_DIR\n"
                                "    pytest.skip('fixture missing')\n")
    result, text = check(skipped)
    assert result == "not_run" and "body did not start" in text and "1 skipped" not in text
    broken = draft("exploit", "True", before="x = (")
    result, text = check(broken)
    assert result == "not_run" and "harness error" in text and "SyntaxError" in text
    assert check(draft("exploit", "parse('<x>') == '&lt;x&gt;'")) == ("ok", None)


@needs_docker
def test_timeout_is_infra_not_retried(environment, tmp_path):
    hang = draft("control", "True", before="import time; time.sleep(600)")
    patch = frozen(hang, draft("exploit", "True"))
    run = execute.run_probe(environment, RUNTIME, patch, "control", artifacts=tmp_path, timeout=5)
    assert run.facts.timed_out and run.facts.exit_code is None and run.outcome is Outcome.INFRA
    assert run.cleanup_confirmed


@needs_docker
def test_sweep_removes_one_runs_containers():
    run_id = f"test-{uuid.uuid4().hex[:10]}"
    names = [create(DockerConfig(image=RUNTIME.image, labels=labels(run_id, "sweep", role))) for role in ("a", "b")]
    other = create(DockerConfig(image=RUNTIME.image, labels=labels(f"{run_id}-other", "sweep")))
    try:
        result = sweep(run_id)
        assert sorted(result.removed) == sorted(names) and result.unconfirmed == ()
    finally:
        assert sweep(f"{run_id}-other").removed == (other,)
