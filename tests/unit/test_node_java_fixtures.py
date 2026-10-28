import json
from pathlib import Path
from typing import TypedDict

import pytest

from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditInput,
    InvestigationRequest,
    JavaRecipe,
    JavaScriptRecipe,
    Submission,
    digest,
)
from corsair.evaluation.agents import load_frozen_fixture
from corsair.evaluation.scoring import AssessmentOracle, load_dataset
from corsair.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = ROOT / "evals"
CASE_IDS = ("node01", "node02", "java01", "java02")


class CaseSpec(TypedDict):
    recipe_type: type[JavaRecipe] | type[JavaScriptRecipe]
    module_file: str
    finding_line: int
    executed_line: str
    outcome: str
    guarded: bool


CASE_SPECS: dict[str, CaseSpec] = {
    "node01": {
        "recipe_type": JavaScriptRecipe,
        "module_file": "reader.mjs",
        "finding_line": 4,
        "executed_line": '  return readFile(`${baseRoot}/${payload}`, "utf8");',
        "outcome": "DEMONSTRATED",
        "guarded": False,
    },
    "node02": {
        "recipe_type": JavaScriptRecipe,
        "module_file": "reader.mjs",
        "finding_line": 7,
        "executed_line": '  if (relative(root, candidate).startsWith("..")) {',
        "outcome": "NOT_DEMONSTRATED",
        "guarded": True,
    },
    "java01": {
        "recipe_type": JavaRecipe,
        "module_file": "Gate.java",
        "finding_line": 7,
        "executed_line": "        return Files.readString(Path.of(baseRoot).resolve(payload));",
        "outcome": "DEMONSTRATED",
        "guarded": False,
    },
    "java02": {
        "recipe_type": JavaRecipe,
        "module_file": "Gate.java",
        "finding_line": 9,
        "executed_line": "        if (!candidate.startsWith(root)) {",
        "outcome": "NOT_DEMONSTRATED",
        "guarded": True,
    },
}


def _agent_entries(name: str) -> list[dict]:
    document = json.loads((EVALS_ROOT / "datasets" / name).read_bytes())
    assert document["schema_version"] == "corsair.agent-dataset/1"
    entries = document["entries"]
    assert isinstance(entries, list)
    assert [entry["case_id"] for entry in entries] == list(CASE_IDS)
    return entries


def _entry(entries: list[dict], case_id: str) -> dict:
    return next(entry for entry in entries if entry["case_id"] == case_id)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_node_java_producer_fixtures_are_typed_snapshot_frozen_and_line_bound(
    case_id: str, tmp_path: Path
):
    entry = _entry(_agent_entries("node-java-producer.json"), case_id)
    input_path, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, entry)
    request = InvestigationRequest.model_validate_json(raw_input)
    spec = CASE_SPECS[case_id]
    recipe = request.case.recipe

    assert digest(raw_input) == entry["input_digest"]
    assert digest((EVALS_ROOT / entry["oracle"]).read_bytes()) == entry["oracle_digest"]
    assert isinstance(recipe, (JavaScriptRecipe, JavaRecipe))
    assert type(recipe) is spec["recipe_type"]
    assert recipe.module_file == spec["module_file"]
    assert recipe.function == "read"
    assert recipe.fixed_args == ("/fixtures/allowed",)
    assert recipe.payload_index == 1
    assert recipe.public_files == {"hello.txt": "hello"}
    assert recipe.expected_control == "hello"
    assert recipe.allowed_exceptions == []
    assert request.case.finding.file == recipe.module_file
    assert request.case.finding.line == spec["finding_line"]

    source_file = input_path.parent / "source" / recipe.module_file
    source_lines = source_file.read_text().splitlines()
    assert source_lines[request.case.finding.line - 1] == spec["executed_line"]
    assert "secret" not in source_file.read_text()

    if isinstance(recipe, JavaRecipe):
        assert recipe.kind == "java.secret_disclosure/1"
        assert recipe.class_name == "Gate"
    else:
        assert recipe.kind == "javascript.secret_disclosure/1"

    snapshot = snapshot_source(
        request.case.source,
        Settings(source_root=str(input_path.parent), artifact_root=str(tmp_path / case_id)),
        ArtifactStore(tmp_path / case_id),
    )
    assert snapshot.sha256 == request.case.source.expected_digest


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_node_java_auditor_packets_have_independent_digests_and_reference_submissions(case_id: str):
    producer_entry = _entry(_agent_entries("node-java-producer.json"), case_id)
    auditor_entry = _entry(_agent_entries("node-java-auditor.json"), case_id)
    input_path, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, auditor_entry)
    packet = AuditInput.model_validate_json(raw_input)
    source_document = json.loads(raw_input)
    reference = Submission.model_validate_json((input_path.parent / "reference.json").read_bytes())
    spec = CASE_SPECS[case_id]

    assert digest(raw_input) == auditor_entry["input_digest"]
    assert producer_entry["input_digest"] != auditor_entry["input_digest"]
    assert "decision" not in source_document
    assert oracle == {"decision": "ACCEPT"}
    assert packet.submission == reference
    assert packet.submission.plan.revision == 1
    assert packet.submission.plan.parent_revision is None
    assert packet.submission.control_payload == "hello.txt"
    assert packet.submission.exploit_payload == "../private/secret.txt"
    assert isinstance(packet.recipe, (JavaScriptRecipe, JavaRecipe))
    assert packet.recipe.fixed_args == ("/fixtures/allowed",)
    assert packet.recipe.payload_index == 1
    assert packet.finding.line == spec["finding_line"]
    assert spec["executed_line"] in packet.source_excerpt

    if spec["guarded"]:
        assert "guard branch" in packet.submission.hypothesis
        assert "rather than asserting a bypass" in packet.submission.hypothesis
    else:
        assert "without a containment check" in packet.submission.hypothesis


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_node_java_assessment_oracles_are_current_versioned_candidate_expectations(case_id: str):
    dataset_path = EVALS_ROOT / "datasets" / "node-java-assessments.json"
    dataset, requests, oracles = load_dataset(dataset_path)
    requests_by_case = {request.case.case_id: request for request in requests}
    oracle = oracles[case_id]
    request = requests_by_case[case_id]
    spec = CASE_SPECS[case_id]

    assert dataset.schema_version == "corsair.dataset/1"
    assert len(dataset.entries) == len(CASE_IDS)
    assert isinstance(oracle, AssessmentOracle)
    assert oracle.schema_version == "corsair.assessment-oracle/1"
    assert [outcome.value for outcome in oracle.acceptable] == [spec["outcome"]]
    assert request.case.finding.line == spec["finding_line"]
    assert request.case.source.expected_digest

    entry = next(item for item in dataset.entries if item.case_id == case_id)
    assert entry.split == "candidate"
    assert digest((EVALS_ROOT / entry.request).read_bytes()) == entry.request_digest
    assert digest((EVALS_ROOT / entry.oracle).read_bytes()) == entry.oracle_digest
