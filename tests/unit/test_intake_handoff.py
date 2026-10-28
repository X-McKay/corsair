"""Agentic intake feeds main's existing evidence runner without replacing its policies."""

from pathlib import Path

import pytest

from corsair.contracts import InvestigationRequest, Usage, digest
from corsair.contracts.intake_agent import (
    AvailableImage,
    ImageInventory,
    IntakeDecision,
    IntakeResult,
)
from corsair.entrypoints.requests import load_investigation_request
from tests.unit.test_intake_policy import proposal


def supported():
    root = Path(__file__).resolve().parents[2]
    request = load_investigation_request(root / "evals/fixtures/case01/request.json")
    image = AvailableImage(
        reference="corsair-python:0.1",
        language="python",
        execution_mode="callable",
        image_id="sha256:" + "1" * 64,
    )
    value = proposal(suggested_image=image.reference, reason_codes=[])
    value = type(value).model_validate(
        {
            **value.model_dump(),
            "issue": {
                "title": "Traversal",
                "description": "Unchecked path read",
                "locations": [{"path": "target.py"}],
            },
            "locations": [{"path": "target.py"}],
        }
    )
    from corsair.contracts import ArtifactRef

    ref = ArtifactRef(sha256="2" * 64, size=1)
    result = IntakeResult(
        run_id="intake",
        decision=IntakeDecision(
            status="completed",
            classification="in_scope_supported",
            image_check="accepted",
            image_id=image.image_id,
        ),
        proposal=value,
        inventory=ImageInventory(images=[image]),
        source=ref,
        result_artifact=ref,
        usage=Usage(llm_calls=2, tool_calls=1),
        inspection_reads=2,
    )
    return request, result


def test_main_case_binding_and_image_are_preserved_by_handoff():
    from corsair.contracts.intake_pipeline import IntakeInvestigationRequest
    from corsair.policies.intake_handoff import bind_investigation

    request, result = supported()
    intake_request = {
        "input": {"kind": "json", "payload": {"title": "Traversal"}},
        "source": request.case.source.model_dump(),
        "budget": request.budget.model_dump(),
    }
    root = IntakeInvestigationRequest(
        case_id=request.case.case_id, intake=intake_request, binding=request.case
    )
    result = result.model_copy(update={"identities": {"request": digest(root.intake)}})
    bound = bind_investigation(root, result, "intake", 600)
    assert isinstance(bound, InvestigationRequest)
    assert bound.case.recipe == request.case.recipe
    assert bound.case.finding.claim_scope == request.case.finding.claim_scope
    assert bound.case.finding.file == "target.py"
    assert bound.case.finding.title == "Traversal"
    assert bound.case.source.expected_digest == result.source.sha256
    assert bound.intake_result == result.result_artifact
    assert bound.budget.max_llm_calls == request.budget.max_llm_calls - 2
    assert bound.budget.max_tool_calls == request.budget.max_tool_calls - 3


@pytest.mark.parametrize("change", ["missing_binding", "path", "request", "image"])
def test_missing_or_substituted_binding_is_never_executed(change):
    from corsair.contracts.intake_pipeline import IntakeInvestigationRequest
    from corsair.policies.intake_handoff import bind_investigation

    request, result = supported()
    root = IntakeInvestigationRequest(
        case_id=request.case.case_id,
        intake={"input": {"kind": "json", "payload": {}}, "source": request.case.source},
        binding=request.case,
    )
    result = result.model_copy(update={"identities": {"request": digest(root.intake)}})
    if change == "missing_binding":
        root = root.model_copy(update={"binding": None})
    if change == "path":
        assert root.binding is not None
        root = root.model_copy(
            update={
                "binding": root.binding.model_copy(
                    update={
                        "finding": root.binding.finding.model_copy(update={"file": "elsewhere.py"})
                    }
                )
            }
        )
    if change == "request":
        result = result.model_copy(update={"identities": {"request": "f" * 64}})
    if change == "image":
        result = result.model_copy(
            update={
                "decision": result.decision.model_copy(update={"image_id": "sha256:" + "f" * 64})
            }
        )
    with pytest.raises(ValueError):
        bind_investigation(root, result, "intake", 600)


@pytest.mark.parametrize("kind", ["uncommitted", "config", "image", "issue", "source"])
def test_prepare_rejects_substituted_intake_receipt(tmp_path, kind, monkeypatch):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.settings import Settings
    from corsair.steps.intake_handoff import admit_intake_selection

    request, result = supported()
    settings = Settings(artifact_root=str(tmp_path))
    result = result.model_copy(update={"identities": {"config": settings.identity}})
    if kind == "config":
        result = result.model_copy(update={"identities": {"config": "f" * 64}})
    store = ArtifactStore(settings.artifact_root)
    ref = store.put_json(result.model_dump(exclude={"result_artifact"}))
    if kind != "uncommitted":
        store.commit("intake.intake", ref)
    bound = request.model_copy(
        update={
            "case": request.case.model_copy(
                update={
                    "finding": request.case.finding.model_copy(
                        update={
                            "title": result.proposal.issue.title,
                            "description": result.proposal.issue.description,
                        }
                    ),
                    "source": request.case.source.model_copy(
                        update={"expected_digest": result.source.sha256}
                    ),
                }
            ),
            "intake_result": ref,
        }
    )
    inventory = result.inventory
    if kind == "image":
        inventory = ImageInventory()
    if kind == "issue":
        bound = bound.model_copy(
            update={
                "case": bound.case.model_copy(
                    update={"finding": bound.case.finding.model_copy(update={"title": "changed"})}
                )
            }
        )
    if kind == "source":
        bound = bound.model_copy(
            update={
                "case": bound.case.model_copy(
                    update={
                        "source": bound.case.source.model_copy(update={"expected_digest": "f" * 64})
                    }
                )
            }
        )
    monkeypatch.setattr("corsair.steps.intake_handoff.discover_images", lambda _: inventory)
    with pytest.raises(ValueError):
        admit_intake_selection(bound, settings, store)
