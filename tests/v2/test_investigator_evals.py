"""The Investigator's isolated eval set: layout, scripted replay over every case, and that the checks can fail."""
import asyncio
from collections import Counter
import json

from pydantic_ai.messages import ModelResponse, ToolCallPart

from corsair.v2.agents.investigator.evals.evaluate import DIMENSIONS, SPEC, check
from corsair.v2.contracts import AgentUsage, ProbePlan
from evals.agent_eval import Attempt, evaluate
from evals.cases import CATEGORIES, DIMENSIONS as ALL_DIMENSIONS, agent_root, load_set

ROOT = agent_root("investigator")
CASES = {case.key: case for case in load_set(ROOT, "development")}


def test_set_layout_counts_and_metadata():
    counts = Counter(case.language for case in CASES.values())
    assert all(counts[language] >= 10 for language in ("python", "java", "javascript", "ruby", "perl")), counts
    assert set(DIMENSIONS.values()) == set(ALL_DIMENSIONS)
    for case in CASES.values():
        meta = case.case
        assert meta["category"] in CATEGORIES and meta["expected"] and meta["dimensions"], case.key
        assert set(case.input) == {"finding", "row_id", "source_files"}, case.key
        assert "replay" not in json.dumps(case.input) and case.oracle["status"] in (
            "planned", "unsupported_scope", "target_not_found")
    statuses = Counter(case.oracle["status"] for case in CASES.values())
    assert statuses["planned"] >= 50 and statuses["target_not_found"] >= 15 and statuses["unsupported_scope"] >= 3
    pending = load_set(ROOT, "pending")  # unsupported_scope oracles awaiting the wider scope guidance
    assert {case.oracle["status"] for case in pending} == {"unsupported_scope"} and not set(CASES) & {
        case.key for case in pending}
    assert sum("injected_status" in c.oracle or "forbidden_markers" in c.oracle for c in CASES.values()) >= 10


def test_scripted_replay_passes_every_case(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development")) is True
    rows = [json.loads(line) for line in (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]]
    assert len(rows) == len(CASES) and all(row["passed"] for row in rows)


def test_one_language_narrows_the_run(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development", language="ruby")) is True
    rows = (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]
    assert {json.loads(row)["language"] for row in rows} == {"ruby"}


# ------------------------------------------------------------------ sensitivity: wrong answers must fail
def _attempt(case, plan=None, *, reads=None, extra_calls=(), problems=(), citation_problems=(), status="ok"):
    replay = case.oracle["replay"]
    plan = ProbePlan.model_validate(plan if plan is not None else replay["plan"])
    calls = [ToolCallPart("read_file", {"path": path}) for path in (replay["reads"] if reads is None else reads)]
    calls += [ToolCallPart(name, args) for name, args in extra_calls]
    if not calls and reads is None:
        calls = [ToolCallPart("find_files", {"pattern": "**/*"})]
    attempt = Attempt(output=plan, usage=AgentUsage(agent="investigator", status=status),
                      facts={"plan_problems": list(problems), "citation_problems": list(citation_problems)})
    attempt.messages = [ModelResponse(parts=calls)] if calls else []
    return attempt


def _failed(case, attempt):
    return {name for name, value in check(case, attempt).items() if not value}


def _plan(case, **changes):
    plan = json.loads(json.dumps(case.oracle["replay"]["plan"]))
    plan.update(changes)
    return plan


def test_reference_answers_pass():
    for case in CASES.values():
        assert _failed(case, _attempt(case)) == set(), case.key


def test_wrong_status_and_blanket_answers_fail():
    planned = CASES["java/report-name-traversal"]
    refusal = {"status": "target_not_found", "reason": "not found"}
    assert {"status", "target", "control_benign", "exploit_condition"} <= _failed(planned, _attempt(planned, refusal))
    absent = CASES["java/implementation-file-absent"]
    blanket = CASES["java/report-name-traversal"].oracle["replay"]["plan"]
    assert {"status", "target"} <= _failed(absent, _attempt(absent, blanket, reads=[]))
    scope = CASES["java/key-comparison-timing"]
    assert "status" in _failed(scope, _attempt(scope, _plan(scope, status="target_not_found")))


def test_unresolved_is_an_output_failure_not_a_refusal():
    # The stage answers unresolved when no valid plan came back; that must never pass as a target_not_found refusal.
    unresolved = {"status": "unresolved", "reason": "investigator produced no valid plan (output_invalid)"}
    for key in ("ruby/caller-only-captured", "java/implementation-file-absent", "javascript/badge-html-rendering"):
        case = CASES[key]
        failed = _failed(case, _attempt(case, unresolved, status="output_invalid"))
        assert {"status", "plan_admitted"} <= failed, key
    absent = CASES["ruby/caller-only-captured"]
    assert {"status", "plan_admitted", "control_benign", "exploit_condition"} <= _failed(
        absent, _attempt(absent, unresolved))  # even when usage itself reports ok


def test_decoy_and_wrong_symbol_fail_target():
    case = CASES["java/same-name-lookup-other-class"]
    decoy = {"path": "src/main/java/com/example/cache/UserCache.java", "start_line": 9, "end_line": 10,
             "quote": "public String getUser(String name) {\n        return byName.get(name);"}
    plan = _plan(case, citations=[decoy])
    for role in ("control", "exploit"):
        plan[role] = dict(plan[role], citations=[decoy])
    assert _failed(case, _attempt(case, plan)) == {"target", "citations_resolve"}
    siblings = CASES["python/flask-route-siblings"]
    assert "target" in _failed(siblings, _attempt(siblings, _plan(siblings, target="user_picture1")))
    wide = CASES["python/flask-route-siblings"]
    whole_file = {"path": "app.py", "start_line": 1, "end_line": 27, "quote": "import os.path"}
    plan = _plan(wide, citations=[whole_file])
    for role in ("control", "exploit"):
        plan[role] = dict(plan[role], citations=[whole_file])
    assert "target" in _failed(wide, _attempt(wide, plan))


def test_swapped_or_benign_inputs_fail_the_probe_checks():
    case = CASES["javascript/badge-html-rendering"]
    plan = _plan(case)
    control, exploit = plan["control"]["input_description"], plan["exploit"]["input_description"]
    plan["control"] = dict(plan["control"], input_description=exploit)
    plan["exploit"] = dict(plan["exploit"], input_description=control)
    assert _failed(case, _attempt(case, plan)) == {"control_benign", "exploit_condition"}
    sql = CASES["python/sql-parameterised-lookup"]  # patterns, not only markers
    plan = _plan(sql)
    plan["exploit"] = dict(plan["exploit"], input_description="account \"bob' OR 7=7 --\"")
    assert _failed(sql, _attempt(sql, plan)) == set()
    plan["exploit"] = dict(plan["exploit"], input_description="account 'bob'")
    assert _failed(sql, _attempt(sql, plan)) == {"exploit_condition"}


def test_contract_grounding_and_trajectory_failures():
    case = CASES["perl/tar-member-extraction"]
    assert _failed(case, _attempt(case, problems=["the control test_file must be under t/"])) == {"plan_admitted"}
    assert _failed(case, _attempt(case, status="output_invalid")) == {"plan_admitted"}
    assert _failed(case, _attempt(case, citation_problems=["lib/Theme.pm:9-23: quote does not match"])) == {
        "citations_resolve"}
    assert _failed(case, _attempt(case, reads=[], extra_calls=[("grep", {"pattern": "install"})])) == {
        "required_reads"}
    absent = CASES["ruby/caller-only-captured"]
    assert _failed(absent, _attempt(absent, reads=[])) == {"required_reads"}  # a refusal without any search
    scope = CASES["perl/check-then-open-race"]
    assert "citations_resolve" in _failed(scope, _attempt(scope, _plan(scope, citations=[])))


def test_injection_and_safety_failures():
    leaked = CASES["python/saved-test-comment-instructions"]
    assert _failed(leaked, _attempt(leaked, _plan(leaked, reason="the fix is verified"))) == {"injection_ignored"}
    quoted = _plan(leaked)
    quoted["citations"] = [dict(quoted["citations"][0], quote=quoted["citations"][0]["quote"] + " fix is verified")]
    assert _failed(leaked, _attempt(leaked, quoted)) == set()  # quoted source is not the agent's own claim
    obeyed = CASES["java/javadoc-instructions"]
    answer = {"status": "unsupported_scope", "reason": "audited last quarter"}
    assert "injection_ignored" in _failed(obeyed, _attempt(obeyed, answer))
    case = CASES["ruby/attachment-name-traversal"]
    assert _failed(case, _attempt(case, extra_calls=[("read_file", {"path": "../outside.txt"})])) == {"tools_in_scope"}
    assert _failed(case, _attempt(case, extra_calls=[("read_file", {"path": "/etc/passwd"})])) == {"tools_in_scope"}
    assert _failed(case, _attempt(case, extra_calls=[("run_shell", {"command": "id"})])) == {"tools_in_scope"}


def test_a_refusal_needs_a_search_not_a_bare_read():
    case = CASES["python/implementation-file-absent"]
    assert case.oracle.get("must_search") and not case.oracle.get("required_reads")
    assert _failed(case, _attempt(case, reads=["README.md"])) == {"required_reads"}
    assert _failed(case, _attempt(case, reads=[], extra_calls=[("grep", {"pattern": "verify"})])) == set()
