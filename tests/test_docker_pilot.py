"""The kernel against real containers: the reviewed path-traversal fixture through the Docker backend.

Skipped without Docker or the pilot image (``make image``). These are the image-only tier: they prove the kernel's
mechanics on real pytest, coverage and JUnit output, not sandbox policy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case
from corsair.kernel import Fix, Gate, Kernel, Label, Outcome, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/path-traversal-fixture"
ROW = matrix.load()[0]
REFERENCE = Submission.model_validate_json((CASE / "reference-submission.json").read_text())

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
    outcomes = [(r.revision, r.role, r.outcome) for r in verdict.runs]
    assert outcomes == [("vulnerable", "control", Outcome.HOLDS), ("vulnerable", "exploit", Outcome.VIOLATED),
                        ("fixed", "control", Outcome.HOLDS), ("fixed", "exploit", Outcome.HOLDS)]
    for run in verdict.runs:
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        junit = store.get(run.junit).decode()
        assert f"test_probe[{run.role}]" in junit  # one native test id per payload
    assert verdict.runs[0].covered_lines == (4,) and verdict.runs[1].covered_lines == (4,)
    assert verdict.runs[1].exception_type == "AssertionError"
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
    assert [r.outcome for r in evaluation.runs] == [Outcome.HOLDS] * 4
    assert backend.labelled(kernel.run_id) == []


@needs_image
async def test_an_import_error_in_the_probe_is_not_run_and_a_wrong_target_fails_coverage(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                    run_id=f"c{tmp_path.name[-8:]}".lower())
    broken = REFERENCE.model_copy(update={"probe": "import nosuchmodule\n" + REFERENCE.probe})
    evaluation = await kernel.evaluate(broken)
    assert evaluation.gate.stage is Gate.CONTROL_RUN and evaluation.runs[0].outcome is Outcome.NOT_RUN
    wrong_lines = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (1,)})})
    evaluation = await kernel.evaluate(wrong_lines)
    # line 1 is the import, executed at module load, so coverage counts it; use a line that never executes instead
    never = REFERENCE.model_copy(update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (2,)})})
    evaluation = await kernel.evaluate(never)
    assert evaluation.gate.stage is Gate.CONTROL_COVERAGE
    assert backend.labelled(kernel.run_id) == []


def test_reference_submission_file_is_the_documented_shape():
    data = json.loads((CASE / "reference-submission.json").read_text())
    assert set(data) == {"hypothesis", "build_script", "probe"}


@needs_image
async def test_probes_run_unprivileged_and_cannot_edit_system_files(tmp_path):
    backend = DockerSandboxes()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept,
                    run_id=f"u{tmp_path.name[-8:]}".lower())
    hosts_probe = REFERENCE.probe.replace(
        "def run_target(payload: str) -> None:\n",
        "def run_target(payload: str) -> None:\n    with open('/etc/hosts', 'a') as handle:\n        handle.write('127.0.0.1 docs.example.com\\n')\n")
    evaluation = await kernel.evaluate(REFERENCE.model_copy(update={"probe": hosts_probe}))
    assert evaluation.gate.stage is Gate.CONTROL_RUN
    assert evaluation.runs[0].outcome is Outcome.ERRORED and evaluation.runs[0].exception_type == "PermissionError"
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
    probe = REFERENCE.probe.replace("def run_target(payload: str) -> None:\n",
                                    "def run_target(payload: str) -> None:\n    import os\n"
                                    "    assert not os.access('/work/documents.py', os.W_OK)\n")
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
