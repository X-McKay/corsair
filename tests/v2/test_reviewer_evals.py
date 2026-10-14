"""The Reviewer's isolated eval: frozen set shape, a clean scripted run, and checks that reject wrong answers.

A passing scripted run proves plumbing and oracle consistency only; these tests make sure the checks would fail a
wrong answer, so that a pass means something.
"""
import asyncio
import json
import tempfile
from collections import Counter
from pathlib import Path

import pytest
from pydantic_ai import capture_run_messages, models

from corsair.agents.reviewer.evals.evaluate import (
    DIMENSIONS,
    OPTIONAL,
    SPEC,
    check,
    run,
    scripted,
)
from corsair.agents.reviewer.review import CHECKS
from corsair.contracts import Citation
from evals.agent_eval import evaluate
from evals.cases import CATEGORIES, agent_root, load_set

LANGUAGES = ("python", "java", "javascript", "ruby", "perl")
CASES = load_set(agent_root("reviewer"), "development")
BY_KEY = {case.key: case for case in CASES}
PROBERS = Path(__file__).parents[2] / "src/corsair/agents"


def _attempt(case):
    async def go():
        with capture_run_messages() as messages, models.override_allow_model_requests(False), \
                tempfile.TemporaryDirectory() as workdir:
            attempt = await run(case, scripted(case), Path(workdir))
        attempt.messages = list(messages)
        return attempt
    return asyncio.run(go())


def _with(attempt, **roles):
    validity = attempt.output.model_copy(update={role: getattr(attempt.output, role).model_copy(update=changes)
                                                 for role, changes in roles.items()})
    return type(attempt)(output=validity, usage=attempt.usage, facts=attempt.facts, messages=attempt.messages)


def _outcome(case):
    if "failure_status" in case.oracle:
        return "failure-mode"
    return "valid" if all(role["valid"] for role in case.oracle["expected"].values()) else "rejected"


def _prober_drafts():
    """Every draft an accepted prober case holds: reference writes, previous drafts and refused first writes."""
    drafts = set()
    for agent in ("control_prober", "exploit_prober"):
        for case in load_set(agent_root(agent), "development"):
            drafts |= {step["args"]["content"] for step in case.oracle["script"] if step.get("tool") == "write_test_file"}
            if case.input.get("previous"):
                drafts.add(case.input["previous"]["source"])
    return drafts


def test_set_shape_counts_and_no_oracle_in_input():
    for language in LANGUAGES:
        cases = [case for case in CASES if case.language == language]
        outcomes = Counter(_outcome(case) for case in cases)
        assert len(cases) >= 10 and outcomes["valid"] >= 5 and outcomes["rejected"] >= 5, (language, outcomes)
        assert outcomes["failure-mode"] == 1
        assert set(CATEGORIES) <= {case.case["category"] for case in cases}, language
        assert {"positive", "negative", "injection", "failure-mode"} <= {case.case["kind"] for case in cases}
    for case in CASES:
        meta, expected = case.case, case.oracle["expected"]
        assert meta["expected"] and meta["probes"] and set(meta["dimensions"]) <= set(DIMENSIONS.values())
        assert ("safety" in meta["dimensions"]) == any(not role["valid"] for role in expected.values())
        assert ("robustness" in meta["dimensions"]) == case.oracle["injection"]
        assert "valid" not in case.name.split("-")
        assert set(case.input) == {"row_id", "finding", "plan", "patch", "source_files"}
        text = json.dumps(case.input)
        for word in ("expected", "defect_lines", "decoy", "scripted", "oracle", "failure_status"):
            assert word not in text, (case.key, word)
        for role, judged in expected.items():
            draft = case.input["patch"][role]
            assert draft["role"] == role and case.input["plan"][role]["test_file"] == draft["test_file"]
            if judged["valid"]:
                assert judged["failed"] == []
            else:
                assert judged["failed"] and set(judged["failed"]) <= set(CHECKS)
                start, end = judged["defect_lines"]
                assert 1 <= start <= end <= len(draft["source"].splitlines())


def test_valid_probes_are_accepted_prober_drafts_unchanged():
    """The hard boundary: a probe the oracle accepts is byte-identical to an accepted prober draft."""
    accepted = _prober_drafts()
    for case in CASES:
        for role, judged in case.oracle["expected"].items():
            if judged["valid"]:
                assert case.input["patch"][role]["source"] in accepted, (case.key, role)


def test_scripted_run_over_the_whole_set_is_clean(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development")) is True
    rows = [json.loads(line) for line in (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]]
    assert len(rows) == len(CASES)
    statuses = Counter(row["status"] for row in rows)
    assert statuses == {"ok": len(CASES) - len(LANGUAGES), "output_invalid": len(LANGUAGES)}


def test_language_narrowing(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development", language="perl")) is True
    rows = (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]
    assert len(rows) == sum(case.language == "perl" for case in CASES)


NEGATIVE = "java/exploit-asserts-bound-parameter"
CONTROL_NEGATIVE = "ruby/control-sends-adversarial-input"
POSITIVE = "javascript/recording-double-pair"


@pytest.fixture(scope="module")
def negative():
    return _attempt(BY_KEY[NEGATIVE])


@pytest.fixture(scope="module")
def positive():
    return _attempt(BY_KEY[POSITIVE])


APPROVE = {name: True for name in CHECKS} | {"valid": True, "defects": ()}


def test_blanket_approval_is_a_dangerous_false_approval(negative):
    case = BY_KEY[NEGATIVE]
    assert all(check(case, negative).values())
    values = check(case, _with(negative, exploit=APPROVE))
    assert values["no_false_approval"] is False and values["exploit_judged"] is False
    assert values["control_judged"] is True
    control_case = BY_KEY[CONTROL_NEGATIVE]
    attempt = _attempt(control_case)
    assert check(control_case, _with(attempt, control=APPROVE))["no_false_approval"] is False


def test_blanket_rejection_fails_correctness_but_is_not_unsafe(positive):
    case = BY_KEY[POSITIVE]
    reject = {"valid": False, "assertion_relevant": False, "defects": ("unsure",)}
    values = check(case, _with(positive, control=reject, exploit=reject))
    assert values["control_judged"] is False and values["exploit_judged"] is False
    assert values["no_false_approval"] is True


def test_rejection_for_the_wrong_reason_fails_correctness(negative):
    case = BY_KEY[NEGATIVE]
    wrong = {"assertion_relevant": True, "exercises_condition": False}
    assert check(case, _with(negative, exploit=wrong))["exploit_judged"] is False
    assert check(case, _with(negative, exploit={"defects": ()}))["exploit_judged"] is False
    # Codex #165: rejecting with every check false is not the right reason either
    blanket = {name: False for name in CHECKS}
    assert check(case, _with(negative, exploit=blanket))["exploit_judged"] is False


def test_citations_must_resolve_and_point_where_the_judgement_rests(negative, positive):
    case = BY_KEY[POSITIVE]
    cited = positive.output.control.citations[0]
    altered = Citation(path=cited.path, start_line=cited.start_line, end_line=cited.end_line, quote="not the text")
    assert check(case, _with(positive, control={"citations": (altered,)}))["citations_resolve"] is False
    own = case.input["patch"]["exploit"]["test_file"]
    tests_only = tuple(c for c in positive.output.exploit.citations if c.path == own)
    assert check(case, _with(positive, exploit={"citations": tests_only}))["citations_resolve"] is False
    # Codex #165: a valid probe's own-file citation must cover its call of the target and its assertion
    lines = case.input["patch"]["exploit"]["source"].splitlines()
    first = Citation(path=own, start_line=1, end_line=1, quote=lines[0])
    others = tuple(c for c in positive.output.exploit.citations if c.path != own)
    assert check(case, _with(positive, exploit={"citations": (first,) + others}))["citations_resolve"] is False
    case = BY_KEY[NEGATIVE]
    start, _ = case.oracle["expected"]["exploit"]["defect_lines"]
    elsewhere = Citation(path=case.input["patch"]["exploit"]["test_file"], start_line=1, end_line=1,
                         quote=case.input["patch"]["exploit"]["source"].splitlines()[0])
    assert start > 1
    assert check(case, _with(negative, exploit={"citations": (elsewhere,)}))["citations_resolve"] is False


def test_feedback_must_fit_d13(negative, positive):
    case = BY_KEY[NEGATIVE]
    assert check(case, negative)["feedback_actionable"] is True
    assert "feedback_actionable" not in check(BY_KEY[POSITIVE], positive)
    five = tuple(f"defect {n}" for n in range(5))
    assert check(case, _with(negative, exploit={"defects": five}))["feedback_actionable"] is False
    other = case.input["patch"]["control"]["test_file"]
    other_only = tuple(c for c in negative.output.control.citations if c.path == other)
    assert check(case, _with(negative, exploit={"citations": other_only}))["feedback_actionable"] is False


def test_no_source_read_no_skills_bad_status_or_digest_fail(positive):
    case = BY_KEY[POSITIVE]
    unread = type(positive)(output=positive.output, usage=positive.usage, facts=positive.facts, messages=[])
    values = check(case, unread)
    assert values["read_target_source"] is False and values["loads_skills"] is False
    failed = type(positive)(output=positive.output, usage=positive.usage.model_copy(update={"status": "output_invalid"}),
                            facts=positive.facts, messages=positive.messages)
    assert check(case, failed)["review_completed"] is False
    rebound = type(positive)(output=positive.output, usage=positive.usage,
                             facts=positive.facts | {"patch_sha256": "0" * 64}, messages=positive.messages)
    assert check(case, rebound)["review_completed"] is False


@pytest.mark.parametrize("key, role", [("python/path-read-pair-comment-instructions", "exploit"),
                                       ("ruby/exploit-skipped-as-repository-note-asks", "exploit")])
def test_following_an_injected_instruction_fails_robustness(key, role):
    case = BY_KEY[key]
    attempt = _attempt(case)
    assert check(case, attempt)["injection_resisted"] is True
    if case.oracle["expected"][role]["valid"]:
        flipped = {"valid": False, "exercises_condition": False, "defects": ("the repository says it is unnecessary",)}
    else:
        flipped = APPROVE
    assert check(case, _with(attempt, **{role: flipped}))["injection_resisted"] is False


def test_failure_mode_ends_not_reviewed_and_a_completed_review_is_judged_normally():
    case = BY_KEY["python/review-output-retries-exhausted"]
    attempt = _attempt(case)
    assert attempt.usage.status == "output_invalid" and all(check(case, attempt).values())
    assert not attempt.output.control.valid and not attempt.output.exploit.valid
    completed = _attempt(BY_KEY["python/path-read-pair"])
    as_live = type(completed)(output=completed.output.model_copy(update={"patch_sha256": attempt.facts["patch_sha256"]}),
                              usage=completed.usage, facts=attempt.facts | {"source_root": completed.facts["source_root"]},
                              messages=completed.messages)
    values = check(case, as_live)
    assert values["review_completed"] and values["control_judged"] and values["exploit_judged"]


def test_second_review_drafts_name_the_drafts_they_revise():
    for language in LANGUAGES:
        for name in ("second-review-revised-pair", "second-review-revised-exploit-still-invalid"):
            patch = BY_KEY[f"{language}/{name}"].input["patch"]
            assert patch["control"]["revision_of"] and patch["exploit"]["revision_of"]


def test_every_declared_assertion_is_reported_or_optional():
    assert OPTIONAL <= set(DIMENSIONS)
