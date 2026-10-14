"""Scripted (no model) checks of the outcome-blind Reviewer: validity computed in code, citations, no outcomes."""
import inspect
import json
from hashlib import sha256

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from corsair.v2.agents import reviewer
from corsair.v2.agents.reviewer.review import ReviewDeps
from corsair.v2.contracts import (Case, Citation, Finding, FrozenPatch, Outcome, ProbeBrief, ProbeDraft, ProbeFacts,
                                  ProbePlan, ProbeRun, Revision)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


CONTROL = ProbeDraft(role="control", test_file="tests/test_ordinary.src", test_name="test_ordinary",
                     source="test_ordinary:\n  marker CORSAIR_MARKER_DIR start\n  check target('a') == 'a'\n  end\n")
EXPLOIT = ProbeDraft(role="exploit", test_file="tests/test_unsafe.src", test_name="test_unsafe",
                     source="test_unsafe:\n  marker CORSAIR_MARKER_DIR start\n  check safe(target('../x')) "
                            "message CORSAIR_TOKEN\n  end\n")
PATCH = FrozenPatch(control=CONTROL, exploit=EXPLOIT, sha256=sha256(b"patch").hexdigest())
CASE = Case(case_id="case-1", finding=Finding(title="Path climbs out of the base", file_path="lib/target.txt"),
            revision=Revision(source="/src", tree_sha256="0" * 64))


def brief(role, draft):
    return ProbeBrief(role=role, test_file=draft.test_file, test_name=draft.test_name, target="target",
                      seam="direct call", input_description="input", property_to_assert="property",
                      citations=(Citation(path="lib/target.txt", start_line=2, end_line=2),))


PLAN = ProbePlan(status="planned", target="target", hypothesis="if a climbing path reaches open without a check",
                 control=brief("control", CONTROL), exploit=brief("exploit", EXPLOIT))


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "target.txt").write_text("line one\nfunction target(name)\nline three\n")
    return tmp_path


def judgement(*, ok=True, defects=(), citations=None, **extra):
    checks = dict(calls_real_target=True, exercises_condition=True, assertion_relevant=ok,
                  doubles_only_dependencies=True)
    return checks | {"defects": list(defects), "citations": citations if citations is not None else [
        {"path": "tests/test_ordinary.src", "start_line": 3, "end_line": 3},
        {"path": "lib/target.txt", "start_line": 2, "end_line": 2}]} | extra


def answering(*answers, seen=None, calls=()):
    answers, calls = list(answers), list(calls)

    async def respond(messages, info: AgentInfo):
        if seen is not None:
            seen.append((messages, info))
        if calls:
            name, args = calls.pop(0)
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart(json.dumps(answers.pop(0) if len(answers) > 1 else answers[0]))])
    return FunctionModel(respond, model_name="scripted")


async def test_valid_is_computed_in_code_and_citations_are_quoted(tree):
    exploit = judgement(ok=False, defects=["the assertion compares a constant"], valid=True,
                        citations=[{"path": "tests/test_unsafe.src", "start_line": 3, "end_line": 3}])
    validity, usage = await reviewer.review(CASE, PLAN, PATCH, answering({"control": judgement(valid=False),
                                                                          "exploit": exploit}),
                                            source_root=tree, revision="fixed")
    assert validity.patch_sha256 == PATCH.sha256 and validity.revision == "fixed"
    assert validity.control.valid is True and validity.exploit.valid is False
    assert validity.exploit.defects == ("the assertion compares a constant",)
    assert validity.control.citations[1].quote == "function target(name)"
    assert validity.exploit.citations[0].quote.strip().startswith("check safe(target('../x'))")
    assert (usage.agent, usage.status, usage.requests) == ("reviewer", "ok", 1)


async def test_unsupported_judgements_are_sent_back(tree):
    seen = []
    bad = [{"control": judgement(citations=[]), "exploit": judgement(ok=False)},
           {"control": judgement(citations=[{"path": "lib/target.txt", "start_line": 9, "end_line": 9}]),
            "exploit": judgement()}]
    good = {"control": judgement(), "exploit": judgement(citations=[
        {"path": "tests/test_unsafe.src", "start_line": 3, "end_line": 3},
        {"path": "lib/target.txt", "start_line": 2, "end_line": 2}])}
    validity, usage = await reviewer.review(CASE, PLAN, PATCH, answering(*bad, good, seen=seen), source_root=tree)
    retries = [str(messages[-1].parts) for messages, _ in seen[1:]]
    assert "must cite" in retries[0] and "needs a defect" in retries[0]
    assert "outside the file" in retries[1]
    assert validity.control.valid and validity.exploit.valid and usage.requests == 3


async def test_a_review_that_does_not_complete_is_negative(tree):
    validity, usage = await reviewer.review(CASE, PLAN, PATCH, answering({"control": judgement(citations=[]),
                                                                          "exploit": judgement(citations=[])}),
                                            source_root=tree)
    assert usage.status == "output_invalid"
    assert not validity.control.valid and not validity.exploit.valid
    assert validity.control.defects == ("review not completed: output_invalid",)


async def test_review_never_receives_outcomes(tree):
    params = set(inspect.signature(reviewer.review).parameters)
    assert params == {"case", "plan", "patch", "model", "source_root", "revision"}
    assert set(ReviewDeps.model_fields) == {"source_root", "drafts"}
    seen = []
    model = answering({"control": judgement(), "exploit": judgement(citations=[
        {"path": "tests/test_unsafe.src", "start_line": 3, "end_line": 3},
        {"path": "lib/target.txt", "start_line": 2, "end_line": 2}])}, seen=seen,
        calls=[("read_file", {"path": "lib/target.txt"}), ("search_files", {"pattern": "target"})])
    await reviewer.review(CASE, PLAN, PATCH, model, source_root=tree, revision="vulnerable")
    text = " ".join(str(messages) + str(info.instructions) for messages, info in seen).lower()
    outcome_words = (set(ProbeFacts.model_fields) | set(ProbeRun.model_fields) - {"role", "output"}
                     | {o.value for o in Outcome} | {"vulnerable", "fixed revision"})
    assert not [word for word in outcome_words if word in text]
    assert "3:   check safe(target('../x'))" in text and "function target(name)" in text


def test_factory_constructs_in_direct_and_durable_modes():
    agent = reviewer.create_agent(TestModel())
    durable = reviewer.create_agent(TestModel(), durability=TemporalDurability(models={"m": TestModel()}))
    assert agent.name == durable.name == "reviewer"
