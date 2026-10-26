import ast
import asyncio
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.entrypoints.cli import execute, parser, validate_run_id
from corsair.entrypoints.terminal import Terminal
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
    assert json.loads(capsys.readouterr().out) == {"attempts": 1, "failed": 0}


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
        ProducerProposal,
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
    return ProducerDecision(root=ProducerProposal(submission=submission))


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


def test_human_result_leads_with_verdict_then_rounds_identity_and_totals(capsys):
    output = _human(capsys, _demonstrated_result(), "--no-color")

    verdict = output.index("EXPLOIT_DEMONSTRATED")
    assert verdict < output.index("Rounds") < output.index("Identity")
    assert "SUPPORTED" in output and "COMPLETED" in output and "component" in output
    assert "held" in output and "violated" in output
    assert "L12-14, 20 " in output and "L12-14, 20-21" in output
    assert "ACCEPT" in output and "differential-is-relevant" in output
    assert "3 llm · 4 tool" in output and "1200/210 tok" in output
    assert "scripted-producer" in output and "sha256:555555555555" in output
    # The full result digest is folded across lines at 80 columns, never ellipsized.
    assert "9" * 64 in "".join(ch for ch in output if ch not in " │\n")
    # Totals come from the shared scoring calculation: producer plus audit usage.
    assert "LLM calls       4 " in output and "Input tokens    1500" in output
    assert "Cost            unknown" in output
    assert "…" not in output.split("Identity")[0]  # no fact is ellipsized at 80 columns
    _assert_private_content_absent(output)


def test_human_inconclusive_result_shows_audit_rejection_and_unknown_totals(capsys):
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
