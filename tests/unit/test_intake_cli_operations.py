"""Operator views and recovery for the actual intake result contracts."""

import json

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts.intake_agent import IntakeDecision, IntakeProposal, IntakeResult, Issue
from corsair.contracts.intake_pipeline import IntakeInvestigationResult
from corsair.entrypoints.cli import execute, parser
from corsair.entrypoints.runs import list_runs
from corsair.entrypoints.terminal import Terminal
from corsair.settings import Settings


def stopped_parent():
    intake = IntakeResult(
        run_id="operator.intake",
        decision=IntakeDecision(
            status="completed",
            classification="out_of_scope",
            reason_codes=["OUTSIDE_SCOPE_POLICY"],
        ),
        proposal=IntakeProposal(
            issue=Issue(title="MODEL_SENTINEL", description="PRIVATE_DESCRIPTION"),
            scope="out_of_scope",
            surface="unknown",
            language="unknown",
            execution_mode="unknown",
            requirements=[],
            locations=[],
            reason_codes=["OUTSIDE_SCOPE_POLICY"],
        ),
    )
    return IntakeInvestigationResult(
        run_id="operator",
        case_id="case",
        status="stopped",
        stop_reason="OUT_OF_SCOPE",
        intake=intake,
    )


@pytest.mark.parametrize("parent", [False, True])
@pytest.mark.parametrize("as_dict", [False, True])
def test_human_intake_views_omit_model_text_and_explain_stop(capsys, parent, as_dict):
    result = stopped_parent()
    terminal = Terminal(parser().parse_args(["inspect", "operator", "--format", "human"]))
    shown = result if parent else result.intake
    terminal.emit(shown.model_dump(mode="json") if as_dict else shown)
    output = capsys.readouterr().out
    assert "MODEL_SENTINEL" not in output and "PRIVATE_DESCRIPTION" not in output
    assert "outside" in output.lower() and "scope" in output.lower()
    assert "Native receipt" not in output


def test_runs_lists_stopped_intake_parent_with_filter_and_identity(tmp_path):
    store = ArtifactStore(tmp_path)
    parent = stopped_parent()
    store.commit("intake-investigation.operator", store.put_json(parent))
    rows = list_runs(store, case_id="case", limit=1)["runs"]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "operator"
    assert rows[0]["stop_reason"] == "OUT_OF_SCOPE"
    assert rows[0]["investigation_run_id"] is None
    assert list_runs(store, case_id="another")["runs"] == []


@pytest.mark.parametrize(
    "arguments", [["inspect", "operator", "--explain"], ["explain", "operator"]]
)
async def test_parent_explanation_is_available_without_a_child(tmp_path, capsys, arguments):
    settings = Settings(artifact_root=str(tmp_path / "artifacts"))
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(settings.model_dump_json())
    store = ArtifactStore(settings.artifact_root)
    store.commit("intake-investigation.operator", store.put_json(stopped_parent()))
    code = await execute(
        parser().parse_args([*arguments, "--settings", str(settings_path), "--format", "json"])
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["stop_reason"] == "OUT_OF_SCOPE"
    assert result["explanation"] and result["next_step"]
    assert "MODEL_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize(
    "arguments",
    [
        ["investigate", "missing.json", "--source", "source"],
        ["investigate", "missing.json", "--json", "issue.json", "--source", "source"],
    ],
)
async def test_conflicting_source_is_rejected_before_opening_request(arguments):
    with pytest.raises(ValueError, match="source.*binding|binding.*source"):
        await execute(parser().parse_args(arguments))


@pytest.mark.parametrize("reference", ["abc", "owner/repo", "owner/repo#abc", "repo#1"])
def test_invalid_issue_reference_has_actionable_format_error(reference):
    from corsair.entrypoints.requests import parse_issue_reference

    with pytest.raises(ValueError, match="OWNER/REPO#NUMBER"):
        parse_issue_reference(reference, [])


async def test_intake_requires_source_before_reading_json():
    with pytest.raises(ValueError, match="--source"):
        await execute(parser().parse_args(["investigate", "--json", "missing.json"]))


def test_older_receipt_without_diagnostics_still_decodes():
    from corsair.contracts import IntakeDiagnostics

    intake = stopped_parent().intake
    assert intake is not None
    value = intake.model_dump(exclude={"diagnostics"})
    assert IntakeResult.model_validate(value).diagnostics == IntakeDiagnostics()


def test_parent_lookup_rejects_a_result_committed_under_another_identity(tmp_path):
    from corsair.entrypoints.runs import load_intake_parent

    store = ArtifactStore(tmp_path)
    store.commit("intake-investigation.wrong", store.put_json(stopped_parent()))
    with pytest.raises(ValueError, match="identity"):
        load_intake_parent(store, "wrong")
    assert list_runs(store) == {"runs": [], "invalid_records": 1}


def test_human_selected_image_uses_selected_reference_when_two_tags_share_an_id(capsys):
    from corsair.contracts.intake_agent import AvailableImage, ImageInventory

    image = AvailableImage(
        reference="first:1",
        image_id="sha256:" + "a" * 64,
        language="python",
        execution_mode="callable",
    )
    intake = stopped_parent().intake
    assert intake is not None and intake.proposal is not None
    intake = intake.model_copy(
        update={
            "inventory": ImageInventory(
                images=[image, image.model_copy(update={"reference": "selected:1"})]
            ),
            "proposal": intake.proposal.model_copy(update={"suggested_image": "selected:1"}),
            "decision": IntakeDecision(
                status="completed",
                classification="in_scope_supported",
                image_id=image.image_id,
                image_check="accepted",
            ),
        }
    )
    Terminal(parser().parse_args(["inspect", "operator", "--format", "human"])).emit(intake)
    output = capsys.readouterr().out
    assert "selected:1" in output and "first:1" not in output
