"""Operator-facing progress, terminal lifecycle and compact result contracts."""

import asyncio
import io
import json
from unittest.mock import AsyncMock, Mock

import pytest
from rich.console import Console

from corsair.adapters.temporal import client as temporal_client
from corsair.contracts import Disposition, ExecutionStatus, InvestigationResult, Verdict
from corsair.entrypoints import terminal as terminal_module
from corsair.entrypoints.cli import parser
from corsair.entrypoints.terminal import Terminal
from tests.unit.test_intake_cli_operations import stopped_parent
from tests.unit.test_terminal import _demonstrated_result, _manifest


def terminal(*options, width=80):
    ui = Terminal(parser().parse_args(["inspect", "run1", "--format", "human", *options]))
    ui.out = Console(file=io.StringIO(), width=width, color_system=None, record=True)
    ui.err = Console(file=io.StringIO(), width=width, color_system=None, record=True)
    return ui


@pytest.mark.parametrize("child_available", [True, False])
async def test_parent_progress_observes_child_without_losing_selected_image(child_available):
    async def parent_query(*args, **kwargs):
        del args, kwargs
        return {
            "phase": "investigation",
            "investigation_run_id": "child",
            "image_reference": "runtime:1",
            "image_id": "sha256:" + "a" * 64,
            "started": "2026-10-29T12:00:00+00:00",
        }

    async def child_query(*args, **kwargs):
        del args, kwargs
        if not child_available:
            raise RuntimeError("PRIVATE_QUERY_ERROR")
        return {
            "phase": "audit",
            "session": 2,
            "round": 3,
            "max_rounds": 4,
            "started": "2026-10-29T12:01:00+00:00",
            "private": "MODEL_TEXT",
        }

    client = Mock()
    client.get_workflow_handle.return_value.query = child_query
    result = await temporal_client.query_intake_progress(client, Mock(query=parent_query))
    assert result["phase"] == ("audit" if child_available else "investigation")
    assert result["image_reference"] == "runtime:1"
    assert result["started"] == "2026-10-29T12:00:00+00:00"
    assert result.get("child_status_unavailable", False) is (not child_available)
    assert "MODEL_TEXT" not in json.dumps(result) and "PRIVATE_QUERY_ERROR" not in json.dumps(
        result
    )
    if child_available:
        assert result["session"] == 2 and result["round"] == 3


@pytest.mark.parametrize("value,label", [(stopped_parent(), "Stopped"), (42, "Completed")])
async def test_wait_finishes_with_a_static_observed_outcome(value, label, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.001)
    ui = terminal("--no-animation")
    result = await ui.wait(
        asyncio.sleep(0, result=value),
        "Run",
        query=lambda: asyncio.sleep(0, result={"phase": "intake"}),
    )
    assert result == value
    assert label in ui.err.export_text()


async def test_failed_wait_renders_failure_without_exception_body():
    ui = terminal("--no-animation")

    async def fail():
        raise RuntimeError("PRIVATE_ERROR")

    with pytest.raises(RuntimeError):
        await ui.wait(fail(), "Run", run_id="run1")
    output = ui.err.export_text()
    assert "Failed" in output and "PRIVATE_ERROR" not in output


async def test_detaching_wait_prints_reconnect_command_and_preserves_cancellation():
    ui = terminal("--no-animation", "--settings", "/tmp/custom settings.json")
    ready = asyncio.Event()

    async def pending():
        ready.set()
        await asyncio.Event().wait()

    waiting = asyncio.create_task(ui.wait(pending(), "Run", run_id="run1"))
    await ready.wait()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    output = ui.err.export_text()
    assert "Detached" in output and "inspect run1 --online --watch" in output
    assert "--settings '/tmp/custom settings.json'" in output


@pytest.mark.parametrize("watch", [False, True])
async def test_online_inspect_can_reconnect_to_standalone_intake(monkeypatch, capsys, watch):
    from types import SimpleNamespace

    from temporalio.client import WorkflowExecutionStatus

    from corsair.entrypoints.cli import execute

    intake = stopped_parent().intake
    assert intake is not None
    handle = Mock(id="run1")
    handle.describe = AsyncMock(
        return_value=SimpleNamespace(
            workflow_type="corsair.intake", status=WorkflowExecutionStatus.COMPLETED
        )
    )
    handle.result = AsyncMock(return_value=intake)
    client = Mock()
    client.get_workflow_handle.return_value = handle
    monkeypatch.setattr(temporal_client, "connect", AsyncMock(return_value=client))
    options = ["inspect", "run1", "--online", "--format", "json"]
    await execute(parser().parse_args([*options, *(["--watch"] if watch else [])]))
    result = json.loads(capsys.readouterr().out)
    assert result == (
        intake.model_dump(mode="json") if watch else {"run_id": "run1", "state": "COMPLETED"}
    )


async def test_query_loss_is_visible_and_recovery_is_reported(monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.001)
    ui = terminal("--no-animation")
    done = asyncio.Event()
    calls = 0

    async def query():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("PRIVATE_QUERY")
        if calls == 3:
            done.set()
        return {"phase": "producer"}

    await ui.wait(done.wait(), "Run", query=query)
    output = ui.err.export_text()
    assert "Status unavailable" in output and "Status restored" in output
    assert "PRIVATE_QUERY" not in output


@pytest.mark.parametrize("width", [48, 80, 120])
def test_compact_result_keeps_verdict_scope_and_image_without_round_tables(width):
    ui = terminal(width=width)
    value = _demonstrated_result().model_copy(update={"manifest": _manifest()})
    ui.emit(value)
    output = ui.out.export_text()
    assert value.verdict.value in output and "Evidence scope" in output
    assert "Image" in output and "--details" in output
    assert "Identity · Totals" not in output and "Stopped at" not in output
    assert max(map(len, output.splitlines())) <= width


def test_details_retains_round_tables_and_identity():
    ui = terminal("--details", width=120)
    ui.emit(_demonstrated_result())
    output = ui.out.export_text()
    assert "Identity · Totals" in output and "Stopped at" in output


def test_failed_first_query_does_not_claim_a_previous_update():
    from corsair.entrypoints.render.progress import progress_panel

    ui = terminal(width=48)
    ui.out.print(progress_panel("Run", None, [], unavailable_for=10, animate=False, width=48))
    output = ui.out.export_text()
    assert "No status received" in output and "Last update" not in output


def test_details_does_not_change_machine_receipt(capsys):
    value = InvestigationResult(
        run_id="run1",
        case_id="case",
        disposition=Disposition.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        verdict=Verdict.INCONCLUSIVE,
        reason="budget exhausted",
    )
    for flags in ([], ["--details"]):
        ui = Terminal(parser().parse_args(["inspect", "run1", "--format", "json", *flags]))
        ui.emit(value)
        assert json.loads(capsys.readouterr().out) == value.model_dump(mode="json")


@pytest.mark.parametrize("width", [48, 80, 120])
def test_live_parent_snapshot_is_not_decoded_as_a_finished_receipt(width):
    ui = terminal(width=width)
    ui.emit(
        {
            "schema_version": "corsair.intake-investigation-result/1",
            "phase": "audit",
            "session": 1,
            "round": 2,
            "max_rounds": 4,
            "image_reference": "runtime:1",
            "image_id": "sha256:" + "a" * 64,
            "child_status_unavailable": True,
            "private": "PRIVATE_MODEL_TEXT",
        }
    )
    output = ui.out.export_text()
    assert "audit" in output and "2/4" in output and "runtime:1" in output
    assert "unavailable" in output and "PRIVATE_MODEL_TEXT" not in output
    assert max(map(len, output.splitlines())) <= width


@pytest.mark.parametrize(
    "status,label",
    [
        (ExecutionStatus.ERROR, "Failed"),
        (ExecutionStatus.BLOCKED, "Stopped"),
        (ExecutionStatus.CANCELLED, "Cancelled"),
    ],
)
async def test_returned_operational_failure_never_gets_completed_badge(status, label):
    ui = terminal()
    result = _demonstrated_result().model_copy(update={"execution_status": status})
    await ui.wait(asyncio.sleep(0, result=result), "Run", run_id="run1")
    assert label in ui.err.export_text() and "Completed" not in ui.err.export_text()


async def test_old_parent_status_does_not_require_a_child_query():
    client = Mock()
    parent = Mock(query=AsyncMock(return_value={"phase": "intake"}))
    assert await temporal_client.query_intake_progress(client, parent) == {"phase": "intake"}
    client.get_workflow_handle.assert_not_called()


@pytest.mark.parametrize("width", [48, 80, 120])
def test_detailed_results_and_run_lists_keep_long_identities_readable(width):
    ui = terminal("--details", width=width)
    result = _demonstrated_result()
    ui.emit(result)
    output = ui.out.export_text(clear=True)
    assert "Stopped at" in output and "Identity · Totals" in output
    compact = "".join(output.split()).replace("│", "")
    assert result.manifest.image_id in compact
    assert max(map(len, output.splitlines())) <= width
    identity = "run-" + "a" * 90
    ui.emit(
        {
            "runs": [
                {
                    "recorded_at": "2026-10-29T12:00:00+00:00",
                    "run_id": identity,
                    "case_id": "case",
                    "verdict": "INCONCLUSIVE",
                    "execution_status": "COMPLETED",
                }
            ],
            "invalid_records": 0,
        }
    )
    output = ui.out.export_text()
    if width < 80:
        assert identity in "".join(output.split()).replace("│", "")
    else:
        cells = [cell.strip() for line in output.splitlines() for cell in line.split("│")]
        assert identity == "".join(
            cell for cell in cells if cell.startswith("run-") or set(cell) == {"a"}
        )
    assert max(map(len, output.splitlines())) <= width


@pytest.mark.parametrize("receipt", ["valid", "absent", "mismatch", "corrupt"])
def test_parent_summary_only_displays_a_bound_committed_child(tmp_path, receipt):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts.intake_pipeline import IntakeInvestigationResult
    from tests.unit.test_intake_handoff import supported

    _, intake = supported()
    store = ArtifactStore(tmp_path)
    child = _demonstrated_result()
    ref = store.put_json(child)
    if receipt != "absent":
        store.commit(
            "result.run1", ref if receipt != "mismatch" else store.put_json({"different": 1})
        )
    if receipt == "corrupt":
        ref = store.put_json({"schema_version": "corsair.result/1"})
        child = child.model_copy(update={"run_id": "invalid"})
        store.commit("result.invalid", ref)
    parent = IntakeInvestigationResult(
        run_id="parent",
        case_id=child.case_id,
        status="investigation_finished",
        stop_reason=None,
        intake=intake,
        investigation_run_id=child.run_id,
        investigation_result=ref,
        investigation_disposition=child.disposition,
        investigation_execution_status=child.execution_status,
    )
    ui = terminal()
    ui.emit(parent, store=store)
    output = ui.out.export_text()
    assert ("EXPLOIT_DEMONSTRATED" in output) is (receipt == "valid")
    assert ("receipt unavailable" in output) is (receipt != "valid")
