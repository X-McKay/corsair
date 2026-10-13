"""Corpus campaign input separation and interrupted/failed dispatch accounting; no live execution."""
import json
from pathlib import Path

import pytest

from evals.corpus import campaign, cases
from corsair.investigation.request import IssueRequest


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    provider = tmp_path / "provider.json"
    image_file = tmp_path / "images.json"
    provider.write_text("{}")
    image_file.write_text(json.dumps({"python": "sha256:" + "a" * 64}))
    monkeypatch.setattr(campaign, "identity", lambda *a: {"frozen": True})
    monkeypatch.setattr(campaign, "load_inference", lambda p: object())
    directory = tmp_path / "campaign"
    manifest = campaign.prepare(directory, ["ih-python-pathtraversal"], provider, image_file)
    return directory, manifest, provider, image_file


def test_development_selection_never_opens_other_case_trees(monkeypatch):
    snapshot = cases.snapshot
    opened = []
    def selected_only(path):
        opened.append(path)
        assert path.parent.name == "pathtraversal"
        return snapshot(path)
    monkeypatch.setattr(cases, "snapshot", selected_only)
    loaded = cases.load(split="development", language="python", case_ids={"ih-python-pathtraversal"})
    assert len(loaded) == 1 and len(opened) == 2
    assert loaded[0].split == "development"


def test_requests_are_neutral_and_negative_has_no_candidate(prepared):
    directory, manifest, _, _ = prepared
    assert len(manifest["slots"]) == 2
    positive, negative = manifest["slots"]
    first = IssueRequest.model_validate_json(Path(positive["issue"]).read_bytes())
    second = IssueRequest.model_validate_json(Path(negative["issue"]).read_bytes())
    assert first.fixed_revision == second.revision and second.fixed_revision is None
    for request in (first, second):
        assert "pathtraversal" not in request.repository
        assert "negative" not in request.repository and "positive" not in request.repository
        assert not cases.label_words(request.issue_text())
    assert negative["expected"] == {"execution": "completed", "finding": "not_reproduced", "fix": "not_applicable"}
    assert json.loads((directory / "summary.json").read_text())["status"] == {"planned": 2}


def test_failures_remain_in_denominator_and_are_not_retried(prepared):
    directory, _, provider, image_file = prepared
    calls = []
    def fails(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("dispatch lost")
    result = campaign.run(directory, provider, image_file, slots=1, dispatcher=fails)
    assert result["planned"] == 2 and result["status"] == {"failed": 1, "planned": 1}
    campaign.run(directory, provider, image_file, slots=1, dispatcher=fails)
    assert len(calls) == 1  # Unresolved dispatch ownership blocks all later slots as well.
    assert campaign.report(directory)["status"] == {"failed": 1, "planned": 1}
    assert (directory / "attempt-0001-error.txt").is_file()


def test_started_unknown_slot_is_never_blindly_dispatched(prepared):
    directory, _, provider, image_file = prepared
    campaign._write(directory / "attempt-0001.json", {"id": "attempt-0001", "status": "started"})
    calls = []
    def fails(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("next slot")
    result = campaign.run(directory, provider, image_file, slots=1, dispatcher=fails)
    assert len(calls) == 0 and result["status"] == {"unknown": 1, "planned": 1}
    assert result["outcomes_by_direction"]["positive_pair"] == {"unknown": 1}


def test_reconciliation_uses_final_record_but_cannot_score_gate_ceiling(prepared):
    directory, manifest, provider, image_file = prepared
    slot = manifest["slots"][0]
    evidence = directory / slot["id"] / "investigation"
    evidence.mkdir(parents=True)
    (evidence / "request.json").write_bytes(Path(slot["issue"]).read_bytes())
    item = {"label": "INCONCLUSIVE", "label_basis": "gate_assessment_rejected", "selected": None,
            "reached": "complete", "final": slot["expected"], "stopped_at": None, "cleanup": {"baseline": "confirmed"}}
    (evidence / "record.json").write_text(json.dumps(item))
    campaign._write(directory / "attempt-0001.json", {"id": "attempt-0001", "status": "started"})
    def refuses(*args, **kwargs):
        raise RuntimeError("second slot")
    result = campaign.run(directory, provider, image_file, slots=1, dispatcher=refuses)
    attempt = json.loads((directory / "attempt-0001.json").read_text())
    assert attempt["status"] == "completed" and attempt["matches_expected_final"] is None
    assert result["status"] == {"completed": 1, "failed": 1}


def test_changed_frozen_identity_blocks_dispatch(prepared, monkeypatch):
    directory, _, provider, image_file = prepared
    monkeypatch.setattr(campaign, "identity", lambda *a: {"frozen": False})
    with pytest.raises(ValueError, match="frozen campaign"):
        campaign.run(directory, provider, image_file, slots=1)


def test_dataset_digest_is_stable_across_neutral_materialization_roots(prepared):
    directory, manifest, provider, image_file = prepared
    other = campaign.prepare(directory.with_name("other"), ["ih-python-pathtraversal"], provider, image_file)
    assert manifest["dataset_sha256"] == other["dataset_sha256"]
    assert manifest["slots"][0]["issue_sha256"] != other["slots"][0]["issue_sha256"]


def test_mutated_issue_cannot_ground_a_started_record(prepared):
    directory, manifest, provider, image_file = prepared
    slot = manifest["slots"][0]
    evidence = directory / slot["id"] / "investigation"
    evidence.mkdir(parents=True)
    request = json.loads(Path(slot["issue"]).read_text())
    request["issue"]["title"] = "Changed report"
    Path(slot["issue"]).write_text(json.dumps(request))
    (evidence / "request.json").write_text(json.dumps(request))
    (evidence / "record.json").write_text(json.dumps({"label": "LIKELY_EXPLOITABLE"}))
    campaign._write(directory / "attempt-0001.json", {"id": "attempt-0001", "status": "started"})
    def refuses(*args, **kwargs):
        raise RuntimeError("second slot")
    result = campaign.run(directory, provider, image_file, slots=1, dispatcher=refuses)
    assert result["status"] == {"unknown": 1, "planned": 1}


def test_default_token_zeros_are_unknown_and_nonzero_values_remain_partial(prepared):
    directory, _, _, _ = prepared
    campaign._write(directory / "attempt-0001.json", {"id": "attempt-0001", "status": "completed",
                    "record": {"label": "INCONCLUSIVE", "reached": "planning", "selected": None,
                               "usage": {"0-identification": {"input_tokens": 0, "output_tokens": 7, "requests": 1}}}})
    metrics = campaign.report(directory)["observed_efficiency"]
    assert metrics["input_tokens"]["total"] is None and metrics["input_tokens"]["partial_nonzero_total"] is None
    assert metrics["output_tokens"]["total"] is None and metrics["output_tokens"]["partial_nonzero_total"] == 7


def test_second_dispatcher_cannot_overlap_the_same_campaign(prepared):
    directory, _, provider, image_file = prepared
    calls = []
    def first(*args, **kwargs):
        def second(*args, **kwargs):
            calls.append("second")
        with pytest.raises(ValueError, match="active dispatcher"):
            campaign.run(directory, provider, image_file, slots=1, dispatcher=second)
        raise RuntimeError("first failure retained")
    campaign.run(directory, provider, image_file, slots=1, dispatcher=first)
    assert not calls


def test_unconfirmed_cleanup_stops_later_planned_slots(prepared):
    directory, _, provider, image_file = prepared
    calls = []
    def unconfirmed(*args, **kwargs):
        calls.append(args)
        return {"label": "ERROR", "reached": "execution", "selected": {"language": "python"},
                "cleanup": {"baseline": "unconfirmed"}, "final": None}
    result = campaign.run(directory, provider, image_file, slots=2, dispatcher=unconfirmed)
    assert len(calls) == 1 and result["status"] == {"completed": 1, "planned": 1}


def test_known_admission_refusal_does_not_block_later_slots(prepared):
    directory, _, provider, image_file = prepared
    calls = []
    def refused(*args, **kwargs):
        calls.append(args)
        return {"label": "UNABLE_TO_RUN", "reached": "admission", "selected": None,
                "cleanup": {}, "final": None, "crashed": False}
    result = campaign.run(directory, provider, image_file, slots=2, dispatcher=refused)
    assert len(calls) == 2 and result["status"] == {"completed": 2}


def test_relative_campaign_directory_dispatches_an_absolute_evidence_root(prepared, monkeypatch):
    directory, _, provider, image_file = prepared
    monkeypatch.chdir(directory.parent)
    def inspect_root(request, evidence, prepared_images, **kwargs):
        assert evidence.is_absolute() and evidence.is_relative_to(directory)
        return {"label": "UNABLE_TO_RUN", "reached": "admission", "selected": None, "crashed": False, "cleanup": {}}
    campaign.run(Path(directory.name), provider, image_file, slots=1, dispatcher=inspect_root)
