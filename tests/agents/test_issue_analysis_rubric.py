"""The coded rubric dataset is evaluator-only data with a stable, regenerable file form."""
from pathlib import Path
import tempfile

import pytest

from pydantic_evals import Dataset

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput
from evals.issue_analysis.rubric import (
    DATASET_PATH, RUBRICS, SEMANTIC_CLASSES, AttemptLabel, CaseRubric, build_dataset, calibration_attempts,
    judge_rubric, load_attempt_labels, load_dataset,
)


def test_committed_dataset_matches_regeneration():
    with tempfile.TemporaryDirectory() as directory:
        fresh = Path(directory) / "cases.yaml"
        build_dataset().to_file(fresh, schema_path=None)
        assert fresh.read_text() == DATASET_PATH.read_text(), "run evals/issue_analysis/rubric.py to regenerate"


def test_every_case_carries_consistent_labels():
    dataset = load_dataset()
    assert {case.name for case in dataset.cases} == set(RUBRICS)
    for case in dataset.cases:
        rubric = case.metadata
        assert isinstance(rubric, CaseRubric) and isinstance(case.inputs, IssueAnalysisInput)
        if rubric.expected_status == "ready":
            assert rubric.required_conditions and case.inputs.source_files
        else:
            assert not case.inputs.source_files or rubric.expected_status == "unsupported"
        if case.expected_output is not None:
            assert isinstance(case.expected_output, IssueAnalysis)
            assert case.expected_output.status == rubric.expected_status
        assert all(isinstance(item, str) for item in rubric.reported_failure_history)
    assert SEMANTIC_CLASSES <= set(CaseRubric.model_fields["reported_failure_history"].annotation.__args__[0].__args__)


def test_judge_rubric_renders_substance_only():
    text = judge_rubric(RUBRICS["path_traversal"])
    assert text.startswith("Expected status: ready.")
    assert all(condition in text for condition in RUBRICS["path_traversal"].required_conditions)
    assert all(claim in text for claim in RUBRICS["path_traversal"].forbidden_claims)
    assert "paraphrase" in text
    abstain = judge_rubric(RUBRICS["missing_source"])
    assert "must abstain" not in abstain and "Missing facts name" in abstain


def test_task_inputs_exclude_labels():
    # The evaluation task receives case.inputs only; rubric and oracle never reach the prompt.
    case = next(case for case in load_dataset().cases if case.name == "path_traversal")
    rendered = case.inputs.model_dump_json()
    assert "required_conditions" not in rendered and "forbidden_claims" not in rendered
    assert case.expected_output is not None and case.expected_output.hypothesis is not None
    assert case.expected_output.hypothesis.observable_effect not in rendered
    assert isinstance(Dataset[IssueAnalysisInput, IssueAnalysis, CaseRubric].from_file(DATASET_PATH), Dataset)


def test_attempt_labels_identify_individual_outputs():
    # Two attempts of one case carry different reviewed labels; neither inherits the case history.
    sha, skill = "a" * 64, "c" * 64
    clean = AttemptLabel(case="path_traversal", run="r", attempt="1", outcome="typed_output", output_sha256=sha,
                         skill_sha256=skill, labels=(), reviewed_by="sol", source="review: no defect")
    defective = AttemptLabel(case="path_traversal", run="r", attempt="2", outcome="typed_output", output_sha256="b" * 64,
                             skill_sha256=skill, labels=("omitted_access_condition",), reviewed_by="root_and_sol",
                             source="review: missing read access")
    failed = AttemptLabel(case="path_traversal", run="r", attempt="3", outcome="no_output", failure_layer="provider",
                          reviewed_by="root", source="receipt: response tokens exhausted")
    unidentified = AttemptLabel(case="path_traversal", run="r", attempt="4", outcome="typed_output",
                                labels=("imprecise_api_wording",), reviewed_by="root", source="report sentence")
    # An output hash alone does not identify the producing skill, so the entry stays excluded.
    skill_unknown = AttemptLabel(case="path_traversal", run="r", attempt="5", outcome="typed_output",
                                 output_sha256="d" * 64, labels=(), reviewed_by="root", source="review")
    assert clean.labels != defective.labels
    assert RUBRICS["path_traversal"].reported_failure_history and not clean.labels
    assert calibration_attempts((clean, defective, failed, unidentified, skill_unknown)) == (clean, defective)
    assert not skill_unknown.calibration_ready and not unidentified.calibration_ready
    with pytest.raises(ValueError):
        AttemptLabel(case="c", run="r", attempt="6", outcome="no_output", labels=("omitted_access_condition",),
                     reviewed_by="root", source="x")
    with pytest.raises(ValueError):
        AttemptLabel(case="c", run="r", attempt="7", outcome="typed_output", output_sha256=sha, skill_sha256=skill,
                     labels=("response_truncation",), reviewed_by="root", source="x")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "labels.yaml"
        path.write_text("- {case: c, run: r, attempt: '1', outcome: no_output, failure_layer: provider, reviewed_by: root, source: s}\n"
                        "- {case: c, run: r, attempt: '1', outcome: no_output, failure_layer: provider, reviewed_by: root, source: s}\n")
        with pytest.raises(ValueError):
            load_attempt_labels(path)


def test_committed_attempt_labels_load_and_name_dataset_cases():
    labels = load_attempt_labels()
    names = {case.name for case in load_dataset().cases}
    assert labels and all(item.case in names for item in labels)
    # Published findings lack output and skill identity until coded from private copies: none is calibration-ready yet.
    assert calibration_attempts(labels) == ()
