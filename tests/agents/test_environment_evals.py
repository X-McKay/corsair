"""Boundary checks for the environment host observation suite and missing evidence."""

import json
from uuid import uuid4

from evals.environment.evaluate import HANDLE, ROOT, RecordedExecution
from evals.run import compare


def test_unknown_command_fails_closed_without_executing_it():
    case = json.loads((ROOT / "cases.json").read_text())[0]
    execution = RecordedExecution(case)
    receipt = execution.execute(
        HANDLE, ("sh", "-c", "touch /tmp/no-host-execution"), uuid4()
    )
    assert receipt.native_exit == 126
    assert receipt.stdout == b"command outside recorded operator policy"


def test_missing_report_has_unknown_counts_and_no_false_comparison():
    current = {"agent": "environment", "run": "x", "summary": {"report": "missing"}}
    text = compare(current, None, None)
    assert "unknown" in text and "0/0" not in text
    completed = {
        "agent": "environment",
        "run": "y",
        "summary": {"attempts": 1, "clean_attempts": 1},
    }
    text = compare(completed, current, "x")
    assert "comparison unavailable" in text and "clean attempts 0/0" not in text


def test_ready_identity_checks_reject_wrong_toolchain_framework_and_discovery():
    from types import SimpleNamespace
    from evals.environment.evaluate import EnvironmentChecks
    from corsair.agents.environment.contracts import EnvironmentInput

    case = json.loads((ROOT / "cases.json").read_text())[0]
    output = SimpleNamespace(
        status="ready",
        recipe=[],
        receipts=[],
        **{
            key: case["draft"][key]
            for key in (
                "toolchain_id",
                "framework",
                "baseline_test_id",
                "baseline_test_path",
                "discovery_command",
            )
        },
    )
    ctx = SimpleNamespace(
        metadata=case,
        output=output,
        inputs=SimpleNamespace(inputs=EnvironmentInput.model_validate(case["inputs"])),
        attributes={
            "read_paths": case["required_reads"],
            "commands": case["commands"],
            "records": [],
        },
    )
    assert EnvironmentChecks().evaluate(ctx)["setup_identity"]
    output.toolchain_id = "wrong-runtime"
    assert not EnvironmentChecks().evaluate(ctx)["setup_identity"]
    output.toolchain_id = case["draft"]["toolchain_id"]
    output.framework = "invented-framework"
    assert not EnvironmentChecks().evaluate(ctx)["setup_identity"]
    output.discovery_command = ["echo", "fake-discovery"]
    assert not EnvironmentChecks().evaluate(ctx)["discovery_command"]


def test_sparse_metrics_report_observed_coverage_without_imputing_zero(tmp_path):
    from evals.run import summarize

    case = {
        "name": "one",
        "assertions": {"ok": {"value": True}},
        "evaluator_failures": [],
        "metrics": {"calls": 2},
        "scores": {},
        "task_duration": 1,
    }
    other = dict(case, name="two", metrics={})
    (tmp_path / "report.json").write_text(
        json.dumps({"cases": [case, other], "failures": []})
    )
    summary = summarize(tmp_path)
    assert summary["efficiency_mean"]["calls"] == 2
    assert summary["efficiency_samples"]["calls"] == {"observed": 1, "attempts": 2}


def test_fixture_identity_and_outcome_labels_are_absent_from_agent_prompt():
    from corsair.agents.environment.agent import environment_prompt
    from corsair.agents.environment.contracts import EnvironmentInput

    cases = json.loads((ROOT / "cases.json").read_text())
    for case in cases:
        inputs = EnvironmentInput.model_validate(case["inputs"])
        assert inputs.policy_profile == "setup-public"
        prompt = environment_prompt(inputs)
        assert "fixture_id" not in prompt
        for marker in (
            "setup-registry",
            "setup-tls",
            "setup-unknown-delivery",
            "setup-unsupported-toolchain",
            "setup-ready",
        ):
            assert marker not in prompt


def test_unsupported_requirement_rejects_inverted_runtime_claim_with_valid_citation():
    from types import SimpleNamespace
    from corsair.agents.environment.contracts import EnvironmentInput
    from evals.environment.evaluate import EnvironmentChecks

    case = next(
        c
        for c in json.loads((ROOT / "cases.json").read_text())
        if c["status"] == "unsupported"
    )
    inputs = EnvironmentInput.model_validate(case["inputs"])
    citation = SimpleNamespace(
        path="README.md", start_line=2, end_line=2, quote="Requires Python 3.13."
    )
    output = SimpleNamespace(
        status="unsupported",
        requirement=case["draft"]["requirement"],
        citations=[citation],
        receipts=[],
    )
    ctx = SimpleNamespace(
        metadata=case,
        output=output,
        inputs=SimpleNamespace(inputs=inputs),
        attributes={"read_paths": ["README.md"], "commands": [], "records": []},
    )
    assert all(EnvironmentChecks().evaluate(ctx).values())
    output.requirement = "Python 3.12 required but prepared runtime is 3.13"
    checks = EnvironmentChecks().evaluate(ctx)
    assert checks["grounding"] and checks["status"]
    assert not checks["unsupported_requirement"]
