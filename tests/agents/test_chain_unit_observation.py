"""Shared direct composition accepts reviewed unit properties without requesting probes."""

import asyncio
from dataclasses import replace

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from corsair.agents.source.contracts import SourceFile
from corsair.composition.direct import CapturedReviewSource, run_direct
from evals.fixture_e2e.case import (
    CASES, FIXTURE, INVENTORY, fixture_case, reference_plan, reviewed_runners, scripted_authoring,
    scripted_identification,
)
from tests.agents.test_fixture_composition import stages, store


def unit_planner():
    draft = reference_plan()
    for role in ("control", "security"):
        draft[role].pop("witness")
        draft[role]["observation"] = {
            "kind": "return_value" if role == "control" else "exception",
            "property": "Ordinary document contents" if role == "control" else "ValueError rejects traversal",
            "seam": "Existing read_document function interface",
        }
    async def respond(messages, info):
        done = sum(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        if done < 2:
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": ("documents.py", "test_existing.py")[done]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"plan": draft})])
    return FunctionModel(respond)


def unit_assessor(seen, candidate=True, fix_applicable=True):
    async def respond(messages, info):
        prompt = next(p.content for m in messages for p in m.parts if p.part_kind == "user-prompt")
        items = [m.groupdict() for m in INVENTORY.finditer(prompt)]
        pre_execution = prompt.startswith("Pre-execution")
        if pre_execution:
            seen[:] = items
        reads = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
                 and p.tool_name == "read_evidence"]
        for item in items:
            end = max((read.end_line for read in reads if read.item_id == item['item']), default=0)
            if end < int(item['lines']):
                return ModelResponse(parts=[ToolCallPart("read_evidence", {
                    "item_id": item['item'], "start_line": end + 1})])
        def cite(item):
            return {"item_id": item["item"], "start_line": 1, "end_line": min(80, int(item["lines"]))}
        def reviews(revision):
            selected = [i for i in items if i["kind"] in ("patch", "plan") or (i["kind"] == "source" and i["revision"] == revision)]
            return {"revision": revision, "source_linked": True, "condition_exercised": True,
                    "assertions_relevant": True, "dependency_scope_valid": True,
                    "rationale": {"statement": "Frozen tests call the saved implementation and assert the reported property", "citations": [cite(i) for i in selected]}}
        receipts = [cite(i) for i in items if i["kind"] == "receipt"]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "execution": "unknown" if pre_execution else "completed", "finding": "inconclusive" if pre_execution else "reproduced", "fix": "not_applicable" if pre_execution else (("verified" if candidate else "not_verified") if fix_applicable else "not_applicable"),
            "application_observations": [], "sandbox_observations": [],
            "interpretation": {"statement": "Planned assertion fails on baseline and passes on candidate", "citations": [cite(items[0])] if pre_execution else receipts},
            "limitations": ["Only the reviewed component property is established"],
            "validity_reviews": [reviews(r) for r in (("baseline", "candidate") if candidate else ("baseline",))] if pre_execution else [],
        })])
    return FunctionModel(respond)


@pytest.mark.parametrize("candidate_source", ["present", "missing", "wrong_identity", "no_candidate"])
def test_composition_uses_independent_unit_reviews_for_final_gate(store, tmp_path, candidate_source):
    case = fixture_case()
    if candidate_source == "no_candidate":
        case = replace(case, revision_sources={"baseline": case.revision_sources["baseline"]})
    sources = {"baseline": CapturedReviewSource(case.revision_sources["baseline"], case.issue.source_files)}
    if candidate_source not in ("missing", "no_candidate"):
        sources["candidate"] = CapturedReviewSource(
            case.revision_sources["candidate"] if candidate_source == "present" else "0" * 64,
            (SourceFile(path="documents.py", content=(FIXTURE / CASES["exploitable"]["candidate"] / "documents.py").read_text()),))
    candidate_available = candidate_source == "present"
    case = replace(case, review_sources=sources)
    seen, requested = [], []
    (tmp_path / "work").mkdir()
    runners = reviewed_runners(store, tmp_path / "work")
    class CheckingRunner:
        def __init__(self, runner, purpose):
            self.runner, self.purpose = runner, purpose
        def run(self, patch, *, witness=None, **kwargs):
            if self.purpose != "development":
                assert seen, "Frozen execution cannot precede the validity review"
                assert all(i["kind"] in ("plan", "source", "patch") for i in seen)
            requested.append(witness)
            return self.runner.run(patch, witness=witness, **kwargs)
    with models.override_allow_model_requests(False):
        result = asyncio.run(run_direct(case, stages(planning=unit_planner(), assessment=unit_assessor(seen, candidate_available, candidate_source != "no_candidate")),
                                        lambda purpose: CheckingRunner(runners(purpose), purpose)))
    assert result.reason == "complete", result.reason
    assert requested and all(w is None for w in requested)
    assert result.observation_plan.observation_mode == "unit_test"
    assert all(e.observed.patch_sha256 == result.patch.patch_sha256 for e in result.executions)
    assert result.validity_review.evidence is None
    assert result.validity_review.gate_result is None
    assert result.gate == result.assessment.gate_result
    assert result.gate.permitted.finding == "reproduced"
    assert result.gate.permitted.fix == ("not_applicable" if candidate_source == "no_candidate" else
                                         "verified" if candidate_available else "not_verified")
    assert len(result.assessment.validity_reviews) == (2 if candidate_available else 1)
    assert {i["revision"] for i in seen if i["kind"] == "source"} == ({"baseline", "candidate"} if candidate_available else {"baseline"})
    assert result.assessment.evidence.baseline[0].test_validity is not None
    if candidate_source == "no_candidate":
        assert not result.assessment.evidence.candidate
        assert len(result.executions) == 1
    else:
        assert (result.assessment.evidence.candidate[0].test_validity is not None) == candidate_available


def test_captured_review_sources_roundtrip_in_durable_chain_request():
    from pydantic import TypeAdapter
    from corsair.composition.direct import CompositionBudget
    from corsair.workflows.chain_runtime import ChainRequest, StageKeys
    case = fixture_case()
    case = replace(case, review_sources={"baseline": CapturedReviewSource(
        case.revision_sources["baseline"], case.issue.source_files)})
    request = ChainRequest(case, StageKeys("a", "b", "c", "d"), CompositionBudget())
    adapter = TypeAdapter(ChainRequest)
    restored = adapter.validate_json(adapter.dump_json(request))
    assert restored == request
    assert restored.case.review_sources["baseline"].files == case.issue.source_files
