"""Normal investigations cannot bypass intake or replace its admitted image."""

import pytest

from corsair.contracts import Source, Usage, digest
from corsair.contracts.intake import (
    ImageInventory,
    IntakeDecision,
    IntakeRequest,
    IntakeResult,
    JsonIssueInput,
)
from tests.unit.execution import round_input
from tests.unit.test_intake_policy import proposal


def supported():
    from corsair.contracts.pipeline import IssueInvestigationRequest

    item = round_input()
    request = IssueInvestigationRequest(
        case_id="reported",
        intake=IntakeRequest(
            input=JsonIssueInput(payload={"title": "Traversal"}),
            source=Source(path="repository"),
        ),
    )
    value = proposal(suggested_image=item.prepared.request.image.reference, reason_codes=[])
    return request, IntakeResult(
        run_id="root.intake",
        decision=IntakeDecision(
            status="completed",
            classification="in_scope_supported",
            image_check="accepted",
            image_id=item.prepared.request.image.image_id,
        ),
        proposal=value,
        inventory=ImageInventory(images=[item.prepared.request.image]),
        source=item.prepared.source,
        result_artifact=item.prepared.source,
        identities={"request": digest(request.intake)},
        usage=Usage(llm_calls=2, tool_calls=1),
        inspection_reads=2,
    )


@pytest.mark.parametrize(
    "decision,expected",
    [
        (IntakeDecision(status="completed", classification="out_of_scope"), "OUT_OF_SCOPE"),
        (
            IntakeDecision(status="completed", classification="in_scope_not_supported"),
            "UNSUPPORTED",
        ),
        (IntakeDecision(status="needs_input"), "NEEDS_INPUT"),
        (IntakeDecision(status="error", error_code="MODEL_FAILED"), "INTAKE_ERROR"),
    ],
)
def test_every_non_supported_intake_stops_before_execution(decision, expected):
    from corsair.policies.pipeline import intake_stop_reason

    _, intake = supported()
    assert intake_stop_reason(intake.model_copy(update={"decision": decision})) == expected


def test_supported_handoff_pins_issue_source_and_exact_inventory_image():
    from corsair.policies.pipeline import execution_from_intake, remaining_budget

    request, intake = supported()
    budget = remaining_budget(request.intake.budget, intake, 120)
    execution = execution_from_intake(request, intake, "root.intake", budget)
    assert execution.image == intake.inventory.images[0]
    assert execution.image.image_id == intake.decision.image_id
    assert execution.source.expected_digest == intake.source.sha256
    assert execution.intake_result == intake.result_artifact
    assert execution.issue == intake.proposal.issue
    assert budget.max_llm_calls == 14 and budget.max_tool_calls == 21


@pytest.mark.parametrize("kind", ["image", "issue", "request", "reference", "identity"])
def test_handoff_rejects_substituted_or_missing_provenance(kind):
    from corsair.policies.pipeline import execution_from_intake, remaining_budget

    request, intake = supported()
    budget = remaining_budget(request.intake.budget, intake, 120)
    expected_id = "root.intake"
    if kind == "image":
        intake = intake.model_copy(
            update={
                "decision": intake.decision.model_copy(update={"image_id": "sha256:" + "f" * 64})
            }
        )
    elif kind == "issue":
        intake = intake.model_copy(update={"proposal": None})
    elif kind == "request":
        intake = intake.model_copy(update={"identities": {"request": "f" * 64}})
    elif kind == "reference":
        intake = intake.model_copy(update={"result_artifact": None})
    else:
        expected_id = "another.intake"
    with pytest.raises(ValueError):
        execution_from_intake(request, intake, expected_id, budget)


@pytest.mark.parametrize("llms,tools,seconds", [(15, 0, 120), (0, 19, 120), (0, 0, 29)])
def test_root_budget_is_not_reset_between_stages(llms, tools, seconds):
    from corsair.policies.pipeline import remaining_budget

    request, intake = supported()
    intake = intake.model_copy(update={"usage": Usage(llm_calls=llms, tool_calls=tools)})
    with pytest.raises(ValueError):
        remaining_budget(request.intake.budget, intake, seconds)


@pytest.mark.parametrize("kind", ["uncommitted", "configuration", "decision_image"])
async def test_execution_preparation_rejects_untrusted_intake_provenance(
    tmp_path, monkeypatch, kind
):
    from corsair.adapters.scm.local import snapshot_source
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.execution import ExecutionStart
    from corsair.settings import Settings
    from corsair.steps.execution import ExecutionActivities

    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    source = tmp_path / "repository"
    source.mkdir()
    (source / "reader.py").write_text("def answer(): return 42\n")
    store = ArtifactStore(settings.artifact_root)
    _, intake = supported()
    intake = intake.model_copy(
        update={
            "source": snapshot_source(Source(path=str(source)), settings, store),
            "identities": {"config": settings.identity},
        }
    )
    if kind == "configuration":
        intake = intake.model_copy(update={"identities": {"config": "f" * 64}})
    if kind == "decision_image":
        intake = intake.model_copy(
            update={
                "decision": intake.decision.model_copy(update={"image_id": "sha256:" + "f" * 64})
            }
        )
    reference = store.put_json(intake.model_dump(exclude={"result_artifact"}))
    if kind != "uncommitted":
        store.commit(f"intake.{intake.run_id}", reference)
    execution = round_input().prepared.request.model_copy(
        update={
            "issue": intake.proposal.issue,
            "source": Source(path=str(source)),
            "intake_result": reference,
        }
    )
    monkeypatch.setattr("corsair.steps.execution.discover_images", lambda _: intake.inventory)
    monkeypatch.setattr("temporalio.activity.heartbeat", lambda *_: None)
    with pytest.raises(ValueError):
        await ExecutionActivities(settings, store).prepare(
            ExecutionStart(run_id="test", request=execution)
        )


async def test_normal_api_schedules_intake_parent_and_direct_api_is_explicit():
    from unittest.mock import AsyncMock

    from corsair.entrypoints.api import start_investigation
    from corsair.settings import Settings

    client = AsyncMock()
    request, _ = supported()
    await start_investigation(client, request, Settings(), run_id="parent")
    assert client.start_workflow.call_args.args[0].__qualname__ == "IssueInvestigationWorkflow.run"
    with pytest.raises(ValueError, match="start_execution"):
        await start_investigation(
            client, round_input().prepared.request, Settings(), run_id="direct"
        )


def test_normal_cli_accepts_raw_issue_inputs_and_explicit_direct_mode():
    from corsair.entrypoints.cli import parser

    raw = parser().parse_args(["investigate", "--json", "scan.json", "--source", "repository"])
    assert raw.json_input == "scan.json" and not raw.direct
    reference = parser().parse_args(
        ["investigate", "--issue", "org/repo#7", "--source", "repository"]
    )
    assert reference.issue == "org/repo#7"
    direct = parser().parse_args(["investigate", "request.json", "--direct"])
    assert direct.direct


def test_pipeline_request_loader_pins_paths_without_erasing_admission_spelling(tmp_path):
    from corsair.entrypoints.requests import load_issue_investigation_request

    request, _ = supported()
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json())
    loaded = load_issue_investigation_request(path)
    assert loaded.intake.source.path == str(tmp_path / "repository")
    unsafe = request.model_copy(
        update={
            "intake": request.intake.model_copy(update={"source": Source(path="../repository")})
        }
    )
    path.write_text(unsafe.model_dump_json())
    assert "../repository" in load_issue_investigation_request(path).intake.source.path


@pytest.mark.parametrize(
    "kind",
    [
        "valid",
        "uncommitted_intake",
        "substituted_intake",
        "uncommitted_execution",
        "substituted_execution",
    ],
)
async def test_parent_record_requires_exact_committed_children(tmp_path, kind):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.execution import ExecutionResult
    from corsair.contracts.pipeline import IssueInvestigationResult
    from corsair.steps.pipeline import PipelineActivities

    store = ArtifactStore(str(tmp_path))
    request, intake = supported()
    ref = store.put_json(intake.model_dump(exclude={"result_artifact"}))
    if kind != "uncommitted_intake":
        store.commit(f"intake.{intake.run_id}", ref)
    intake = intake.model_copy(update={"result_artifact": ref})
    child = ExecutionResult(run_id="root.execution", case_id=request.case_id, outcome="SUCCEEDED")
    execution_ref = store.put_json(child)
    if kind != "uncommitted_execution":
        store.commit(f"execution-result.{child.run_id}", execution_ref)
    result = IssueInvestigationResult(
        run_id="root",
        case_id=request.case_id,
        request_digest=digest(request),
        status="investigation_finished",
        stop_reason=None,
        intake=intake,
        execution_run_id=child.run_id,
        execution_result=execution_ref,
        execution_outcome=child.outcome,
    )
    if kind == "substituted_intake":
        result = result.model_copy(
            update={"intake": intake.model_copy(update={"usage": Usage(llm_calls=9)})}
        )
    if kind == "substituted_execution":
        result = result.model_copy(update={"execution_outcome": "FAILED"})
    activity = PipelineActivities(store)
    if kind == "valid":
        saved = await activity.record(result)
        assert saved.result_artifact == store.reconcile("issue-investigation.root")
        assert await activity.record(result) == saved
    else:
        with pytest.raises(ValueError):
            await activity.record(result)
        assert store.reconcile("issue-investigation.root") is None
