import json
from pathlib import Path

import pytest

from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import AuditInput, InvestigationRequest, PythonRecipe
from corsair.evaluation.agents import load_frozen_fixture
from corsair.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = ROOT / "evals"

ORIGINAL_IDENTITIES = {
    "case01": (
        "7fd8a7c3036704adde08b407744e7ea1fdf428554fef21a29e73b4a14d83a4c6",
        "02275f674a11f70a0cd426d67593d3e995a9fc1af9c91d55d9a889b427069eaf",
    ),
    "audit01": (
        "d48f38dc1dbd5c13fb50f5e0abcc205ec64d8b2f7f98a19f007dd8feddd92123",
        "374257696b602b3252f2e1fb7340ecd8630e1fcf53820260d04b884bed126f4f",
    ),
    "audit02": (
        "dc8fe285edf0b8de5c0b5e0e4e6a115a6e69b6d1d6f83ce8a876991b8f39ce7f",
        "7db730fa160fd72c8613962722bd63d70ba5dec5627c5c93aefa3fe0a29c4424",
    ),
}


def _entries(dataset_name: str) -> list[dict]:
    document = json.loads((EVALS_ROOT / "datasets" / dataset_name).read_bytes())
    assert document["schema_version"] == "corsair.agent-dataset/1"
    entries = document["entries"]
    assert isinstance(entries, list)
    return entries


def _entry(entries: list[dict], case_id: str) -> dict:
    return next(entry for entry in entries if entry["case_id"] == case_id)


def test_expanded_manifests_retain_original_frozen_identities():
    producer_entries = _entries("producer-expanded.json")
    auditor_entries = _entries("auditor-expanded.json")

    assert [entry["case_id"] for entry in producer_entries] == [
        "case01",
        "producer02",
        "producer03",
    ]
    assert [entry["case_id"] for entry in auditor_entries] == [
        "audit01",
        "audit02",
        "audit03",
        "audit04",
    ]

    for entry in [*producer_entries, *auditor_entries]:
        _, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, entry)
        assert raw_input
        assert oracle

    for case_id, identities in ORIGINAL_IDENTITIES.items():
        entries = producer_entries if case_id == "case01" else auditor_entries
        entry = _entry(entries, case_id)
        assert (entry["input_digest"], entry["oracle_digest"]) == identities


@pytest.mark.parametrize(
    ("case_id", "function", "fixed_kwargs"),
    [
        ("producer02", "read_document", {"document_root": "/fixtures/allowed"}),
        (
            "producer03",
            "fetch_record",
            {"records_root": "/fixtures/allowed", "encoding": "utf-8"},
        ),
    ],
)
def test_expanded_producer_cases_are_typed_and_snapshot_frozen(
    case_id: str, function: str, fixed_kwargs: dict, tmp_path: Path
):
    entry = _entry(_entries("producer-expanded.json"), case_id)
    input_path, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, entry)
    request = InvestigationRequest.model_validate_json(raw_input)

    assert isinstance(request.case.recipe, PythonRecipe)
    assert request.case.recipe.function == function
    assert request.case.recipe.fixed_kwargs == fixed_kwargs
    assert request.case.recipe.payload_parameter not in fixed_kwargs
    assert isinstance(oracle["control_payload"], str)
    assert all(isinstance(payload, str) for payload in oracle["candidate_payloads"])
    assert oracle["control_payload"] != oracle["candidate_payloads"][0]

    snapshot = snapshot_source(
        request.case.source,
        Settings(source_root=str(input_path.parent), artifact_root=str(tmp_path)),
        ArtifactStore(tmp_path),
    )
    assert snapshot.sha256 == request.case.source.expected_digest


def test_expanded_auditor_cases_are_typed_with_external_decisions():
    expected_decisions = {"audit03": "ACCEPT", "audit04": "REJECT"}
    for case_id, expected_decision in expected_decisions.items():
        entry = _entry(_entries("auditor-expanded.json"), case_id)
        _, raw_input, oracle = load_frozen_fixture(EVALS_ROOT, entry)
        packet = AuditInput.model_validate_json(raw_input)
        input_document = json.loads(raw_input)

        assert packet.submission.control_payload != packet.submission.exploit_payload
        assert "decision" not in input_document
        assert oracle == {"decision": expected_decision}
