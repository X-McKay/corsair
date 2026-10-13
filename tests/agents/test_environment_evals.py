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
    assert receipt.stdout == b"synthetic fixture refusal: unrecorded command"
    assert execution.unrecorded_commands == [("sh", "-c", "touch /tmp/no-host-execution")]


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


def test_measured_zero_attributes_contribute_once_and_missing_values_stay_unknown(tmp_path):
    from evals.run import summarize

    base = {"name": "one", "assertions": {"ok": {"value": True}},
            "evaluator_failures": [], "scores": {}, "task_duration": 1}
    cases = [dict(base, metrics={}, attributes={"observed_output_corrections": 0,
                                                "unrelated": 99}),
             dict(base, name="two", metrics={"observed_output_corrections": 2},
                  attributes={"observed_output_corrections": 2}),
             dict(base, name="three", metrics={}, attributes={})]
    (tmp_path / "report.json").write_text(json.dumps({"cases": cases, "failures": []}))
    result = summarize(tmp_path)
    assert result["efficiency_mean"]["observed_output_corrections"] == 1
    assert result["efficiency_samples"]["observed_output_corrections"] == {"observed": 2, "attempts": 3}
    assert "unrelated" not in result["efficiency_mean"]


def environment_context(name):
    from types import SimpleNamespace
    from corsair.agents.environment.contracts import EnvironmentInput

    case = next(c for c in json.loads((ROOT / "cases.json").read_text()) if c["name"] == name)
    draft = dict(case["draft"])
    draft["citations"] = [SimpleNamespace(**c) for c in draft.get("citations", [])]
    return SimpleNamespace(metadata=case, output=SimpleNamespace(**draft, receipts=[]),
                           inputs=SimpleNamespace(inputs=EnvironmentInput.model_validate(case["inputs"])),
                           attributes={"read_paths": case["required_reads"], "commands": [], "records": []})


def test_blocked_build_requires_dependencies_before_the_failed_compile():
    from evals.environment.evaluate import EnvironmentChecks

    ctx = environment_context("build")
    ctx.attributes["commands"] = ctx.metadata["commands"]
    assert all(EnvironmentChecks().evaluate(ctx).values())
    ctx.attributes["commands"] = ctx.metadata["commands"][1:]
    facts = EnvironmentChecks().evaluate(ctx)
    assert facts["status"] and facts["layer"] and facts["command_policy"]
    assert not facts["required_commands"]
    ctx.attributes["commands"] = list(reversed(ctx.metadata["commands"]))
    assert not EnvironmentChecks().evaluate(ctx)["required_commands"]


def test_unknown_delivery_requires_the_observed_prefix_and_halts():
    from evals.environment.evaluate import EnvironmentChecks

    ctx = environment_context("unknown-delivery")
    ctx.attributes["commands"] = ctx.metadata["commands"][:1]
    assert all(EnvironmentChecks().evaluate(ctx).values())
    ctx.attributes["commands"] = []
    assert not EnvironmentChecks().evaluate(ctx)["required_commands"]
    ctx.attributes["commands"] = ctx.metadata["commands"][1:]
    assert not EnvironmentChecks().evaluate(ctx)["required_commands"]
    ctx.attributes["commands"] = ctx.metadata["commands"]
    assert not EnvironmentChecks().evaluate(ctx)["unknown_halt"]


def test_budget_block_requires_the_observed_prefix_without_commands_after_the_cap():
    from evals.environment.evaluate import EnvironmentChecks

    ctx = environment_context("command-budget")
    ctx.attributes["commands"] = ctx.metadata["commands"][:1]
    assert all(EnvironmentChecks().evaluate(ctx).values())
    ctx.attributes["commands"] = []
    assert not EnvironmentChecks().evaluate(ctx)["required_commands"]
    ctx.attributes["commands"] = ctx.metadata["commands"][1:2]
    assert not EnvironmentChecks().evaluate(ctx)["required_commands"]
    ctx.attributes["commands"] = ctx.metadata["commands"][:2]
    assert not EnvironmentChecks().evaluate(ctx)["command_budget"]


def test_missing_or_partial_provider_tokens_are_unknown_but_counters_keep_zero(tmp_path):
    from evals.run import summarize

    cases = []
    token_keys = ('observed_input_tokens', 'observed_output_tokens', 'input_tokens', 'output_tokens')
    for index, (present, tokens) in enumerate(((False, 0), (False, 50), (True, 0), (None, 10))):
        cases.append({'name': str(index), 'assertions': {'ok': {'value': True}},
                      'evaluator_failures': [], 'scores': {}, 'task_duration': 1,
                      'attributes': {'provider_usage_present': present, 'observed_commands': 0,
                                     'observed_input_tokens': tokens, 'observed_output_tokens': tokens},
                      'metrics': dict.fromkeys(token_keys, tokens)})
    (tmp_path / 'report.json').write_text(json.dumps({'cases': cases, 'failures': []}))
    result = summarize(tmp_path)
    for key in token_keys:
        assert result['efficiency_samples'][key] == {'observed': 2, 'attempts': 4}
        assert result['efficiency_mean'][key] == 5
    assert result['efficiency_samples']['observed_commands'] == {'observed': 4, 'attempts': 4}
    assert result['efficiency_mean']['observed_commands'] == 0

    (tmp_path / 'report.json').write_text(json.dumps({'cases': cases[:2], 'failures': []}))
    unknown = summarize(tmp_path)
    assert not set(token_keys) & unknown['efficiency_mean'].keys()
    assert not set(token_keys) & unknown['efficiency_samples'].keys()
