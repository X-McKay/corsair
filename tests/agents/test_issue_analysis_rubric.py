"""The coded rubric dataset is evaluator-only data with a stable, regenerable file form."""
from pathlib import Path
import tempfile

from pydantic_evals import Dataset

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput
from evals.issue_analysis.rubric import (
    DATASET_PATH, RUBRICS, SEMANTIC_CLASSES, CaseRubric, build_dataset, judge_rubric, load_dataset,
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
        # Labels classify reviewer findings; provider and evaluator classes are retained but never semantic.
        assert all(isinstance(item, str) for item in rubric.observed_failures)
    assert SEMANTIC_CLASSES <= set(CaseRubric.model_fields["observed_failures"].annotation.__args__[0].__args__)


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
