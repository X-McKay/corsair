"""The kernel against real containers: the reviewed path-traversal fixture through the Docker backend.

Skipped without Docker or the pilot image (``make image``). These are the image-only tier: they prove the kernel's
mechanics on real pytest, coverage and JUnit output, not sandbox policy.
"""
from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case, revision
from corsair.kernel import Fix, Gate, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/cs-0001-a"
ROW = matrix.load()[0]
REFERENCE = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
SCRIPT_CASE = ROOT / "cases/cs-0001-b"

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
needs_image = pytest.mark.skipif(not (docker_available() and docker("image", "inspect", ROW.image).returncode == 0),
                                 reason=f"docker or {ROW.image} unavailable (make image)")


@needs_image
async def test_reference_submission_is_verified_with_real_pytest_coverage_and_junit(tmp_path):
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=store, auditor=accept, run_id=f"t{tmp_path.name[-8:]}".lower())
    evaluation = await kernel.evaluate(REFERENCE)
    assert evaluation.gate.stage is Gate.VERIFIED, evaluation.gate
    verdict = evaluation.verdict
    assert verdict is not None and verdict.label is Label.LIKELY_EXPLOITABLE and verdict.fix is Fix.VERIFIED
    outcomes = [(r.revision, r.role, r.result) for r in verdict.runs]
    assert outcomes == [("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
                        ("fixed", "control", RoleResult.PASS), ("fixed", "exploit", RoleResult.FAIL)]
    for run in verdict.runs:
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        junit = store.get(run.junit).decode()
        assert f"test_probe[{run.role}]" in junit  # one native test id per payload
        native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
        assert native_case.find("error") is None
        assert run.exception_type is None
    assert all(run.covered_lines == REFERENCE.hypothesis.target_lines for run in verdict.runs)
    assert [run.invariant_held for run in verdict.runs] == [True, False, True, True]
    assert all(run.exception_type is None for run in verdict.runs)
    assert verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert all("outcome" not in run for run in verdict.model_dump(mode="json")["runs"])
    assert backend.labelled(kernel.run_id) == []  # nothing left behind


@needs_image
async def test_a_benign_exploit_payload_has_an_audited_negative_disposition(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                    run_id=f"b{tmp_path.name[-8:]}".lower())
    benign = REFERENCE.model_copy(update={"probe": REFERENCE.probe.replace('EXPLOIT_PAYLOAD = "../outside.txt"',
                                                                            'EXPLOIT_PAYLOAD = "document.txt"')})
    evaluation = await kernel.evaluate(benign)
    assert evaluation.gate.stage is Gate.VERIFIED and evaluation.gate.passed
    assert evaluation.verdict.label is Label.LIKELY_NOT_EXPLOITABLE and evaluation.verdict.rule == "K4"
    assert [r.result for r in evaluation.runs] == [RoleResult.PASS, RoleResult.FAIL] * 2
    assert backend.labelled(kernel.run_id) == []


@needs_image
async def test_an_import_error_is_not_run_and_a_wrong_target_fails_coverage(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                    run_id=f"c{tmp_path.name[-8:]}".lower())
    broken = REFERENCE.model_copy(update={"probe": "import nosuchmodule\n" + REFERENCE.probe})
    evaluation = await kernel.evaluate(broken)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and evaluation.runs[0].result is RoleResult.NOT_RUN
    # Repository-wide coverage can render driver-only data even when importing the probe fails.
    assert evaluation.runs[0].covered_target is False and evaluation.runs[0].covered_lines == ()
    assert evaluation.runs[0].junit_tests == 0 and evaluation.runs[0].invariant_held is None
    assert b"collection failure" in kernel.artifacts.get(evaluation.runs[0].junit)
    wrong_lines = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (1,)})})
    evaluation = await kernel.evaluate(wrong_lines)
    # line 1 is the import, executed at module load, so coverage counts it; use a line that never executes instead
    never = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (2,)})})
    evaluation = await kernel.evaluate(never)
    assert evaluation.gate.stage is Gate.CONTROL_COVERAGE
    assert backend.labelled(kernel.run_id) == []


def test_reference_submission_file_is_the_documented_shape():
    data = json.loads((CASE / "reference-submission.json").read_text())
    assert set(data) == {"contract_version", "hypothesis", "build_script", "probe"}


@needs_image
async def test_probes_run_unprivileged_and_cannot_edit_system_files(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                    run_id=f"u{tmp_path.name[-8:]}".lower())
    hosts_probe = REFERENCE.probe.replace(
        "    with tempfile.TemporaryDirectory() as root:\n",
        "    with open('/etc/hosts', 'a') as handle:\n        handle.write('127.0.0.1 docs.example.com\\n')\n    with tempfile.TemporaryDirectory() as root:\n")
    evaluation = await kernel.evaluate(REFERENCE.model_copy(update={"probe": hosts_probe}))
    assert evaluation.gate.stage is Gate.CONTROL_RUN
    assert evaluation.runs[0].result is RoleResult.ERROR and evaluation.runs[0].exception_type == "PermissionError"
    assert backend.labelled(kernel.run_id) == []


@needs_image
async def test_source_permissions_are_normalized_for_a_read_only_unprivileged_probe(tmp_path):
    import shutil
    from corsair.case import revision

    tree = tmp_path / "tree"
    shutil.copytree(load_case(CASE).revision.source, tree)
    tree.chmod(0o700)
    for path in tree.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    case = load_case(CASE).model_copy(update={"revision": revision(tree), "fixed_revision": None})
    probe = REFERENCE.probe.replace("    with tempfile.TemporaryDirectory() as root:\n",
                                    "    import os\n"
                                    "    assert not os.access('/work/documents.py', os.W_OK)\n"
                                    "    with tempfile.TemporaryDirectory() as root:\n")
    backend = DockerSandboxes()
    result = await Kernel(backend, ROW, case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(
        REFERENCE.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.VERIFIED, result


@needs_image
async def test_probe_import_cannot_redirect_or_reformat_the_driver_record(tmp_path):
    probe = ("import json, os\n"
             "os.environ['CORSAIR_ROLE'] = 'exploit'\n"
             "os.environ['CORSAIR_RESULT'] = '/tmp/corsair/forged.json'\n"
             "json.dumps = lambda value: '{\\\"outcome\\\": \\\"holds\\\"}'\n" + REFERENCE.probe)
    backend = DockerSandboxes()
    result = await Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(
        REFERENCE.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.VERIFIED, result


@needs_image
async def test_python_driver_requires_boolean(tmp_path):
    # Assertion-style probes and ignored return values must never count as Boolean evidence.
    probe = REFERENCE.probe.replace("def run_target(", "def original_target(")
    probe += "\ndef run_target(payload):\n    original_target(payload)\n"
    backend = DockerSandboxes()
    result = await Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"),
                          auditor=accept).evaluate(REFERENCE.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].exception_type == "TypeError"
    assert result.runs[0].invariant_held is None
    assert backend.labelled() == []


@needs_image
@pytest.mark.parametrize("value,error_type", [("1", "TypeError"), ('"true"', "TypeError"),
                                               ("{}", "TypeError"), ("None", "TypeError"),
                                               ("raise AssertionError('application')", "AssertionError"),
                                               ("raise ValueError('application')", "ValueError")])
async def test_python_boolean_errors(tmp_path, value, error_type):
    probe = REFERENCE.probe.replace("def run_target(", "def original_target(")
    action = value if value.startswith("raise ") else "return " + value
    probe += "\ndef run_target(payload):\n    original_target(payload)\n    " + action + "\n"
    backend = DockerSandboxes()
    result = await Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"),
                          auditor=accept).evaluate(REFERENCE.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].result is RoleResult.ERROR and result.runs[0].exception_type == error_type
    assert result.runs[0].invariant_held is None
    assert backend.labelled() == []


@needs_image
@pytest.mark.parametrize("remove_start_only", [False, True], ids=["inherited", "config-inherited"])
async def test_python_script_collects_exact_child_lines_and_verifies_fix(tmp_path, remove_start_only):
    # Dropping START alone must not lose coverage.py 7.13's inherited PROCESS_CONFIG.
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    if remove_start_only:
        probe = reference.probe.replace("import json\n", "import json\nimport os\n")
        probe = probe.replace("        completed = subprocess.run(\n",
                              "        child_env = dict(os.environ)\n"
                              "        child_env.pop('COVERAGE_PROCESS_START', None)\n"
                              "        completed = subprocess.run(\n")
        probe = probe.replace("cwd=root, check=True, capture_output=True, text=True, timeout=5,",
                              "cwd=root, check=True, capture_output=True, text=True, timeout=5, env=child_env,")
        reference = reference.model_copy(update={"probe": probe})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, ROW, load_case(SCRIPT_CASE), artifacts=store, auditor=accept,
                    run_id=f"pys{tmp_path.name[-8:]}".lower())
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [(run.revision, run.role, run.result) for run in result.runs] == [
        ("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
        ("fixed", "control", RoleResult.PASS), ("fixed", "exploit", RoleResult.FAIL),
    ]
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    for run in result.runs:
        assert run.covered_target is True and run.covered_lines == (7,)
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        report = json.loads(store.get(run.coverage))
        target = report["files"].get("cli_target.py", report["files"].get("/work/cli_target.py"))
        assert target is not None and 7 in target["executed_lines"]
        assert run.exception_type is None
    assert backend.labelled(kernel.run_id) == []


@needs_image
@pytest.mark.parametrize("seed_coverage", [False, True], ids=["clean", "seeded-shards"])
async def test_python_script_without_child_startup_is_inconclusive(tmp_path, seed_coverage):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    probe = reference.probe.replace("import json\n", "import json\nimport os\n")
    probe = probe.replace("        completed = subprocess.run(\n",
                          "        child_env = dict(os.environ)\n"
                          "        child_env.pop('COVERAGE_PROCESS_START', None)\n"
                          "        child_env.pop('COVERAGE_PROCESS_CONFIG', None)\n"
                          "        completed = subprocess.run(\n")
    probe = probe.replace("cwd=root, check=True, capture_output=True, text=True, timeout=5,",
                          "cwd=root, check=True, capture_output=True, text=True, timeout=5, env=child_env,")
    if seed_coverage:
        # Prepared images can retain genuine build-time data. It cannot prove this role's child ran.
        build_script = '''python - <<'PY'
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from coverage import CoverageData

results = Path("/tmp/corsair")
results.mkdir(exist_ok=True)
results.chmod(0o777)
with tempfile.TemporaryDirectory() as root:
    allowed = Path(root) / "allowed"
    allowed.mkdir()
    (allowed / "document.txt").write_text("seed-document")
    completed = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "--parallel-mode", "--source=/work",
         "/work/cli_target.py", "document.txt"], cwd=root, check=True, capture_output=True, text=True,
        env=dict(os.environ, COVERAGE_FILE=str(results / "coverage")),
    )
    assert json.loads(completed.stdout) == "seed-document"
shards = list(results.glob("coverage.*"))
assert shards
for shard in shards:
    data = CoverageData(basename=str(shard))
    data.read()
    assert 7 in data.lines("/work/cli_target.py")
shutil.copyfile(shards[0], results / "coverage")
# The report path is preserved by reset but must never be an input to coverage combine.
shutil.copyfile(shards[0], results / "coverage.json")
(results / "coverage.json").chmod(0o666)
for name in ("result.json", "junit.xml", "keep.txt", "coverage-not-data"):
    artifact = results / name
    artifact.write_text("prepared-marker")
    artifact.chmod(0o666)
PY
'''
        probe = probe.replace("def run_target(payload: str) -> bool:\n",
                              "def run_target(payload: str) -> bool:\n"
                              "    for name in ('result.json', 'junit.xml', 'keep.txt', 'coverage-not-data'):\n"
                              "        assert (Path('/tmp/corsair') / name).read_text() == 'prepared-marker'\n"
                              "    assert Path('/tmp/corsair/coverage.json').read_bytes().startswith(b'SQLite format 3')\n")
        reference = reference.model_copy(update={"build_script": build_script})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, ROW, load_case(SCRIPT_CASE), artifacts=store,
                    auditor=accept, run_id=f"pyn{tmp_path.name[-8:]}".lower())
    result = await kernel.evaluate(reference.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [(run.revision, run.role, run.result) for run in result.runs] == [
        ("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
    ]
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_target is False and run.covered_lines == ()
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        report = json.loads(store.get(run.coverage))
        target = report["files"].get("cli_target.py", report["files"].get("/work/cli_target.py"))
        assert target is None or target["executed_lines"] == []
    assert backend.labelled(kernel.run_id) == []


@needs_image
@pytest.mark.parametrize("run_target_child", [False, True], ids=["decoy-only", "merged-children"])
async def test_python_script_path_identity_across_multiple_children(tmp_path, run_target_child):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    tree = tmp_path / "tree"
    shutil.copytree(SCRIPT_CASE / "vulnerable", tree)
    decoy = tree / "other" / "cli_target.py"
    decoy.parent.mkdir()
    decoy.write_text((tree / "cli_target.py").read_text())
    case = load_case(SCRIPT_CASE).model_copy(update={"revision": revision(tree), "fixed_revision": None})
    # Run an identical basename at a different path first. It cannot satisfy /work/cli_target.py.
    probe = reference.probe.replace('        completed = subprocess.run(\n',
                                    '        subprocess.run(\n'
                                    '            [sys.executable, "/work/other/cli_target.py", payload],\n'
                                    '            cwd=root, check=True, capture_output=True, text=True, timeout=5,\n'
                                    '        )\n'
                                    '        completed = subprocess.run(\n')
    if not run_target_child:
        probe = probe.replace('[sys.executable, "/work/cli_target.py", payload]',
                              '[sys.executable, "/work/other/cli_target.py", payload]')
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, ROW, case, artifacts=store, auditor=accept,
                    run_id=f"pyp{tmp_path.name[-8:]}".lower())
    result = await kernel.evaluate(reference.model_copy(update={"probe": probe}))
    assert result.gate.stage is (Gate.VERIFIED if run_target_child else Gate.CONTROL_COVERAGE), result
    assert result.verdict.label is (Label.LIKELY_EXPLOITABLE if run_target_child else Label.INCONCLUSIVE)
    for run in result.runs:
        assert run.covered_lines == ((7,) if run_target_child else ())
        assert run.cleanup_confirmed is True
        report = json.loads(store.get(run.coverage))
        other = report["files"].get("other/cli_target.py", report["files"].get("/work/other/cli_target.py"))
        assert other is not None and 7 in other["executed_lines"]
    assert backend.labelled(kernel.run_id) == []
