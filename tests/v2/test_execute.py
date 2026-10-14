"""Trusted probe execution: template, exit map, token and blinding rules without Docker; a real pytest probe pair
end to end in the local toolchain image; and the reconciler."""
import hashlib
import importlib
import sys
import types
import uuid

import pytest

from corsair.v2 import execute
from corsair.v2.build import replay
from corsair.v2.contracts import (Environment, ExitClass, FrozenPatch, Outcome, ProbeDraft, ProbeFacts, Recipe)
from corsair.v2.reconcile import sweep
from corsair.v2.workspace.docker import DockerConfig, create, docker, labels
from tests.v2.test_build_replay import BASELINE, RUNTIME, make_case, needs_docker


def _d8(facts: ProbeFacts) -> Outcome:
    """The D8 table, standing in only when the Decide worker's outcome.py is absent from this branch."""
    if facts.timed_out or facts.exit_code is None or facts.exit_class in (ExitClass.HARNESS_ERROR, None):
        return Outcome.INFRA
    if facts.exit_class is ExitClass.NO_TESTS or not facts.start_marker:
        return Outcome.NOT_RUN
    if facts.exit_class is ExitClass.PASS and facts.end_marker and not facts.token_in_output:
        return Outcome.PASSED
    if facts.exit_class is ExitClass.TEST_FAILED and not facts.end_marker:
        return Outcome.ASSERTION_FAILED if facts.token_in_output else Outcome.ERRORED
    return Outcome.ANOMALOUS


@pytest.fixture(autouse=True)
def outcome_module(monkeypatch):
    try:
        importlib.import_module("corsair.v2.outcome")
    except ImportError:
        monkeypatch.setitem(sys.modules, "corsair.v2.outcome", types.SimpleNamespace(classify=_d8))


def draft(role: str, body: str, test_file: str = "tests/corsair/test_probe.py", name: str = "test_probe"
          ) -> ProbeDraft:
    source = ("import os\nfrom app.calc import parse\n\n\n"
              f"def {name}():\n"
              "    marker = os.environ['CORSAIR_MARKER_DIR']\n"
              "    open(marker + '/start', 'w').close()\n"
              f"    {body}\n"
              "    open(marker + '/end', 'w').close()\n")
    return ProbeDraft(role=role, test_file=test_file, test_name=name, source=source)


def frozen(control: ProbeDraft, exploit: ProbeDraft) -> FrozenPatch:
    digest = hashlib.sha256((control.source + exploit.source).encode()).hexdigest()
    return FrozenPatch(control=control, exploit=exploit, sha256=digest)


def test_template_filling_is_generic():
    probe = draft("control", "pass", test_file="src/test/java/org/x/ProbeTest.java", name="probe")
    template = ("run", "{file}", "--class={class}", "-m", "{module}#{name}", "{literal}")
    assert execute.fill_template(template, probe) == [
        "run", "src/test/java/org/x/ProbeTest.java", "--class=ProbeTest", "-m", "src.test.java.org.x.ProbeTest#probe",
        "{literal}"]


def test_exit_codes_map_through_the_row_and_unlisted_is_unknown():
    assert execute.exit_class(RUNTIME, 1) is ExitClass.TEST_FAILED
    assert execute.exit_class(RUNTIME, 5) is ExitClass.NO_TESTS
    assert execute.exit_class(RUNTIME, 137) is ExitClass.UNKNOWN
    assert execute.exit_class(RUNTIME, None) is None


def test_tokens_are_fresh_and_only_for_the_exploit():
    tokens = {execute.new_token("exploit") for _ in range(50)}
    assert len(tokens) == 50 and all(len(token) == 32 for token in tokens)
    assert execute.new_token("control") is None


@pytest.mark.parametrize("outcome, leaks", [(Outcome.ERRORED, True), (Outcome.NOT_RUN, True),
                                            (Outcome.PASSED, False), (Outcome.ASSERTION_FAILED, False),
                                            (Outcome.ANOMALOUS, False), (Outcome.INFRA, False)])
def test_diagnose_is_blinded(monkeypatch, outcome, leaks):
    token = "f" * 32
    output = (f"ImportError at line 3 {token} " + "x" * 20_000).encode()
    seen = execute.Observation(facts=None, output=output, duration_s=1.0, token=token, cleanup_confirmed=True)
    monkeypatch.setattr(execute, "observe", lambda *args, **kwargs: seen)
    monkeypatch.setattr(execute, "classify", lambda facts: outcome)
    environment = Environment(image="img", runtime_row="row", recipe_sha256="a" * 64, tree_sha256="b" * 64)
    got, text = execute.diagnose(environment, RUNTIME, draft("exploit", "pass"))
    assert got is outcome
    if leaks:
        assert "ImportError" in text and token not in text and len(text.encode()) <= execute.DIAGNOSTICS_LIMIT
    else:
        assert text == ""


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
    exploit = draft("exploit", "assert parse('<x>') == '&lt;x&gt;', os.environ['CORSAIR_TOKEN']")
    control = draft("control", "assert parse('plain') == 'plain'", test_file="tests/corsair/test_control.py")
    patch = frozen(control, exploit)
    run_id = f"test-{uuid.uuid4().hex[:10]}"

    failed = execute.run_probe(environment, RUNTIME, patch, "exploit", run_id=run_id, artifacts=tmp_path)
    assert failed.facts.exit_code == 1 and failed.facts.exit_class is ExitClass.TEST_FAILED
    assert failed.facts.start_marker and not failed.facts.end_marker and failed.facts.token_in_output
    assert failed.outcome is Outcome.ASSERTION_FAILED and failed.cleanup_confirmed
    assert failed.duration_s is not None and failed.output is not None and failed.patch_sha256 == patch.sha256

    passed = execute.run_probe(environment, RUNTIME, patch, "control", run_id=run_id, artifacts=tmp_path)
    assert passed.facts.exit_code == 0 and passed.facts.start_marker and passed.facts.end_marker
    assert not passed.facts.token_in_output and passed.outcome is Outcome.PASSED
    output = (tmp_path / passed.output.sha256[:2] / passed.output.sha256).read_bytes()
    assert b"1 passed" in output
    assert docker("ps", "-a", "--filter", f"label=corsair.v2.run={run_id}", "--format", "{{.Names}}").stdout == b""


@needs_docker
def test_diagnose_returns_errors_but_never_a_result(environment):
    broken = draft("exploit", "assert parse(undefined_name), os.environ['CORSAIR_TOKEN']")
    outcome, text = execute.diagnose(environment, RUNTIME, broken)
    assert outcome is Outcome.ERRORED and "NameError" in text
    skipped = ProbeDraft(role="control", test_file="tests/corsair/test_skip.py", test_name="test_skip",
                         source="import pytest\n\n\ndef test_skip():  # never reaches CORSAIR_MARKER_DIR\n"
                                "    pytest.skip('fixture missing')\n")
    outcome, text = execute.diagnose(environment, RUNTIME, skipped)
    assert outcome is Outcome.NOT_RUN and "1 skipped" in text
    failing = draft("exploit", "assert parse('<x>') == '&lt;x&gt;', os.environ['CORSAIR_TOKEN']")
    assert execute.diagnose(environment, RUNTIME, failing) == (Outcome.ASSERTION_FAILED, "")


@needs_docker
def test_timeout_is_infra_not_retried(environment, tmp_path):
    hang = draft("control", "import time; time.sleep(600)")
    patch = frozen(hang, draft("exploit", "pass"))
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
