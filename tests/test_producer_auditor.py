"""The producer loop with a scripted model and the kernel on the sandbox double; the auditor with a test model."""
from __future__ import annotations

import json

import pytest
from pathlib import Path

from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.auditor import audit, build_auditor, render
from corsair.case import load_case
from corsair.kernel import Gate, Kernel, Label, Submission
from corsair.producer import SKILLS_DIR, investigate, render_case
from tests.fakes import FakeSandboxes, Script
from tests.test_kernel import CASE, HAPPY, REFERENCE

pytestmark = pytest.mark.anyio

ROW = matrix.load()[0]


def scripted(responses: list[list[tuple[str, dict] | str]]) -> FunctionModel:
    """Each request takes the next scripted response: tool calls (name, args) or a final text."""
    queue = list(responses)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = queue.pop(0) if queue else ["I have no further moves."]
        parts = [TextPart(item) if isinstance(item, str) else ToolCallPart(tool_name=item[0], args=item[1]) for item in step]
        return ModelResponse(parts=parts)

    return FunctionModel(respond)


def make_kernel(fake: FakeSandboxes, tmp_path: Path) -> Kernel:
    return Kernel(fake, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path / "artifacts"), run_id="prod1")


async def test_producer_explores_submits_and_stops_when_verified(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    model = scripted([
        [("read_skill", {"name": "differential-probing"})],
        [("bash", {"command": "sed -n 1,20p documents.py"})],
        [("submit", {"submission": REFERENCE.model_dump(mode="json")})],
        ["Verified: read_document reads outside the root; the fix is verified."],
    ])
    run = await investigate(load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake)
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
        return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json")})])

    run = await investigate(load_case(CASE), ROW, model=FunctionModel(respond), kernel=make_kernel(fake, tmp_path),
                            backend=fake, max_submissions=2)
    assert len(run.evaluations) == 2
    assert all(e.gate.stage is Gate.EXPLOIT_RUN for e in run.evaluations)
    assert run.verdict.label is Label.INCONCLUSIVE and run.verdict.rule == "K3"
    assert "exploit_run" in run.verdict.reason
    assert run.error and run.error.startswith("BudgetExhausted")
    assert run.requests == 3  # two evaluated submissions, then the budget ends the third
    assert len(seen_prompts) == 2 and "not demonstrated" in seen_prompts[0] and "Submissions left: 1" in seen_prompts[0]


async def test_a_submission_rejected_by_the_guard_never_touches_a_sandbox(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    bad = REFERENCE.model_dump(mode="json") | {"probe": "from unittest import mock\nCONTROL_PAYLOAD=1\nEXPLOIT_PAYLOAD=2\ndef run_target(p): pass\n"}
    model = scripted([[("submit", {"submission": bad})], ["giving up"]])
    run = await investigate(load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake,
                            max_submissions=1)
    assert run.evaluations[0].gate.stage is Gate.AST_GUARD
    assert [spec.labels["corsair.lite.stage"] for spec in fake.creates] == ["work"]


def test_render_case_carries_the_finding_but_no_oracle():
    text = render_case(load_case(CASE), ROW)
    assert "Path traversal in read_document" in text and "documents.py line 4" in text and "fixed revision exists" in text
    oracle = json.loads((CASE / "oracle.json").read_text())
    assert oracle["expected_label"] not in text and "expected" not in text.lower()


def test_skills_exist_and_name_the_contract():
    names = sorted(p.stem for p in SKILLS_DIR.glob("*.md"))
    assert names == ["build-recipes", "differential-probing", "python-pytest"]
    text = (SKILLS_DIR / "differential-probing.md").read_text()
    for symbol in ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target"):
        assert symbol in text


async def test_auditor_returns_the_typed_result_and_sees_no_outcome():
    agent = build_auditor(TestModel(custom_output_args={"valid": False, "reason": "run_target branches on the payload"}))
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
            return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json")})])
        if calls == 2:  # the retry prompt named fix_run; resubmit a probe that catches the rejection
            fake.scenario[("fixed", "exploit")] = Script("holds")
            fixed_probe = REFERENCE.probe.replace("except ValueError:", "except (ValueError, OSError):")
            return ModelResponse(parts=[ToolCallPart(tool_name="submit", args={"submission": REFERENCE.model_dump(mode="json") | {"probe": fixed_probe}})])
        return ModelResponse(parts=[TextPart("Verified with the fix.")])

    run = await investigate(load_case(CASE), ROW, model=FunctionModel(respond), kernel=make_kernel(fake, tmp_path),
                            backend=fake, max_submissions=3)
    assert [e.gate.stage for e in run.evaluations] == [Gate.FIX_RUN, Gate.VERIFIED]
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.fix.value == "verified"
    assert run.error is None and run.requests == 3


async def test_budget_exhaustion_after_fix_run_keeps_the_verified_label_with_the_fix_unverified(tmp_path):
    fake = FakeSandboxes({**HAPPY, ("fixed", "exploit"): Script("errored", "ValueError", "rejected")})
    model = scripted([[("submit", {"submission": REFERENCE.model_dump(mode="json")})], ["Keeping the result."]])
    run = await investigate(load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake,
                            max_submissions=1)
    assert run.verdict.label is Label.LIKELY_EXPLOITABLE and run.verdict.fix.value == "not_verified"
    assert run.evaluations[0].gate.stage is Gate.FIX_RUN and run.error is None
