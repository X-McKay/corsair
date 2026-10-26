import ast
import asyncio
import io
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from corsair.entrypoints import terminal as terminal_module
from corsair.entrypoints.cli import execute, parser, validate_run_id
from corsair.entrypoints.terminal import (
    Terminal,
    child_changes,
    progress_fields,
    progress_panel,
)
from corsair.observability.logging import JsonFormatter, MetadataFilter, event


@pytest.mark.parametrize(
    "arguments",
    [
        ["--format", "json", "report", "x"],
        ["report", "x", "--format", "json"],
    ],
)
def test_presentation_options_work_before_and_after_command(arguments):
    args = parser().parse_args(arguments)
    assert args.format == "json"
    assert args.no_animation is False


def test_machine_output_has_no_ansi_even_with_forced_color(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    terminal.emit({"status": "pass", "message": "[red]data not markup[/red]"})
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert json.loads(output)["message"].startswith("[red]")
    assert not terminal.animate


def test_human_terminal_displays_colors_without_interpreting_data(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    terminal = Terminal(parser().parse_args(["--format", "human", "report", "x"]))
    terminal.emit({"attempts": 3, "passed": 2, "failed": 1, "cost_usd": None})
    output = capsys.readouterr().out
    assert "\x1b[" in output
    assert "Corsair" in output
    assert "unknown" in output


def test_no_color_and_no_animation_disable_control_codes(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    terminal = Terminal(
        parser().parse_args(
            [
                "report",
                "x",
                "--format",
                "human",
                "--no-color",
                "--no-animation",
            ]
        )
    )
    terminal.emit({"attempts": 1})
    assert "\x1b" not in capsys.readouterr().out
    assert not terminal.animate


async def test_wait_observes_queries_and_propagates_result():
    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    queries = []

    async def query():
        queries.append(True)
        return {"phase": "evidence", "round": 1}

    result = await terminal.wait(asyncio.sleep(0, result=42), "Real waiter", query=query)
    assert result == 42
    assert len(queries) == 1


async def test_cancelling_local_wait_does_not_call_remote_cancel():
    terminal = Terminal(parser().parse_args(["report", "x"]))
    released = asyncio.Event()

    async def pending():
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    waiter = asyncio.create_task(terminal.wait(pending(), "pending"))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert released.is_set()


def test_structured_logs_whitelist_and_redact_credentials(monkeypatch):
    monkeypatch.setenv("PRIVATE_API_TOKEN", "private-token-to-redact")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(MetadataFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("corsair")
    prior_handlers = logger.handlers[:]
    prior_level, prior_propagate = logger.level, logger.propagate
    logger.handlers.clear()
    logger.handlers.append(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    try:
        event(
            "activity.failed",
            run_id="r1",
            error_type="RuntimeError",
            message="private-token-to-redact https://user:password@example.com/x?token=y\x1b[31m",
            prompt="NEVER_LOG_THIS",
            payload="NEVER_LOG_THIS",
        )
    finally:
        logger.handlers.clear()
        logger.handlers.extend(prior_handlers)
        logger.propagate = prior_propagate
        logger.setLevel(prior_level)
    row = json.loads(output.getvalue())
    assert row["run_id"] == "r1"
    assert "prompt" not in row and "payload" not in row
    assert "private-token-to-redact" not in output.getvalue()
    assert "password" not in output.getvalue()
    assert "\x1b" not in output.getvalue()


def test_failed_command_has_clean_jsonl_stderr_and_nonzero_exit(tmp_path):
    executable = Path(sys.executable).parent / "corsair"
    result = subprocess.run(
        [
            str(executable),
            "--format",
            "json",
            "--log-format",
            "json",
            "report",
            str(tmp_path / "absent"),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "FORCE_COLOR": "1"},
    )
    assert result.returncode == 2
    assert result.stdout == ""
    rows = [json.loads(line) for line in result.stderr.splitlines()]
    assert rows[-1]["event"] == "cli.failed"
    assert rows[-1]["error_type"] == "FileNotFoundError"
    assert "\x1b" not in result.stderr and "Traceback" not in result.stderr


def test_runtime_has_no_placeholder_or_test_dependency():
    root = Path(__file__).resolve().parents[2] / "src/corsair"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("tests", "unittest.mock")), path
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.startswith(("tests", "unittest.mock")) for alias in node.names
                ), path
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                assert getattr(node.exc.func, "id", None) != "NotImplementedError", path


def test_nested_native_pydantic_receipts_are_json_serializable(capsys):
    from corsair.contracts import BatchItem

    terminal = Terminal(parser().parse_args(["report", "x", "--format", "json"]))
    terminal.emit([BatchItem(case_id="case1", run_id="run1", error="unavailable")])
    assert json.loads(capsys.readouterr().out)[0]["case_id"] == "case1"


async def test_execute_dispatches_report_without_runtime_services(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {"attempts": 1, "failed": 0}}))

    args = parser().parse_args(["--format", "json", "report", str(report)])

    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out) == {"summary": {"attempts": 1, "failed": 0}}


def _comparable_report(path, *, status="pass", digest_value="sha256:frozen", reason="done"):
    rows = [
        {
            "run_id": "eval-1.c0.r0",
            "case_id": "case01",
            "status": status,
            "verdict": "EXPLOIT_DEMONSTRATED" if status == "pass" else "INCONCLUSIVE",
            "execution_status": "COMPLETED",
            "forbidden_label": False,
            "llm_calls": 3,
            "input_tokens": 120,
            "output_tokens": 30,
            "agent_seconds": 2.5,
            "reason": reason,
        }
    ]
    path.write_text(
        json.dumps({"rows": rows, "summary": {"attempts": 1}, "dataset_digest": digest_value})
    )
    return path


def test_human_report_renders_one_row_per_case(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    report = _comparable_report(tmp_path / "report.json", reason="[red]not markup[/red]")
    terminal = Terminal(parser().parse_args(["--format", "human", "--no-color", "report", "x"]))

    terminal.emit(json.loads(report.read_text()))

    output = capsys.readouterr().out
    assert "Corsair · Cases" in output
    assert "case01" in output and "EXPLOIT_DEMONSTRATED" in output
    assert "3 LLM" in output and "120/30 tok" in output
    assert "[red]not markup[/red]" in output
    assert "sha256:frozen" in output


async def test_execute_compare_exits_by_regression_and_emits_the_structured_diff(tmp_path, capsys):
    baseline = _comparable_report(tmp_path / "baseline.json")
    same = _comparable_report(tmp_path / "same.json")
    worse = _comparable_report(tmp_path / "worse.json", status="fail")

    args = parser().parse_args(["--format", "json", "compare", str(baseline), str(same)])
    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out)["regression"] is False

    args = parser().parse_args(["--format", "json", "compare", str(baseline), str(worse)])
    assert await execute(args) == 1
    diff = json.loads(capsys.readouterr().out)
    assert diff["baseline_report"] == str(baseline)
    assert diff["regressions"] == [{"case_id": "case01", "repeat": 0, "reason": "pass_to_fail"}]


async def test_execute_compare_refuses_mismatched_datasets_without_the_flag(tmp_path, capsys):
    baseline = _comparable_report(tmp_path / "baseline.json")
    other = _comparable_report(tmp_path / "other.json", digest_value="sha256:other")

    args = parser().parse_args(["--format", "json", "compare", str(baseline), str(other)])
    with pytest.raises(ValueError, match="--allow-dataset-mismatch"):
        await execute(args)
    assert capsys.readouterr().out == ""

    args = parser().parse_args(
        ["--format", "json", "compare", str(baseline), str(other), "--allow-dataset-mismatch"]
    )
    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out)["dataset_match"] is False


async def test_human_compare_warns_on_dataset_mismatch_and_lists_changed_cases(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("COLUMNS", "200")
    baseline = _comparable_report(tmp_path / "baseline.json")
    worse = _comparable_report(tmp_path / "worse.json", status="fail", digest_value="sha256:b")
    args = parser().parse_args(
        [
            "--format",
            "human",
            "--no-color",
            "compare",
            str(baseline),
            str(worse),
            "--allow-dataset-mismatch",
        ]
    )

    assert await execute(args) == 1

    output = capsys.readouterr().out
    assert "Dataset mismatch" in output
    assert "sha256:frozen" in output and "sha256:b" in output
    assert "REGRESSION" in output
    assert "pass to fail" in output
    assert "Changed cases" in output


async def test_human_compare_of_identical_reports_reports_no_changes(tmp_path, capsys):
    baseline = _comparable_report(tmp_path / "baseline.json")
    args = parser().parse_args(
        ["--format", "human", "--no-color", "compare", str(baseline), str(baseline)]
    )

    assert await execute(args) == 0

    output = capsys.readouterr().out
    assert "NO REGRESSION" in output
    assert "No per-case status or label changes" in output
    assert "Dataset mismatch" not in output


async def test_eval_saves_the_loaded_dataset_digest(tmp_path, monkeypatch, capsys):
    from corsair.adapters.temporal import client as temporal_client
    from corsair.contracts import BatchItem, digest
    from corsair.entrypoints import api
    from corsair.evaluation.scoring import load_dataset
    from corsair.settings import Settings

    class Handle:
        id = "eval-provenance"

        async def query(self, _query):
            return {"completed": 1, "total": 1}

    dataset_path = Path(__file__).resolve().parents[2] / "evals/datasets/dev.json"
    dataset, _, _ = load_dataset(dataset_path)

    async def connect(_settings):
        return object()

    async def start_evaluation(_client, _batch, _settings):
        return Handle()

    async def wait_for_result(_handle):
        return [BatchItem(case_id="case01", run_id="eval-provenance-case01", error="unavailable")]

    monkeypatch.setattr(
        "corsair.entrypoints.cli._settings",
        lambda _: Settings(artifact_root=str(tmp_path / "artifacts")),
    )
    monkeypatch.setattr(temporal_client, "connect", connect)
    monkeypatch.setattr(temporal_client, "wait_for_result", wait_for_result)
    monkeypatch.setattr(api, "start_evaluation", start_evaluation)
    report = tmp_path / "evaluation.json"
    args = parser().parse_args(
        [
            "--format",
            "json",
            "eval",
            str(dataset_path),
            "--run-id",
            "eval-provenance",
            "--output",
            str(report),
        ]
    )

    assert await execute(args) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["unavailable_results"] == 1
    assert json.loads(report.read_text())["dataset_digest"] == digest(dataset)


async def test_rescore_saves_the_loaded_dataset_digest(tmp_path, monkeypatch, capsys):
    from corsair.contracts import digest
    from corsair.entrypoints import cli
    from corsair.evaluation.scoring import load_dataset
    from corsair.settings import Settings

    dataset_path = Path(__file__).resolve().parents[2] / "evals/datasets/dev.json"
    dataset, _, _ = load_dataset(dataset_path)
    monkeypatch.setattr(
        cli, "_settings", lambda _: Settings(artifact_root=str(tmp_path / "artifacts"))
    )
    monkeypatch.setattr(
        cli,
        "_score_saved_result",
        lambda _store, identity, _oracles: {"run_id": identity, "status": "pass"},
    )
    report = tmp_path / "rescored.json"
    args = parser().parse_args(
        [
            "--format",
            "json",
            "rescore",
            str(dataset_path),
            "rescore-provenance",
            "--output",
            str(report),
        ]
    )

    assert await execute(args) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["passed"] == 1
    assert json.loads(report.read_text())["dataset_digest"] == digest(dataset)


async def test_inspect_rejects_watch_before_loading_or_creating_runtime_state():
    args = parser().parse_args(["inspect", "run1", "--watch"])

    with pytest.raises(ValueError, match="--watch requires --online"):
        await execute(args)


def test_run_id_rejects_invalid_or_reserved_length_values():
    with pytest.raises(ValidationError):
        validate_run_id("invalid/id")
    with pytest.raises(ValueError, match="operation suffixes"):
        validate_run_id("a" * 61)


def test_cli_exit_does_not_retain_handled_exception_tracebacks(tmp_path):
    # A test-only context observer invokes the actual main function, without fake responses.
    probe = (
        "import json\n"
        "from corsair.entrypoints.cli import main\n"
        "try:\n"
        "    main()\n"
        "except SystemExit as exit:\n"
        "    print(json.dumps({'code': exit.code, 'context_released': exit.__context__ is None}))\n"
        "    raise\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, "report", str(tmp_path / "absent"), "--log-format", "json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"code": 2, "context_released": True}
    assert json.loads(result.stderr.splitlines()[-1])["event"] == "cli.failed"


def test_client_only_operations_do_not_import_worker_or_adk_composition():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import corsair.adapters.temporal.client; "
            "assert 'corsair.entrypoints.worker' not in sys.modules; "
            "assert not any(name.startswith('google.adk') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


# Payload, hypothesis, plan and model-authored reason strings that human output must never show.
_PRIVATE = (
    "CONTROL-PAYLOAD-SENTINEL",
    "EXPLOIT-PAYLOAD-SENTINEL",
    "HYPOTHESIS-SENTINEL",
    "PLAN-SENTINEL",
    "AUDIT-REASON-SENTINEL",
    "FEEDBACK-REASON-SENTINEL",
    "ABSTAIN-REASON-SENTINEL",
)


def _manifest():
    from corsair.contracts import RunManifest

    return RunManifest(
        package_version="0.1.0",
        request_digest="1" * 64,
        config_digest="2" * 64,
        producer_prompt_digest="3" * 64,
        auditor_prompt_digest="4" * 64,
        image_id="sha256:" + "5" * 64,
        models={"producer": "scripted-producer", "auditor": "scripted-auditor"},
    )


def _proposal():
    from corsair.contracts import (
        PlanRevision,
        ProducerDecision,
        Submission,
    )

    submission = Submission(
        hypothesis="HYPOTHESIS-SENTINEL",
        plan=PlanRevision(
            revision=1,
            objective="PLAN-SENTINEL objective",
            next_steps=["PLAN-SENTINEL step"],
            reason="PLAN-SENTINEL reason",
        ),
        control_payload={"path": "CONTROL-PAYLOAD-SENTINEL"},
        exploit_payload={"path": "../EXPLOIT-PAYLOAD-SENTINEL"},
    )
    return ProducerDecision(kind="proposal", submission=submission)


def _observation(adversarial_outcome, *, operation_id="run1.r1"):
    from corsair.contracts import ArtifactRef, Observation, RoleObservation, RoleOutcome

    return Observation(
        operation_id=operation_id,
        source_digest="6" * 64,
        submission_digest="7" * 64,
        control=RoleObservation(
            outcome=RoleOutcome.HELD,
            target_executed=True,
            covered_lines=[12, 13, 14, 20],
            reason="validated native pytest/coverage evidence",
            native_exit_code=0,
        ),
        adversarial=RoleObservation(
            outcome=adversarial_outcome,
            target_executed=True,
            covered_lines=[12, 13, 14, 20, 21],
            reason="validated native pytest/coverage evidence",
            native_exit_code=1 if adversarial_outcome is RoleOutcome.VIOLATION else 0,
        ),
        artifact=ArtifactRef(sha256="8" * 64, size=512),
        cleanup_confirmed=True,
    )


def _audit(decision, rule):
    from corsair.contracts import AuditOutput, AuditResult, Usage

    return AuditOutput(
        review=AuditResult(decision=decision, rule=rule, reason="AUDIT-REASON-SENTINEL"),
        usage=Usage(llm_calls=1, input_tokens=300, output_tokens=40, seconds=1.5),
    )


def _demonstrated_result():
    from corsair.contracts import (
        ArtifactRef,
        AuditDecision,
        Disposition,
        ExecutionStatus,
        InvestigationResult,
        ProducerOutput,
        RoleOutcome,
        RoundResult,
        Usage,
        Verdict,
    )

    return InvestigationResult(
        run_id="run1",
        case_id="case01",
        disposition=Disposition.SUPPORTED,
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
        execution_status=ExecutionStatus.COMPLETED,
        reason="paired native observation supports the component claim",
        manifest=_manifest(),
        rounds=[
            RoundResult(
                index=1,
                producer=ProducerOutput(
                    decision=_proposal(),
                    usage=Usage(
                        llm_calls=3, tool_calls=4, input_tokens=1200, output_tokens=210, seconds=4
                    ),
                ),
                observation=_observation(RoleOutcome.VIOLATION),
                audit=_audit(AuditDecision.ACCEPT, "differential-is-relevant"),
            )
        ],
        result_artifact=ArtifactRef(sha256="9" * 64, size=2048),
    )


def _inconclusive_result():
    from corsair.contracts import (
        AuditDecision,
        Disposition,
        ExecutionStatus,
        Feedback,
        InvestigationResult,
        ProducerOutput,
        RoleOutcome,
        RoundResult,
        Usage,
        Verdict,
    )

    rejected = RoundResult(
        index=1,
        producer=ProducerOutput(decision=_proposal(), usage=Usage(llm_calls=2, tool_calls=1)),
        observation=_observation(RoleOutcome.VIOLATION),
        audit=_audit(AuditDecision.REJECT, "payload-not-grounded"),
    )
    held = RoundResult(
        index=2,
        session=2,
        producer=ProducerOutput(
            decision=_proposal(),
            usage=Usage(llm_calls=1, tool_calls=2),
            feedback=Feedback(gate="audit", reason="FEEDBACK-REASON-SENTINEL"),
        ),
        observation=_observation(RoleOutcome.HELD, operation_id="run2.s2.r2"),
        audit=_audit(AuditDecision.ACCEPT, "differential-is-relevant"),
    )
    return InvestigationResult(
        run_id="run2",
        case_id="case02",
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        reason="Investigation budget exhausted.",
        manifest=_manifest(),
        rounds=[rejected, held],
        usage_complete=False,
    )


def _human(capsys, value, *extra):
    terminal = Terminal(parser().parse_args(["--format", "human", *extra, "report", "x"]))
    terminal.emit(value)
    return capsys.readouterr().out


def _assert_private_content_absent(output):
    for sentinel in _PRIVATE:
        assert sentinel not in output, sentinel


def test_human_result_leads_with_verdict_then_rounds_identity_and_totals(capsys, monkeypatch):
    output = _human(capsys, _demonstrated_result(), "--no-color")

    verdict = output.index("EXPLOIT_DEMONSTRATED")
    assert verdict < output.index("Rounds") < output.index("Identity")
    # The full result digest is folded across lines at 80 columns, never ellipsized.
    assert "9" * 64 in "".join(ch for ch in output if ch not in " │\n")
    assert "…" not in output.split("Identity")[0]  # no fact is ellipsized at 80 columns
    _assert_private_content_absent(output)

    # Six round columns fold cells at 80 columns; read the cell facts at a wider terminal.
    monkeypatch.setenv("COLUMNS", "120")
    output = _human(capsys, _demonstrated_result(), "--no-color")
    assert "SUPPORTED" in output and "COMPLETED" in output and "component" in output
    assert "held" in output and "violated" in output
    assert "L12-14, 20 " in output and "L12-14, 20-21" in output
    assert "ACCEPT" in output and "differential-is-relevant" in output
    assert "3 llm · 4 tool" in output and "1200/210 tok" in output
    assert "scripted-producer" in output and "sha256:555555555555" in output
    # Totals come from the shared scoring calculation: producer plus audit usage.
    assert "LLM calls       4 " in output and "Input tokens    1500" in output
    assert "Cost            unknown" in output
    _assert_private_content_absent(output)


def test_human_inconclusive_result_shows_audit_rejection_and_unknown_totals(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "120")
    output = _human(capsys, _inconclusive_result(), "--no-color")

    assert output.index("INCONCLUSIVE") < output.index("Rounds")
    assert "REJECT" in output and "payload-not-grounded" in output
    assert "gate: audit" in output
    assert "2.2" in output  # session 2, round 2
    assert "tokens unknown" in output
    assert "Usage complete  false" in output
    assert "LLM calls       unknown" in output
    _assert_private_content_absent(output)


def test_human_verify_observation_renders_roles_without_a_verdict(capsys):
    from corsair.contracts import RoleOutcome

    output = _human(capsys, _observation(RoleOutcome.VIOLATION), "--no-color")

    assert "Native reference observation" in output
    assert "no security verdict" in output
    assert "EXPLOIT_DEMONSTRATED" not in output
    assert "control" in output and "adversarial" in output
    assert "held" in output and "violated" in output
    assert "L12-14, 20-21" in output
    assert "validated native" in output  # kernel-authored role reason
    assert "Cleanup           confirmed" in output
    assert "run1.r1" in output
    _assert_private_content_absent(output)


def test_human_result_colours_verdict_without_interpreting_markup(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    result = _demonstrated_result().model_copy(update={"reason": "[bold]not markup[/bold]"})

    output = _human(capsys, result)

    assert "\x1b[1;31mEXPLOIT_DEMONSTRATED" in output
    assert "[bold]not markup[/bold]" in output
    _assert_private_content_absent(output)


def test_json_result_and_observation_are_unchanged_dumps(capsys):
    from corsair.contracts import RoleOutcome

    terminal = Terminal(parser().parse_args(["--format", "json", "report", "x"]))
    for value in (_demonstrated_result(), _observation(RoleOutcome.HELD)):
        terminal.emit(value)
        expected = json.dumps(value.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        assert capsys.readouterr().out == expected


def test_human_result_renders_fixed_revision_roles_and_gate(capsys):
    from corsair.contracts import Feedback, FixStatus, RoleOutcome

    fixed = _observation(RoleOutcome.HELD, operation_id="run1.fix1").model_copy(
        update={
            "cleanup_confirmed": False,
            "feedback": Feedback(gate="sandbox", reason="FEEDBACK-REASON-SENTINEL"),
        }
    )
    result = _demonstrated_result().model_copy(
        update={"fix_status": FixStatus.NOT_BLOCKED, "fix_observation": fixed}
    )

    output = _human(capsys, result, "--no-color")

    assert output.index("Rounds") < output.index("Fixed revision") < output.index("Identity")
    assert "NOT_BLOCKED" in output
    assert "cleanup NOT confirmed · gate: sandbox" in output
    _assert_private_content_absent(output)


def _wide(capsys, monkeypatch, value, *, store=None):
    """Human result at 160 columns, so cell facts read on one line each."""
    monkeypatch.setenv("COLUMNS", "160")
    terminal = Terminal(parser().parse_args(["--format", "human", "--no-color", "report", "x"]))
    terminal.emit(value, store=store)
    return capsys.readouterr().out


def _line(output, label):
    return next(line for line in output.splitlines() if label in line)


def _cells(output, *values):
    """The stripped table cells of the first row whose cells start with ``values``."""
    for line in output.splitlines():
        cells = [cell.strip() for cell in line.strip("│ ").split("│")]
        if cells[: len(values)] == list(values):
            return cells
    raise AssertionError(f"no row starts with {values}")


def test_human_result_names_each_round_stop_and_the_case_stop_without_model_text(
    capsys, monkeypatch, tmp_path
):
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.contracts import AuditDecision, ProducerDecision
    from corsair.contracts import ProducerOutput as Output
    from tests.unit import test_gate_ledger as ledger_cases
    from tests.unit.test_verdicts import _HELD, _VIOLATION
    from tests.unit.test_verdicts import _observation as _pair

    abstained = Output(
        decision=ProducerDecision(kind="no_grounded_candidate", reason="ABSTAIN-REASON-SENTINEL")
    )
    result = ledger_cases._result(
        [
            ledger_cases._round(abstained),
            ledger_cases._round(
                ledger_cases._proposal(),
                _pair(_HELD, _VIOLATION),
                _audit(AuditDecision.REJECT, "payload-not-grounded"),
                index=2,
            ),
        ],
        reason="Investigation budget exhausted.",
    )
    seen = []

    def verified(_result, store):
        seen.append(store)
        return ledger_cases._verified((1, 2))

    monkeypatch.setattr(terminal_module, "verified_rounds", verified)
    store = ArtifactStore(tmp_path / "artifacts")

    output = _wide(capsys, monkeypatch, result, store=store)

    assert seen == [store]
    assert output.index("Verdict") < output.index("Case stop") < output.index("Rounds")
    assert "budget_exhausted: Investigation budget exhausted." in _line(output, "Case stop")
    assert "Stopped at" in output
    assert "producer_abstained" in _line(output, "1.1")
    assert "audit_reject" in _line(output, "1.2")
    assert "evidence_unverified" not in output
    _assert_private_content_absent(output)


def test_human_result_without_receipt_verification_marks_kernel_rounds_unverified(
    capsys, monkeypatch
):
    output = _wide(capsys, monkeypatch, _inconclusive_result())

    assert "evidence_unverified" in _line(output, "1.1")
    assert "evidence_unverified" in _line(output, "2.2")
    assert "were not validated against the artifact store" in output
    assert "budget_exhausted" in _line(output, "Case stop")
    _assert_private_content_absent(output)


def test_case_stop_falls_back_to_the_last_round_and_never_repeats_the_result_reason(
    capsys, monkeypatch
):
    from corsair.contracts import AuditDecision, ExecutionStatus, Verdict
    from tests.unit import test_gate_ledger as ledger_cases
    from tests.unit.test_verdicts import _HELD, _VIOLATION
    from tests.unit.test_verdicts import _observation as _pair

    monkeypatch.setattr(
        terminal_module, "verified_rounds", lambda value, store: ledger_cases._verified((1, 1))
    )
    demonstrated = ledger_cases._result(
        [
            ledger_cases._round(
                ledger_cases._proposal(),
                _pair(_HELD, _VIOLATION),
                _audit(AuditDecision.ACCEPT, "differential-is-relevant"),
            )
        ],
        verdict=Verdict.EXPLOIT_DEMONSTRATED,
    )
    output = _wide(capsys, monkeypatch, demonstrated)
    assert "demonstrated · kernel at 1.1" in _line(output, "Case stop")

    failed = ledger_cases._result(
        [ledger_cases._round(ledger_cases._invalid("unforeseen adapter reason"))],
        reason="producer: RESULT-REASON-SENTINEL",
        status=ExecutionStatus.ERROR,
        verdict=Verdict.ERROR,
    )
    output = _wide(capsys, monkeypatch, failed)
    stop = _line(output, "Case stop")
    assert "execution_error" in stop and "RESULT-REASON-SENTINEL" not in stop
    assert "producer_invalid" in _line(output, "1.1")


def _transitions(*entries):
    from corsair.contracts import PhaseTransition

    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    return [
        PhaseTransition(
            phase=phase,
            session=session,
            round=round_index,
            at=None if offset is None else start + timedelta(seconds=offset),
        )
        for phase, session, round_index, offset in entries
    ]


def test_human_result_renders_recorded_phase_durations(capsys, monkeypatch):
    timeline = _transitions(
        ("prepare", 0, 0, 0),
        ("producer", 1, 1, 2.5),
        ("evidence", 1, 1, 40),
        ("audit", 1, 1, 70),
        ("producer", 1, 2, 75),
        ("evidence", 1, 2, 150),
        ("record", 1, 2, 160),
    )
    result = _demonstrated_result().model_copy(update={"timeline": timeline})

    output = _wide(capsys, monkeypatch, result)

    assert output.index("Rounds") < output.index("Phases") < output.index("Identity")
    assert "+00:00" in _line(output, "prepare") and "2.5 s" in _line(output, "prepare")
    second_evidence = _cells(output, "1.2", "evidence")
    assert second_evidence[2:] == ["+02:30", "10.0 s"]
    assert _cells(output, "1.2", "record")[3] == "-"
    assert "totals: prepare 2.5 s · producer 01:52 · evidence 40.0 s · audit 5.0 s" in _line(
        output, "totals"
    )
    assert "earlier transitions not retained" not in output


def test_human_phases_keep_unknown_times_and_truncation_explicit(capsys, monkeypatch):
    timeline = _transitions(("producer", 1, 4, None), ("audit", 1, 4, 3), ("record", 1, 4, 4))
    result = _demonstrated_result().model_copy(update={"timeline": timeline})

    output = _wide(capsys, monkeypatch, result)

    assert "unknown" in _line(output, "producer")
    assert "earlier transitions not retained; totals: producer unknown · audit 1.0 s" in output


def test_json_result_carries_the_timeline_and_never_the_rendered_ledger(
    capsys, monkeypatch, tmp_path
):
    from corsair.adapters.storage.filesystem import ArtifactStore

    def unexpected(*_arguments):
        raise AssertionError("JSON output must not verify receipts")

    monkeypatch.setattr(terminal_module, "verified_rounds", unexpected)
    timeline = _transitions(("prepare", 0, 0, 0), ("record", 1, 1, 1))
    result = _demonstrated_result().model_copy(update={"timeline": timeline})
    terminal = Terminal(parser().parse_args(["--format", "json", "report", "x"]))

    terminal.emit(result, store=ArtifactStore(tmp_path / "artifacts"))

    emitted = json.loads(capsys.readouterr().out)
    assert emitted == result.model_dump(mode="json")
    assert [entry["phase"] for entry in emitted["timeline"]] == ["prepare", "record"]
    assert "gate_ledger" not in emitted and "stops" not in emitted


_NOW = datetime(2026, 10, 25, 12, 4, 30, tzinfo=UTC)


def _status(phase: str, session: int, round_index: int, **extra: object) -> dict[str, object]:
    timeline = [
        {"phase": "prepare", "session": 0, "round": 0, "at": "2026-10-25T12:00:00+00:00"},
        {"phase": "producer", "session": 1, "round": 1, "at": "2026-10-25T12:00:05+00:00"},
    ]
    return {
        "phase": phase,
        "session": session,
        "round": round_index,
        "max_sessions": 2,
        "max_rounds": 4,
        "gate": None,
        "started": "2026-10-25T12:00:00+00:00",
        "deadline": "2026-10-25T12:15:00+00:00",
        "timeline": timeline,
        **extra,
    }


def _scripted_query(statuses: list[dict[str, object]], done: asyncio.Event):
    """A fake native query that advances one status per poll, then completes the wait."""
    remaining = list(statuses)

    async def query():
        if len(remaining) == 1:
            done.set()
            return remaining[0]
        return remaining.pop(0)

    return query


async def _finish(done: asyncio.Event) -> str:
    await done.wait()
    return "final"


def test_progress_fields_come_only_from_status_and_local_time():
    fields = dict(progress_fields(_status("evidence", 1, 2, gate="coverage"), _NOW, 999.0))

    assert fields == {
        "elapsed": "04:30",
        "phase": "evidence",
        "session": "1/2",
        "round": "2/4",
        "last gate": "coverage",
        "deadline": "2026-10-25T12:15:00+00:00 (10:30 left)",
    }
    assert dict(progress_fields(None, _NOW, 7.0)) == {
        "elapsed": "00:07",
        "status": "waiting for the workflow status query",
    }
    batch = {"completed": 3, "total": 8, "running": 2, "errors": 1}
    assert dict(progress_fields(batch, _NOW, 65.0)) == {
        "elapsed": "01:05",
        "cases": "3/8",
        "running": "2",
        "errors": "1",
    }
    expired = dict(
        progress_fields(_status("audit", 1, 1), datetime(2026, 10, 25, 13, tzinfo=UTC), 0)
    )
    assert expired["deadline"].endswith("(passed)")


def test_progress_panel_renders_status_and_phase_timeline():
    status = _status("producer", 1, 1)
    console = Console(file=io.StringIO(), width=100, color_system=None, record=True)
    console.print(progress_panel("Investigation run1", status, progress_fields(status, _NOW, 0)))
    frame = console.export_text()

    assert "Corsair · Investigation run1" in frame
    assert "Session" in frame and "1/2" in frame
    assert "Round" in frame and "1/4" in frame
    assert "10:30 left" in frame
    assert "+00:00" in frame and "+00:05" in frame and "prepare" in frame


def test_progress_panel_bounds_the_timeline_to_recent_transitions():
    many = [
        {"phase": f"p{index}", "session": 1, "round": index, "at": "2026-10-25T12:00:00+00:00"}
        for index in range(12)
    ]
    status = _status("p11", 1, 11, timeline=many)
    console = Console(file=io.StringIO(), width=100, color_system=None, record=True)
    console.print(progress_panel("run", status, progress_fields(status, _NOW, 0)))
    frame = console.export_text()

    assert "… 4 earlier" in frame
    assert " p3 " not in frame and " p4 " in frame


async def test_plain_human_wait_prints_one_line_per_status_change(capsys, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "--no-animation", "report", "x"]))
    done = asyncio.Event()
    statuses = [
        _status("producer", 1, 1),
        _status("producer", 1, 1),
        _status("evidence", 1, 1),
        _status("audit", 1, 1, gate="coverage"),
    ]

    result = await terminal.wait(
        _finish(done), "Investigation run1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "\x1b" not in captured.err
    common = "session 1/2 · round 1/4"
    deadline = "deadline 2026-10-25T12:15:00+00:00 (10:30 left)"
    assert captured.err.splitlines() == [
        f"Investigation run1 · elapsed 04:30 · phase producer · {common} · {deadline}",
        f"Investigation run1 · elapsed 04:30 · phase evidence · {common} · {deadline}",
        f"Investigation run1 · elapsed 04:30 · phase audit · {common} · last gate coverage"
        f" · {deadline}",
    ]


async def test_json_wait_prints_no_progress_view(capsys, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    terminal = Terminal(parser().parse_args(["--format", "json", "report", "x"]))
    done = asyncio.Event()
    statuses = [_status("producer", 1, 1), _status("evidence", 1, 1)]

    result = await terminal.wait(
        _finish(done), "Investigation run1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "Investigation run1" not in captured.err and "session" not in captured.err
    assert "\x1b" not in captured.err


async def test_animated_wait_draws_the_live_panel_on_stderr(monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "report", "x"]))
    stream = io.StringIO()
    terminal.err = Console(file=stream, force_terminal=True, color_system=None, width=100)
    terminal.animate = True
    done = asyncio.Event()
    statuses = [_status("producer", 1, 1), _status("evidence", 1, 2)]

    result = await terminal.wait(_finish(done), "Evaluation", query=_scripted_query(statuses, done))
    frame = stream.getvalue()

    assert result == "final"
    assert "Corsair · Evaluation" in frame
    assert "evidence" in frame and "2/4" in frame


def _child(case_id: str, repeat: int, state: str, started=None, finished=None):
    return {
        "case_id": case_id,
        "repeat": repeat,
        "run_id": f"eval1.{case_id}.r{repeat}",
        "state": state,
        "started": started,
        "finished": finished,
    }


def _batch(*children: dict[str, object], omitted: int = 0, total: int = 3) -> dict[str, object]:
    states = [child["state"] for child in children]
    return {
        "completed": states.count("completed") + states.count("failed"),
        "total": total,
        "running": states.count("running"),
        "errors": states.count("failed"),
        "started": "2026-10-25T12:00:00+00:00",
        "children": list(children),
        "children_omitted": omitted,
    }


_T0 = "2026-10-25T12:00:00+00:00"
_T1 = "2026-10-25T12:01:05+00:00"
_T2 = "2026-10-25T12:03:00+00:00"


def test_batch_progress_fields_use_the_batch_start_and_hide_child_rows():
    status = _batch(_child("a", 0, "running", _T0), _child("b", 0, "pending"), omitted=7)
    assert progress_fields(status, _NOW, 1.0) == [
        ("elapsed", "04:30"),
        ("cases", "0/3"),
        ("running", "1"),
        ("errors", "0"),
    ]


def test_progress_panel_renders_child_rows_in_query_order_with_a_progress_bar():
    status = _batch(
        _child("slow", 0, "running", _T0),
        _child("bad", 1, "failed", _T0, _T1),
        _child("next", 0, "pending"),
        _child("good", 0, "completed", _T1, _T2),
        total=4,
    )
    console = Console(file=io.StringIO(), width=120, color_system=None, record=True)
    fields = progress_fields(status, _NOW, 0)
    console.print(progress_panel("Evaluation eval1", status, fields, now=_NOW))
    frame = console.export_text()
    lines = frame.splitlines()

    assert "Corsair · Evaluation eval1" in frame
    assert "Progress" in frame and "━" in frame
    assert "State" in frame and "Elapsed" in frame
    order = [
        next(i for i, line in enumerate(lines) if f" {case} " in line)
        for case in ("slow", "bad", "next", "good")
    ]
    assert order == sorted(order)
    slow = lines[order[0]]
    assert "running" in slow and "04:30" in slow and "eval1.slow.r0" in slow
    assert "failed" in lines[order[1]] and "01:05" in lines[order[1]]
    assert "pending" in lines[order[2]] and ":" not in lines[order[2]].split("pending")[1][:20]
    assert "completed" in lines[order[3]] and "01:55" in lines[order[3]]
    assert "earlier" not in frame


def test_progress_panel_bounds_child_rows_and_counts_hidden_ones():
    children = [_child(f"case{index:02}", 0, "running", _T0) for index in range(20)]
    status = _batch(*children, omitted=30, total=50)
    console = Console(file=io.StringIO(), width=120, color_system=None, record=True)
    console.print(progress_panel("run", status, progress_fields(status, _NOW, 0), now=_NOW))
    frame = console.export_text()

    assert "case15" in frame and "case16" not in frame
    assert "… 34 more" in frame

    few = _batch(_child("a", 0, "running", _T0), omitted=2)
    console = Console(file=io.StringIO(), width=120, color_system=None, record=True)
    console.print(progress_panel("run", few, progress_fields(few, _NOW, 0), now=_NOW))
    assert "… 2 more" in console.export_text()


def test_child_changes_skip_first_seen_pending_rows_and_report_each_transition_once():
    seen: dict[str, str] = {}
    first = _batch(_child("a", 0, "running", _T0), _child("b", 0, "pending"))
    assert [row["case_id"] for row in child_changes(seen, first)] == ["a"]
    assert child_changes(seen, first) == []
    second = _batch(_child("b", 0, "running", _T1), _child("a", 0, "completed", _T0, _T2))
    assert [(row["case_id"], row["state"]) for row in child_changes(seen, second)] == [
        ("b", "running"),
        ("a", "completed"),
    ]
    assert child_changes(seen, {"phase": "producer"}) == []


async def test_plain_human_evaluation_wait_prints_one_line_per_child_state_change(
    capsys, monkeypatch
):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "--no-animation", "report", "x"]))
    done = asyncio.Event()
    statuses = [
        _batch(_child("a", 0, "pending"), _child("b", 0, "pending")),
        _batch(_child("a", 0, "running", _T0), _child("b", 0, "pending")),
        _batch(_child("b", 0, "running", _T1), _child("a", 0, "completed", _T0, _T1)),
        _batch(_child("b", 0, "failed", _T1, _T2), _child("a", 0, "completed", _T0, _T1)),
    ]

    result = await terminal.wait(
        _finish(done), "Evaluation eval1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "\x1b" not in captured.err
    head = "Evaluation eval1 · elapsed 04:30"
    assert captured.err.splitlines() == [
        f"{head} · cases 0/3 · running 0 · errors 0",
        f"{head} · cases 0/3 · running 1 · errors 0 · case a r0 · state running"
        " · case elapsed 04:30",
        f"{head} · cases 1/3 · running 1 · errors 0 · case b r0 · state running"
        " · case elapsed 03:25",
        f"{head} · cases 1/3 · running 1 · errors 0 · case a r0 · state completed"
        " · case elapsed 01:05",
        f"{head} · cases 2/3 · running 0 · errors 1 · case b r0 · state failed"
        " · case elapsed 01:55",
    ]


async def test_json_evaluation_wait_prints_no_child_rows(capsys, monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    terminal = Terminal(parser().parse_args(["--format", "json", "report", "x"]))
    done = asyncio.Event()
    statuses = [
        _batch(_child("a", 0, "running", _T0)),
        _batch(_child("a", 0, "completed", _T0, _T1)),
    ]

    result = await terminal.wait(
        _finish(done), "Evaluation eval1", query=_scripted_query(statuses, done)
    )
    captured = capsys.readouterr()

    assert result == "final"
    assert captured.out == ""
    assert "eval1.a.r0" not in captured.err and "case a" not in captured.err


async def test_animated_evaluation_wait_draws_the_child_table(monkeypatch):
    monkeypatch.setattr(terminal_module, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(terminal_module, "_utcnow", lambda: _NOW)
    terminal = Terminal(parser().parse_args(["--format", "human", "report", "x"]))
    stream = io.StringIO()
    terminal.err = Console(file=stream, force_terminal=True, color_system=None, width=120)
    terminal.animate = True
    done = asyncio.Event()
    statuses = [
        _batch(_child("a", 0, "running", _T0), _child("b", 0, "pending")),
        _batch(_child("b", 0, "running", _T1), _child("a", 0, "completed", _T0, _T1)),
    ]

    result = await terminal.wait(_finish(done), "Evaluation", query=_scripted_query(statuses, done))
    frame = stream.getvalue()

    assert result == "final"
    assert "eval1.b.r0" in frame and "completed" in frame and "━" in frame


def _modules_loaded_by_cli(tmp_path: Path, *arguments: str) -> set[str]:
    """Run the actual CLI entrypoint in a fresh interpreter and list the modules it loaded."""
    probe = (
        "import json, sys\n"
        "from corsair.entrypoints.cli import main\n"
        "try:\n"
        "    main()\n"
        "except SystemExit:\n"
        "    print(json.dumps(sorted(sys.modules)), file=sys.stderr)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
    )
    return set(json.loads(result.stderr.splitlines()[-1]))


def _loads(modules: set[str], prefix: str) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for name in modules)


@pytest.mark.parametrize(
    "arguments", [["--version"], ["--help"], ["unknown-command"], ["agent", "preview", "--help"]]
)
def test_parser_exits_load_no_presentation_contract_or_sdk_modules(tmp_path, arguments):
    modules = _modules_loaded_by_cli(tmp_path, *arguments)

    for prefix in ("rich", "pydantic", "temporalio", "docker", "corsair.contracts"):
        assert not _loads(modules, prefix), prefix


@pytest.mark.parametrize("command", ["report", "compare"])
def test_saved_report_commands_load_no_runtime_sdks(tmp_path, command):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {"passed": 1, "failed": 0}, "rows": []}))
    reports = [str(report)]
    if command == "compare":
        reports += [str(report), "--allow-dataset-mismatch"]

    modules = _modules_loaded_by_cli(tmp_path, "--format", "json", command, *reports)

    assert _loads(modules, "corsair.evaluation.comparison")
    for prefix in ("temporalio", "docker", "corsair.steps", "corsair.adapters.sandboxing"):
        assert not _loads(modules, prefix), prefix
