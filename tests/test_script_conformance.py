"""Deterministic qualification for reviewed repository-local script, CLI and main entrypoints."""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case, load_oracle
from corsair.frameworks.javac_java import _jacoco_coverage
from corsair.kernel import Fix, Gate, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CASE_NAMES = ("cases/cs-0001-b", "cases/cs-0002-b", "cases/cs-0003-b", "cases/cs-0004-b")
EXPECTED_LANGUAGES = {
    "cases/cs-0001-b": "python",
    "cases/cs-0002-b": "javascript",
    "cases/cs-0003-b": "java",
    "cases/cs-0004-b": "perl",
}


def select_script_cases(raw: str | None) -> tuple[Path, ...]:
    names = tuple((raw or " ".join(SCRIPT_CASE_NAMES)).split())
    if names != SCRIPT_CASE_NAMES:
        raise ValueError("SCRIPT_CASES must name each reviewed script case exactly once in its documented order: "
                         + " ".join(SCRIPT_CASE_NAMES))
    paths = tuple(ROOT / name for name in names)
    if any(not path.is_dir() for path in paths):
        raise ValueError("every SCRIPT_CASES entry must be an existing reviewed case directory")
    return paths


SELECTED_CASES = select_script_cases(os.environ.get("SCRIPT_CASES"))
REQUIRE_GATE = os.environ.get("CORSAIR_REQUIRE_SCRIPT_GATE") == "1"


@pytest.mark.parametrize("raw", [
    "cases/cs-0001-b cases/cs-0002-b cases/cs-0003-b",
    "cases/cs-0001-b cases/cs-0002-b cases/cs-0003-b cases/cs-0003-b",
    "cases/cs-0001-b cases/cs-0002-b cases/cs-0003-b cases/unknown",
    "cases/cs-0002-b cases/cs-0001-b cases/cs-0003-b cases/cs-0004-b",
])
def test_script_case_selection_rejects_missing_duplicate_extra_or_reordered_cases(raw):
    with pytest.raises(ValueError, match="each reviewed script case exactly once"):
        select_script_cases(raw)


class ObservedScriptDocker(DockerSandboxes):
    def __init__(self):
        super().__init__()
        self.probe_containers = []

    def open_environment(self, image, workdir, sandbox_labels):
        name = super().open_environment(image, workdir, sandbox_labels)
        self.probe_containers.append((name, sandbox_labels["corsair.lite.revision"],
                                      sandbox_labels["corsair.lite.role"]))
        return name


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("case_path", SELECTED_CASES, ids=lambda path: path.name)
async def test_reviewed_script_reference_is_decisive_with_exact_child_coverage(tmp_path, case_path):
    case = load_case(case_path)
    row = matrix.select(case)
    assert row is not None and row.language == EXPECTED_LANGUAGES[str(case_path.relative_to(ROOT))]
    available = docker_available() and docker("image", "inspect", row.image).returncode == 0
    if not available and REQUIRE_GATE:
        pytest.fail(f"required script gate cannot inspect {row.image}; run make image")
    if not available:
        pytest.skip(f"docker or {row.image} unavailable (make image)")

    submission_data = json.loads((case_path / "reference-submission.json").read_text())
    assert submission_data["contract_version"] == "corsair-lite/differential-probe/2"
    submission = Submission.model_validate(submission_data)
    backend = ObservedScriptDocker()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, row, case, artifacts=store, auditor=accept,
                    run_id=f"s{case_path.name[-2:]}{tmp_path.name[-6:]}".lower())

    evaluation = await kernel.evaluate(submission)

    assert evaluation.gate == evaluation.gate.model_copy(update={"passed": True, "stage": Gate.VERIFIED})
    verdict = evaluation.verdict
    assert verdict is not None and verdict.label is Label.LIKELY_EXPLOITABLE and verdict.fix is Fix.VERIFIED
    assert verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [(run.revision, run.role, run.result) for run in verdict.runs] == [
        ("vulnerable", "control", RoleResult.PASS),
        ("vulnerable", "exploit", RoleResult.PASS),
        ("fixed", "control", RoleResult.PASS),
        ("fixed", "exploit", RoleResult.FAIL),
    ]
    assert [run.invariant_held for run in verdict.runs] == [True, False, True, True]
    assert [(revision, role) for _, revision, role in backend.probe_containers] == [
        ("vulnerable", "control"), ("vulnerable", "exploit"),
        ("fixed", "control"), ("fixed", "exploit"),
    ]
    assert len({name for name, _, _ in backend.probe_containers}) == 4

    for run in verdict.runs:
        assert run.exception_type is None and run.junit_tests == 1 and run.cleanup_confirmed is True
        assert run.covered_target is True and run.covered_lines == submission.hypothesis.target_lines
        native = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert native.get("name") == f"test_probe[{run.role}]"
        assert native.find("error") is None
        assert (native.find("failure") is None) == (run.result is RoleResult.PASS)

        coverage = store.get(run.coverage)
        if row.language == "java":
            source = case.revision if run.revision == "vulnerable" else case.fixed_revision
            coverage = _jacoco_coverage(coverage, submission.hypothesis.target_file, Path(source.source))
        report = json.loads(coverage)
        target = submission.hypothesis.target_file
        target_report = report["files"].get(target) or report["files"].get("/work/" + target)
        assert target_report is not None
        assert set(submission.hypothesis.target_lines) <= set(target_report["executed_lines"])

    oracle = load_oracle(case_path)
    assert oracle["expected_label"] == verdict.label
    assert oracle["expected_fix"] == verdict.fix
    assert backend.labelled(kernel.run_id) == []
