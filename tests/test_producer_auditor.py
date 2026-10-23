"""The producer loop with a scripted model and the kernel on the sandbox double; the auditor with a test model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.agents.auditor.agent import audit, build_auditor, render
from corsair.agents.producer.dependencies import SKILLS_DIR
from corsair.agents.resources import (
    load_agent_spec,
    read_skill_file,
    skill_body,
    skill_inventory,
    validate_agent_spec,
)
from corsair.application.cases import load_case
from corsair.application.investigation import investigate, render_case
from corsair.application.kernel import Kernel
from corsair.domain.verification import Gate, Label
from corsair.runtime import matrix
from tests.fakes import FakeSandboxes, Script
from tests.test_kernel import CASE, HAPPY, REFERENCE

pytestmark = pytest.mark.anyio

ROW = matrix.load()[0]


def scripted(responses: list[list[tuple[str, dict] | str]]) -> FunctionModel:
    """Each request takes the next scripted response: tool calls (name, args) or a final text."""
    queue = list(responses)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = queue.pop(0) if queue else ["I have no further moves."]
        parts = [
            TextPart(item) if isinstance(item, str) else ToolCallPart(tool_name=item[0], args=item[1])
            for item in step
        ]
        return ModelResponse(parts=parts)

    return FunctionModel(respond)


def make_kernel(fake: FakeSandboxes, tmp_path: Path) -> Kernel:
    return Kernel(
        fake,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        run_id="prod1",
        framework=framework(ROW.framework),
    )


async def test_producer_explores_submits_and_stops_when_verified(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    model = scripted(
        [
            [("read_skill", {"name": "differential-probing"})],
            [("bash", {"command": "sed -n 1,20p documents.py"})],
            [("submit", {"submission": REFERENCE.model_dump(mode="json")})],
            ["Verified: read_document reads outside the root; the fix is verified."],
        ]
    )
    run = await investigate(
        load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake
    )
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.fix.value == "verified"
    assert len(run.evaluations) == 1 and run.evaluations[0].gate.stage is Gate.VERIFIED
    assert run.requests == 4 and run.bash_calls == 1 and run.error is None
    assert run.final_text and run.final_text.startswith("Verified")
    # the working sandbox got the vulnerable tree with build network, and was removed
    work = next(spec for spec in fake.creates if spec.labels["corsair.lite.stage"] == "work")
    assert work.network == "build" and work.name in fake.removed and run.cleanup_confirmed is True
    assert any(str(path).endswith("vulnerable") for name, path in fake.copied_trees if name == work.name)
    bash = next(argv for name, argv in fake.execs if name == work.name and argv[0] == "bash")
    assert bash == ("bash", "-lc", "sed -n 1,20p documents.py")


async def test_rejections_return_the_gate_and_the_budget_ends_the_run_inconclusive(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    seen_prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        last = messages[-1]
        for part in getattr(last, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str) and "KERNEL REJECTED" in content:
                seen_prompts.append(content)
        return ModelResponse(
            parts=[ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json")})]
        )

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        max_submissions=2,
    )
    assert len(run.evaluations) == 2
    assert all(e.gate.stage is Gate.EXPLOIT_RUN for e in run.evaluations)
    assert run.verdict.label is Label.INCONCLUSIVE and run.verdict.rule == "K3"
    assert "exploit_run" in run.verdict.reason
    assert run.error and run.error.startswith("BudgetExhausted")
    assert run.requests == 3  # two evaluated submissions, then the budget ends the third
    assert (
        len(seen_prompts) == 2
        and "not demonstrated" in seen_prompts[0]
        and "Submissions left: 1" in seen_prompts[0]
    )


async def test_a_submission_rejected_by_the_guard_never_touches_a_sandbox(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    bad = REFERENCE.model_dump(mode="json") | {
        "probe": "from unittest import mock\nCONTROL_PAYLOAD=1\nEXPLOIT_PAYLOAD=2\ndef run_target(p): pass\n"
    }
    model = scripted([[("submit", {"submission": bad})], ["giving up"]])
    run = await investigate(
        load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake, max_submissions=1
    )
    assert run.evaluations[0].gate.stage is Gate.AST_GUARD
    assert [spec.labels["corsair.lite.stage"] for spec in fake.creates] == ["work"]


def test_render_case_carries_the_finding_but_no_oracle():
    text = render_case(load_case(CASE), ROW)
    assert (
        "Path traversal in read_document" in text
        and "documents.py line 4" in text
        and "fixed revision exists" in text
    )
    oracle = json.loads((CASE / "oracle.json").read_text())
    assert oracle["expected_label"] not in text and "expected" not in text.lower()


def test_skills_exist_and_name_the_contract():
    names = sorted(path.parent.name for path in SKILLS_DIR.glob("*/SKILL.md"))
    assert {
        "build-recipes",
        "differential-probing",
        "python-pytest",
        "runtime-selection",
        "sanitizers",
    } <= set(names)
    text = (SKILLS_DIR / "differential-probing" / "SKILL.md").read_text()
    for symbol in ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target"):
        assert symbol in text


def test_agent_specs_allow_declared_underscore_capabilities_and_reject_factory_drift():
    producer = load_agent_spec("corsair.agents.producer")
    assert {"shell_calls", "model_requests"} <= set(producer.budgets)
    assert {"read_skill", "budget_exhausted"} <= set(producer.tools) | set(producer.errors)
    with pytest.raises(ValueError, match="tool capability drift"):
        validate_agent_spec("corsair.agents.producer", tool_names=())


def test_packaged_skill_inventory_and_reader_refuse_symlinks(tmp_path):
    external = tmp_path / "external.md"
    external.write_text("unreviewed")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "differential-probing").symlink_to(tmp_path)
    assert skill_inventory(skills) == ()
    assert read_skill_file(skills, "differential-probing", ("differential-probing",)) is None


async def test_read_skill_tool_returns_the_original_guidance_body_without_portable_metadata(tmp_path):
    returned: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for part in getattr(messages[-1], "parts", []):
            if getattr(part, "tool_name", None) == "read_skill":
                returned.append(getattr(part, "content"))
        if not returned:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="read_skill", args={"name": "differential-probing"})]
            )
        return ModelResponse(parts=[TextPart("Stopping without a submission.")])

    await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(FakeSandboxes(dict(HAPPY)), tmp_path),
        backend=FakeSandboxes(dict(HAPPY)),
    )
    packaged = (SKILLS_DIR / "differential-probing" / "SKILL.md").read_text()
    assert returned == [skill_body(packaged)]
    assert not returned[0].startswith("---\n")


async def test_auditor_returns_the_typed_result_and_sees_no_outcome():
    agent = build_auditor(
        TestModel(custom_output_args={"valid": False, "reason": "run_target branches on the payload"})
    )
    result = await audit(agent, REFERENCE)
    assert result.valid is False and "branches" in result.reason
    prompt = render(REFERENCE)
    assert "Hypothesis" in prompt and REFERENCE.probe in prompt
    for word in ("passed", "failed", "holds", "violated"):
        assert word not in prompt.lower().replace("fails only", "")  # the auditor never learns an outcome


async def test_fix_run_feedback_lets_the_producer_correct_the_probe_and_never_loses_the_label(tmp_path):
    scenario = {**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "not in the subpath")}
    fake = FakeSandboxes(scenario)
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json")})
                ]
            )
        if calls == 2:  # the retry prompt named fix_run; resubmit a probe that catches the rejection
            fake.scenario[("fixed", "exploit")] = Script("holds")
            fixed_probe = REFERENCE.probe.replace("except ValueError:", "except (ValueError, OSError):")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="submit",
                        args={"submission": REFERENCE.model_dump(mode="json") | {"probe": fixed_probe}},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Verified with the fix.")])

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        max_submissions=3,
    )
    assert [e.gate.stage for e in run.evaluations] == [Gate.FIX_RUN, Gate.VERIFIED]
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.fix.value == "verified"
    assert run.error is None and run.requests == 3


async def test_budget_exhaustion_after_fix_run_keeps_the_verified_label_with_the_fix_unverified(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "rejected")})
    model = scripted(
        [[("submit", {"submission": REFERENCE.model_dump(mode="json")})], ["Keeping the result."]]
    )
    run = await investigate(
        load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake, max_submissions=1
    )
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.fix.value == "not_verified"
    assert run.evaluations[0].gate.stage is Gate.FIX_RUN and run.error is None


async def test_leaked_template_token_is_retried_and_no_submission_is_inconclusive_not_error(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    model = scripted(
        [
            [("bash", {"command": "ls"})],
            ["<|im_start|>user"],
            ["I could not build a probe that reaches the sink."],
        ]
    )
    run = await investigate(
        load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake
    )
    assert run.verdict.label is Label.INCONCLUSIVE and "ended without a submission" in run.verdict.reason
    assert "could not build" in run.verdict.reason and run.requests == 3 and run.error is None


async def test_shell_budget_is_operator_owned_and_a_token_budget_stop_is_inconclusive(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls <= 3:
            return ModelResponse(parts=[ToolCallPart(tool_name="bash", args={"command": f"ls {calls}"})])
        return ModelResponse(parts=[TextPart("Stopping.")])

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        max_bash_calls=2,
    )
    assert run.bash_calls == 2  # the third call was answered with the budget message, not executed
    executed = [argv for name, argv in fake.execs if argv[0] == "bash" and argv[1] == "-lc"]
    assert len(executed) == 2

    def explore_forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name="bash", args={"command": "ls"})])

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(explore_forever),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        request_limit=2,
    )
    assert run.verdict.label is Label.INCONCLUSIVE and "budget ended the run" in run.verdict.reason
    assert run.error and run.error.startswith("UsageLimitExceeded")


def variant(n: int) -> dict:
    """The reference submission with a distinct digest: a different trailing comment in the probe."""
    return REFERENCE.model_dump(mode="json") | {"probe": REFERENCE.probe + f"\n# variant {n}\n"}


async def test_negative_threshold_met_stops_the_producer_early_with_likely_not_exploitable(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": variant(calls)})])

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        max_submissions=4,
    )
    assert run.verdict.label is Label.LIKELY_NOT_EXPLOITABLE and run.verdict.rule == "K4"
    assert run.verdict.fix.value == "not_applicable"
    assert all(e.clean_negative and e.gate.stage is Gate.EXPLOIT_RUN for e in run.evaluations)
    assert len(run.evaluations) == 2 and calls == 2  # the remaining submission budget was not spent
    assert run.early_stop == "negative_threshold" and run.error is None and run.requests == 2
    assert (
        len(fake.opened) == 4
    )  # control and exploit on the vulnerable revision, twice; no fixed-revision runs
    assert run.cleanup_confirmed is True


async def test_below_the_threshold_an_exhausted_budget_stays_inconclusive(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script("holds")})
    model = scripted([[("submit", {"submission": variant(1)})], ["Stopping."]])
    run = await investigate(
        load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake, max_submissions=1
    )
    assert run.evaluations[0].clean_negative and run.early_stop is None
    assert run.verdict.label is Label.INCONCLUSIVE and run.verdict.rule == "K3"
    assert "exploit_run" in run.verdict.reason


async def test_a_failing_fix_keeps_the_exploitable_label_and_later_negatives_neither_downgrade_nor_stop(
    tmp_path,
):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "rejected")})
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:  # exploitable on the vulnerable revision; the fix is not verified (fix_run feedback)
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json")})
                ]
            )
        if (
            calls == 2
        ):  # the vulnerable exploit now holds: clean negatives, which the exploitable verdict outranks
            fake.scenario[("vulnerable", "exploit")] = Script("holds")
            return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": variant(2)})])
        if calls == 3:
            return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": variant(3)})])
        return ModelResponse(parts=[TextPart("Keeping the result.")])

    run = await investigate(
        load_case(CASE),
        ROW,
        model=FunctionModel(respond),
        kernel=make_kernel(fake, tmp_path),
        backend=fake,
        max_submissions=4,
    )
    assert [e.gate.stage for e in run.evaluations] == [Gate.FIX_RUN, Gate.EXPLOIT_RUN, Gate.EXPLOIT_RUN]
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.rule == "K1"
    assert run.verdict.fix.value == "not_verified"
    assert run.early_stop is None and run.error is None and calls == 4
