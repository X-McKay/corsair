"""Frozen inventory membership and oracle categories score without a model judge."""

import pytest

from corsair.contracts.intake_agent import ImageInventory
from corsair.evaluation.intake_agent import IntakeOracle, score_proposal
from tests.unit.test_intake_policy import proposal


def test_image_score_accepts_null_only_when_oracle_does():
    oracle = IntakeOracle(
        classifications=["in_scope_not_supported"],
        surfaces=["function"],
        languages=["python"],
        execution_modes=["callable"],
        required_requirements=[],
        permitted_requirements=[],
        required_reasons=["NO_COMPATIBLE_IMAGE"],
        permitted_reasons=["NO_COMPATIBLE_IMAGE"],
        images=[None],
        paths=["reader.py"],
    )
    row = score_proposal(proposal(), ImageInventory(), oracle)
    assert row["image_correct"] is True
    assert row["classification_correct"] is True
    assert row["requirements_recall"] == 1.0
    assert row["locations_recall"] == 1.0


def test_normalization_score_detects_dropped_facts_despite_correct_decision():
    oracle = IntakeOracle(
        classifications=["in_scope_not_supported"],
        surfaces=["function"],
        languages=["python"],
        execution_modes=["callable"],
        required_requirements=[],
        permitted_requirements=[],
        required_reasons=["NO_COMPATIBLE_IMAGE"],
        permitted_reasons=["NO_COMPATIBLE_IMAGE"],
        images=[None],
        paths=["reader.py"],
        issue_titles=["Traversal"],
        description_fragments=["untrusted path", "reader.py"],
    )
    candidate = proposal()
    row = score_proposal(candidate, ImageInventory(), oracle)
    assert row["classification_correct"] is True
    assert row["normalization_correct"] is False and row["pass"] is False
    candidate = candidate.model_copy(
        update={
            "issue": candidate.issue.model_copy(
                update={"title": "Traversal", "description": "Untrusted path in reader.py"}
            )
        }
    )
    assert score_proposal(candidate, ImageInventory(), oracle)["pass"] is True
    wrong_title = candidate.model_copy(
        update={"issue": candidate.issue.model_copy(update={"title": "Different issue"})}
    )
    assert score_proposal(wrong_title, ImageInventory(), oracle)["pass"] is False


def test_unresolved_case_can_have_a_null_classification_oracle():
    oracle = IntakeOracle(
        classifications=[None],
        surfaces=["unknown"],
        languages=["unknown"],
        execution_modes=["unknown"],
        required_requirements=[],
        permitted_requirements=[],
        required_reasons=["INSUFFICIENT_ISSUE_INFORMATION"],
        permitted_reasons=["INSUFFICIENT_ISSUE_INFORMATION"],
        images=[None],
        paths=[],
    )
    candidate = proposal(
        scope="unknown",
        surface="unknown",
        language="unknown",
        execution_mode="unknown",
        reason_codes=["INSUFFICIENT_ISSUE_INFORMATION"],
        locations=[],
    )
    assert score_proposal(candidate, ImageInventory(), oracle)["classification_correct"] is True


def test_location_scoring_rejects_swapped_symbols():
    oracle = IntakeOracle(
        classifications=["in_scope_not_supported"],
        surfaces=["function"],
        languages=["python"],
        execution_modes=["callable"],
        required_requirements=[],
        permitted_requirements=[],
        required_reasons=[],
        permitted_reasons=["NO_COMPATIBLE_IMAGE"],
        images=[None],
        paths=["a.py", "b.py"],
        locations=[{"path": "a.py", "symbol": "first"}, {"path": "b.py", "symbol": "second"}],
    )
    candidate = proposal(
        locations=[{"path": "a.py", "symbol": "second"}, {"path": "b.py", "symbol": "first"}]
    )
    assert score_proposal(candidate, ImageInventory(), oracle)["locations_recall"] == 0.0


def test_ambiguous_reports_can_retain_or_withhold_a_shared_grounded_path():
    oracle = IntakeOracle(
        classifications=[None],
        surfaces=["function"],
        languages=["python"],
        execution_modes=["callable"],
        required_requirements=[],
        permitted_requirements=[],
        required_reasons=["MULTIPLE_ISSUES"],
        permitted_reasons=["MULTIPLE_ISSUES"],
        images=[None],
        paths=[],
        permitted_paths=["reader.py"],
    )
    candidate = proposal(reason_codes=["MULTIPLE_ISSUES"])
    assert score_proposal(candidate, ImageInventory(), oracle)["pass"] is True
    assert (
        score_proposal(candidate.model_copy(update={"locations": []}), ImageInventory(), oracle)[
            "pass"
        ]
        is True
    )
    from corsair.contracts.intake_agent import Location

    wrong = candidate.model_copy(update={"locations": [Location(path="invented.py")]})
    assert score_proposal(wrong, ImageInventory(), oracle)["pass"] is False


def test_frozen_candidate_inputs_load_without_exposing_oracles():
    from pathlib import Path

    from corsair.evaluation.intake_agent import load_frozen_cases

    cases = load_frozen_cases(
        Path(__file__).resolve().parents[2] / "evals/datasets/intake-capabilities.json"
    )
    assert len(cases) >= 4
    assert all("oracle" not in fixture["request"]["input"] for _, fixture, _ in cases)


def test_scanner_json_cohort_has_frozen_sources_and_external_normalization_labels(tmp_path):
    from pathlib import Path

    from corsair.adapters.scm.local import snapshot_source
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import Source
    from corsair.contracts.intake_agent import IntakeRequest
    from corsair.evaluation.intake_agent import load_frozen_cases
    from corsair.settings import Settings

    root = Path(__file__).resolve().parents[2]
    cases = load_frozen_cases(root / "evals/datasets/intake-json.json")
    assert len(cases) == 32
    names = {path.parent.name for path, _, _ in cases}
    assert {"sarif", "semgrep", "bandit", "gitlab-sast", "checkov", "trivy-dependency"} <= names
    store = ArtifactStore(tmp_path)
    for path, fixture, oracle in cases:
        request = IntakeRequest.model_validate(fixture["request"])
        source = (path.parent / request.source.path).absolute()
        observed = snapshot_source(
            Source(path=str(source)), Settings(source_root=str(root)), store
        ).sha256
        assert fixture["source_digest"] == observed == request.source.expected_digest
        assert "description_fragments" not in request.input.model_dump()
        if oracle.classifications == ["in_scope_supported"]:
            assert "resolver.py" in oracle.description_fragments


async def test_live_evaluator_scores_image_compatible_supported_cases(tmp_path, monkeypatch):
    import json
    import shutil
    from pathlib import Path

    import docker

    from corsair.adapters.inference import intake_agent as adk
    from corsair.adapters.sandboxing import inspection
    from corsair.contracts.intake_agent import IntakeAgentOutput, IntakeProposal
    from corsair.evaluation.intake_agent import evaluate
    from corsair.settings import Settings
    from tests.unit.test_intake_agent import proposal_dict

    root = Path(__file__).resolve().parents[2]
    dataset = json.loads((root / "evals/datasets/intake-capabilities.json").read_bytes())
    entry = next(entry for entry in dataset["entries"] if entry["case_id"] == "python-present")
    fixture_root = tmp_path / "evals"
    target = fixture_root / "fixtures/intake-capabilities/python-present"
    shutil.copytree(root / "evals/fixtures/intake-capabilities/python-present", target)
    dataset["entries"] = [entry]
    path = fixture_root / "datasets/intake.json"
    path.parent.mkdir()
    path.write_text(json.dumps(dataset))
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(settings.model_dump_json())

    class Client:
        def close(self):
            pass

    class Inspection:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    async def output(prepared, *_args):
        value = proposal_dict()
        value.update(issue=prepared.payload, suggested_image="corsair-python:0.1", reason_codes=[])
        return IntakeAgentOutput(proposal=IntakeProposal.model_validate(value))

    monkeypatch.setattr(docker, "from_env", lambda **_kwargs: Client())
    monkeypatch.setattr(inspection, "DockerInspection", Inspection)
    monkeypatch.setattr(adk, "run_intake", output)
    report = await evaluate(path, str(settings_path), 1)
    assert report["rows"][0]["classification"] == "in_scope_supported"
    assert report["passed"] == 1


def test_summary_keeps_invalid_outputs_in_accuracy_denominator():
    from corsair.evaluation.intake_agent import summarize_rows

    summary = summarize_rows(
        [
            {
                "case": "a",
                "status": "completed",
                "classification": "in_scope_supported",
                "expected_classifications": ["in_scope_supported"],
                "classification_correct": True,
                "pass": True,
            },
            {
                "case": "b",
                "status": "OUTPUT_INVALID",
                "expected_classifications": ["in_scope_supported"],
                "pass": False,
            },
        ]
    )
    assert summary["attempts"] == 2
    assert summary["classification_accuracy"] == 0.5
    assert summary["per_class"]["in_scope_supported"]["recall"] == 0.5


def test_partial_report_preserves_unrun_attempts(tmp_path):
    from corsair.evaluation.intake_agent import write_progress

    output = tmp_path / "report.json"
    write_progress(output, [{"case": "one", "pass": True, "status": "scored"}], 2)
    import json

    report = json.loads(output.read_bytes())
    assert report["planned_attempts"] == 2
    assert report["completed_attempts"] == 1
    assert report["complete"] is False
    assert report["attempts"] == 2 and report["passed"] == 1
    assert report["rows"][1]["status"] == "not_run"


@pytest.mark.asyncio
async def test_intake_initial_report_survives_first_admission_interruption(tmp_path, monkeypatch):
    import asyncio
    import json
    from pathlib import Path

    from corsair.evaluation.intake_agent import evaluate
    from corsair.settings import Settings

    def interrupted(*_args):
        raise asyncio.CancelledError

    monkeypatch.setattr("corsair.adapters.scm.local.snapshot_source", interrupted)
    settings = tmp_path / "settings.json"
    settings.write_text(Settings(artifact_root=str(tmp_path / "artifacts")).model_dump_json())
    output = tmp_path / "report.json"
    with pytest.raises(asyncio.CancelledError):
        await evaluate(Path("evals/datasets/intake-capabilities.json"), str(settings), 1, output)
    report = json.loads(output.read_bytes())
    assert report["attempts"] == 8 and report["completed_attempts"] == 0 and not report["complete"]


def test_unsupported_model_configuration_remains_in_failure_denominator():
    from corsair.evaluation.intake_agent import summarize_rows

    row = {"case": "configured-route", "status": "MODEL_CONFIGURATION_UNSUPPORTED", "pass": False}
    summary = summarize_rows([row])
    assert summary["attempts"] == 1 and summary["passed"] == 0
    assert summary["operational_failures"] == 1
    assert summary["configuration_failures"] == 1
    assert summary["scored_attempts"] == 0


def test_summary_counts_completed_scored_rows():
    from corsair.evaluation.intake_agent import summarize_rows

    summary = summarize_rows(
        [
            {"case": "valid", "status": "completed", "classification_correct": True, "pass": True},
            {"case": "invalid", "status": "OUTPUT_INVALID"},
        ]
    )
    assert summary["scored_attempts"] == 1
    assert summary["attempts"] == 2
