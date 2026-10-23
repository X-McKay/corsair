"""Java and Perl use the same kernel gates and boolean-invariant contract as JavaScript."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import Case, Finding, load_case, revision
from corsair.frameworks import framework
from corsair.frameworks.javac_java import _jacoco_coverage
from corsair.kernel import Fix, Gate, Hypothesis, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]


def test_java_coverage_rejects_duplicate_package_and_source_identity(tmp_path):
    target = tmp_path / "safe/src/main/java/Documents.java"
    duplicate = tmp_path / "other/src/main/java/Documents.java"
    target.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    target.write_text("final class Documents {}\n")
    duplicate.write_text('final class Helper {\n  private static final String TEXT = """\n'
                         + r'    \"""' + '\n    package fake;\n'
                         + r'    \"""' + '\n    """;\n}\n')
    jacoco = (b'<report name="ambiguous"><package name=""><sourcefile name="Documents.java">'
              b'<line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>')

    assert _jacoco_coverage(jacoco, "safe/src/main/java/Documents.java", tmp_path) is None


def test_java_coverage_uses_unique_declared_package_identity(tmp_path):
    target = tmp_path / "app/src/main/java/org/example/Documents.java"
    target.parent.mkdir(parents=True)
    target.write_text("package org.example; final class Documents {}\n")
    jacoco = (b'<report name="unique"><package name="org/example"><sourcefile name="Documents.java">'
              b'<line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>')

    normalized = _jacoco_coverage(jacoco, "app/src/main/java/org/example/Documents.java", tmp_path)
    assert json.loads(normalized)["files"]["app/src/main/java/org/example/Documents.java"]["executed_lines"] == [1]


@pytest.mark.docker
@pytest.mark.anyio
async def test_java_kernel_rejects_coverage_merged_across_module_source_roots(tmp_path):
    image = "corsair-lite-java:dev"
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    source = tmp_path / "source"
    target = source / "safe/src/main/java/Documents.java"
    duplicate = source / "other/src/main/java/Documents.java"
    target.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    target.write_text("final class Documents {\n  static boolean reviewed(String value) { return true; }\n}\n")
    duplicate.write_text('final class Helper {\n  private static final String TEXT = """\n'
                         + r'    \"""' + '\n    package fake;\n'
                         + r'    \"""' + '\n    """;\n'
                         '  static boolean check(String value) { return !value.equals("bad"); }\n}\n')
    case = Case(case_id="fixture:ambiguous-java-source", revision=revision(source), finding=Finding(
        title="reviewed Java target", file_path="safe/src/main/java/Documents.java", symbol="Documents.reviewed"))
    submission = Submission(hypothesis=Hypothesis(
        target_file="safe/src/main/java/Documents.java", target_symbol="Documents.reviewed", target_lines=(2,),
        root_cause="A helper accepts a bad value.", expected_violation="The helper returns false."),
        build_script=("mkdir -p /work/.corsair-java/classes\n"
                      "javac -d /work/.corsair-java/classes "
                      "/work/safe/src/main/java/Documents.java /work/other/src/main/java/Documents.java"),
        probe=('public final class CorsairProbe {\n'
               '  public static final String CONTROL_PAYLOAD = "ok";\n'
               '  public static final String EXPLOIT_PAYLOAD = "bad";\n'
               '  public static boolean runTarget(String payload) { return Helper.check(payload); }\n'
               '}\n'))
    backend = DockerSandboxes()

    result = await Kernel(backend, matrix.select(case), case,
                          artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(submission)

    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.runs[0].covered_target is None
    assert result.verdict.label is Label.INCONCLUSIVE and result.verdict.rule == "K3"
    assert result.verdict.revisions[0].reason_code == "CONTROL_COVERAGE"
    assert result.verdict.reason == "control did not execute safe/src/main/java/Documents.java lines [2]"
    assert backend.labelled() == []


@pytest.mark.parametrize("adapter_name,language,probe_fragment", [
    ("javac-java", "java", "public static boolean runTarget"),
    ("perl-tap", "perl", "sub run_target"),
])
def test_adapter_registry_has_explicit_java_and_perl_contracts(adapter_name, language, probe_fragment):
    adapter = framework(adapter_name)
    case_dir = ROOT / f"cases/path-traversal-{language}"
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    assert adapter.language == language and adapter.guard(submission.probe).passed
    assert probe_fragment in submission.probe
    assert matrix.select(load_case(case_dir)).framework == adapter_name


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [
    ("java", "corsair-lite-java:dev"),
    ("perl", "corsair-lite-perl:dev"),
])
async def test_reference_submission_is_verified_in_native_runtime(tmp_path, language, image):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    result = await Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept).evaluate(submission)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict is not None
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    assert [run.result for run in result.runs] == [
        RoleResult.PASS, RoleResult.PASS, RoleResult.PASS, RoleResult.FAIL,
    ]
    for run in result.runs:
        assert run.junit_tests == 1 and run.coverage is not None and run.cleanup_confirmed
        assert run.covered_lines == submission.hypothesis.target_lines
        assert f"test_probe[{run.role}]" in store.get(run.junit).decode()
        native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
        assert native_case.find("error") is None
        assert run.exception_type is None
        if language == "perl":
            status = "ok" if run.result is RoleResult.PASS else "not ok"
            assert f"{status} 1 - test_probe[{run.role}]" in store.get(run.output).decode().splitlines()
    assert backend.labelled() == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [
    ("java", "corsair-lite-java:dev"),
    ("perl", "corsair-lite-perl:dev"),
])
async def test_probe_or_application_assertions_are_errors_in_boolean_runtimes(tmp_path, language, image):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    if language == "java":
        probe = submission.probe.replace(
            'return !"outside".equals(content);',
            'if ("outside".equals(content)) throw new AssertionError("application assertion");\n'
            '            return true;')
    else:
        probe = submission.probe.replace(
            "return $content ne 'outside';",
            "die \"application assertion\\n\" if $content eq 'outside';\n    return 1;")
    backend = DockerSandboxes()
    result = await Kernel(backend, matrix.select(case), case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(
        submission.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.EXPLOIT_RUN, result
    assert result.runs[-1].result is RoleResult.ERROR
    assert backend.labelled() == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [("java", "corsair-lite-java:dev"), ("perl", "corsair-lite-perl:dev")])
@pytest.mark.parametrize("value", ["string", "number", "object", "missing"])
async def test_native_drivers_require_boolean(tmp_path, language, image, value):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    if language == "java":
        returned = {"string": '\"true\"', "number": "1", "object": "new Object()", "missing": "null"}[value]
        probe = submission.probe.replace("static boolean runTarget", "static Object runTarget")
        probe = probe.replace('return !"outside".equals(content);', "return " + returned + ";")
    else:
        returned = {"string": "'true'", "number": "2", "object": "{}", "missing": "undef"}[value]
        probe = submission.probe.replace("return $content ne 'outside';", "return " + returned + ";")
    backend = DockerSandboxes()
    result = await Kernel(backend, matrix.select(case), case, artifacts=ArtifactStore(tmp_path / "artifacts"),
                          auditor=accept).evaluate(submission.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].exception_type == "TypeError" and result.runs[0].invariant_held is None
    assert backend.labelled() == []
