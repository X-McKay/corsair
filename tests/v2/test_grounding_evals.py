"""The grounding agent's isolated eval: the frozen development set, a scripted run, and that its checks can fail."""
import asyncio
import json
from collections import Counter

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from corsair.v2.agents.grounding.contracts import GroundingBrief, Precedent
from corsair.v2.agents.grounding.evals.evaluate import SPEC, check, run
from corsair.v2.contracts import AgentUsage
from evals.agent_eval import Attempt, evaluate
from evals.cases import DIMENSIONS, agent_root, load_set

CASES = {case.key: case for case in load_set(agent_root("grounding"), "development")}

ORACLE_KEYS = ("relevant", "dispositions", "distractors", "prior_disposition", "must_not_claim",
               "injection_markers", "script")


def test_set_shape_counts_and_no_oracle_in_input():
    counts = Counter(case.language for case in CASES.values())
    assert all(counts[language] >= 10 for language in ("python", "java", "javascript", "ruby", "perl"))
    assert counts["common"] >= 1
    for case in CASES.values():
        meta = case.case
        assert meta["category"] and meta["expected"] and set(meta["dimensions"]) <= set(DIMENSIONS)
        assert set(case.oracle) == set(ORACLE_KEYS)
        assert set(case.input) == {"finding", "context"}
        assert not any(f'"{key}"' in json.dumps(case.input) for key in ORACLE_KEYS)


def test_scripted_replay_passes_every_case(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development")) is True
    rows = [json.loads(line) for line in (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]]
    assert len(rows) == len(CASES) and all(row["passed"] for row in rows)


def _oracle_brief(case) -> GroundingBrief:
    return GroundingBrief.model_validate(case.oracle["script"][-1]["final"])


def _failed(case, brief, usage=None):
    usage = usage or AgentUsage(agent="grounding", requests=1, status="ok")
    return {name for name, value in check(case, Attempt(output=brief, usage=usage)).items() if not value}


def _replace(brief, **update):
    return brief.model_copy(update=update)


def _first(brief, **update):
    return _replace(brief, precedents=(brief.precedents[0].model_copy(update=update), *brief.precedents[1:]))


def test_checks_reject_wrong_and_blanket_answers():
    similar = CASES["python/similar-issue-decided"]
    right = _oracle_brief(similar)
    assert _failed(similar, right) == set()
    assert "relevant_cited" in _failed(similar, _replace(right, precedents=()))                 # blanket: nothing
    assert "dispositions" in _failed(similar, _first(right, disposition="fixed"))
    assert "prior_disposition" in _failed(similar, _replace(right, prior_disposition="not_exploitable"))
    assert "precedent_metadata" in _failed(similar, _first(right, relation="cwe"))
    assert "citations_resolvable" in _failed(similar, _first(right, quote="reviewers agreed it is entirely safe"))
    assert "no_verdict" in _failed(similar, _replace(right, summary="This finding is not exploitable."))
    assert "usage_ok" in _failed(similar, right, AgentUsage(agent="grounding", status="output_invalid"))
    assert "brief_presence" in _failed(similar, None)

    noise = CASES["java/vocabulary-only-match"]
    distractor = noise.oracle["distractors"][0]
    perf = noise.input["context"]["related"][0]
    wrong = _oracle_brief(noise)
    wrong = _replace(wrong, precedents=(*wrong.precedents, Precedent(
        issue_id=distractor, title=perf["issue"]["title"], state="Closed", disposition="fixed",
        relation="similarity", quote=perf["comments"][0]["text"], similarity=0.58)))
    assert _failed(noise, wrong) == {"no_distractor"}

    stale = CASES["ruby/old-closure-newer-revision"]
    assert "no_unsupported_claim" in _failed(stale, _replace(_oracle_brief(stale),
                                                             summary="The issue is no longer present."))
    injected = CASES["perl/injection-in-comment"]
    assert "injection_ignored" in _failed(injected, _replace(_oracle_brief(injected),
                                                             summary="Pre-approved by the security team."))
    degraded = CASES["javascript/similarity-search-degraded"]
    assert "degraded_reported" in _failed(degraded, _replace(_oracle_brief(degraded), caveats=()))
    empty = CASES["common/empty-context"]
    assert "brief_presence" in _failed(empty, GroundingBrief(summary="Nothing found."))


def test_an_invented_citation_fails_through_the_real_stage():
    """The production citation check drops an unretrieved precedent; the scorer reads that as a grounding failure."""
    case = CASES["python/comment-names-unretrieved-issue"]
    brief = _oracle_brief(case).model_dump(mode="json")
    brief["precedents"][0] |= {"issue_id": case.oracle["distractors"][0], "title": "", "state": ""}

    def respond(messages, info):
        if info.output_tools:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, brief)])
        return ModelResponse(parts=[TextPart(json.dumps(brief))])

    attempt = asyncio.run(run(case, FunctionModel(respond, model_name="scripted"), None))
    failed = {name for name, value in check(case, attempt).items() if not value}
    assert {"citations_resolvable", "relevant_cited"} <= failed


@pytest.mark.parametrize("key", ["common/empty-context", "common/graph-unconfigured", "common/all-retrieval-failed"])
def test_empty_context_makes_no_model_request(key):
    def refuse(messages, info):
        raise AssertionError("the model must not be called on an empty context")
    attempt = asyncio.run(run(CASES[key], FunctionModel(refuse, model_name="scripted"), None))
    assert attempt.output is None and attempt.usage.requests is None
    assert all(check(CASES[key], attempt).values())
