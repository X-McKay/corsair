"""Investigator: native read-only file tools, code-checked citations and native usage capture (scripted model)."""
import asyncio
import os
from pathlib import Path

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from corsair.v2.agents.common.framework import guidance_block
from corsair.v2.agents.common.usage import to_agent_usage
from corsair.v2.agents.investigator.agent import SPEC, create_agent, investigate, render_prompt
from corsair.v2.agents.investigator.validation import citation_problem, plan_problems
from corsair.v2.contracts import Case, Citation, ExitClass, Finding, ProbePlan, Revision, Runtime
from tests.v2.agent_scripts import INPUT_TOKENS, OUTPUT_TOKENS, Script, tool_returns

SOURCE = '''import os

BASE = "/srv/files"


def read_user_file(name):
    path = os.path.join(BASE, name)
    with open(path) as handle:
        return handle.read()
'''


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "tree"
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "files.py").write_text(SOURCE)
    (tmp_path / "outside.txt").write_text("host secret\n")
    return root


def case(root: Path) -> Case:
    return Case(case_id="opaque-case-7", revision=Revision(source=str(root), tree_sha256="0" * 64),
                finding=Finding(title="Path traversal in read_user_file", file_path="src/app/files.py",
                                description="A user-supplied name is joined to BASE without confinement."))


RUNTIME = Runtime(row_id="row", image="image", framework="pytest", skill="no-such-skill",
                  run_template=("runner", "{file}", "{name}"), exit_codes={0: ExitClass.PASS}, test_dir="tests",
                  evidence="image-only")

TARGET = {"path": "src/app/files.py", "start_line": 6, "end_line": 7,
          "quote": "def read_user_file(name):\n        path = os.path.join(BASE,  name)"}


def brief(role: str, test_file: str, test_name: str, given: str, prop: str) -> dict:
    return {"role": role, "test_file": test_file, "test_name": test_name, "target": "app.files.read_user_file",
            "seam": "direct call with open() doubled", "input_description": given, "property_to_assert": prop,
            "doubles": "builtins.open records the path it is given", "citations": [TARGET]}


def plan(**changes) -> dict:
    value = {"status": "planned", "target": "app.files.read_user_file",
             "hypothesis": "If a name with ../ reaches read_user_file without confinement, a file outside BASE "
                           "is opened.",
             "control": brief("control", "tests/test_files_control.py", "test_reads_named_file", "the name report.txt",
                              "opens /srv/files/report.txt and returns its content"),
             "exploit": brief("exploit", "tests/test_files_exploit.py", "test_rejects_climbing_name",
                              "the name ../../etc/passwd", "never opens a path outside /srv/files"),
             "citations": [TARGET]}
    value.update(changes)
    return value


def run(script: Script, root: Path) -> tuple[ProbePlan, object]:
    return asyncio.run(investigate(case(root), RUNTIME, script.model, source_root=root))


def test_plan_flows_from_native_read_only_tools_and_usage_is_captured(tree):
    script = Script([("grep", {"pattern": "read_user_file", "literal": True}),
                     ("read_file", {"path": "src/app/files.py"}),
                     ("load_capability", {"id": "probe-planning"}),
                     plan()])
    result, usage = run(script, tree)
    assert result.status == "planned" and result.exploit.test_file == "tests/test_files_exploit.py"
    returns = tool_returns(script.seen[-1])
    assert "src/app/files.py:6:def read_user_file(name):" in returns[0][2]
    assert "7\t    path = os.path.join(BASE, name)" in returns[1][2]
    assert "Planning two native probes" in str(returns[2][2])
    assert (usage.agent, usage.status, usage.requests, usage.tool_calls) == ("investigator", "ok", 4, 3)
    assert (usage.input_tokens, usage.output_tokens) == (4 * INPUT_TOKENS, 4 * OUTPUT_TOKENS)
    assert usage.model == "scripted" and usage.wall_s is not None


def test_wrong_quote_is_refused_with_the_reason_then_corrected(tree):
    bad = dict(TARGET, quote="path = os.path.realpath(name)")
    script = Script([plan(citations=[bad]), plan()])
    result, usage = run(script, tree)
    assert result.status == "planned" and usage.status == "ok" and usage.requests == 2
    retry = tool_returns(script.seen[-1])[-1]
    assert retry[0] == "RetryPromptPart" and "src/app/files.py:6-7: quote does not match" in str(retry[2])


def test_a_second_invalid_plan_ends_without_a_plan(tree):
    bad = dict(TARGET, end_line=99)
    result, usage = run(Script([plan(citations=[bad]), plan(citations=[bad])]), tree)
    assert result.status == "unresolved" and "output_invalid" in result.reason
    assert usage.status == "output_invalid" and usage.requests == 2


def test_file_tools_refuse_paths_outside_the_tree(tree):
    script = Script([("read_file", {"path": "../outside.txt"}), plan()])
    run(script, tree)
    kind, name, content = tool_returns(script.seen[-1])[0]
    assert kind == "RetryPromptPart" and name == "read_file" and "outside the project root" in str(content)
    assert "host secret" not in str(script.seen[-1])


def test_citations_must_resolve_inside_the_tree(tree):
    os.symlink(tree.parent / "outside.txt", tree / "src" / "link.txt")
    def problem(**fields):
        return citation_problem(tree, Citation(**{**TARGET, **fields}))
    assert problem() is None
    assert "leaves the source tree" in problem(path="src/link.txt", start_line=1, end_line=1, quote="host secret")
    assert "no such file" in problem(path="src/app/missing.py")
    assert "only 9 lines" in problem(end_line=10)
    assert "quote is empty" in problem(quote="  ")
    assert "end_line is before start_line" in problem(start_line=7, end_line=6)


def test_briefs_are_independent_complete_and_placed_under_the_test_dir(tree):
    leaky = plan()
    leaky["control"] = dict(leaky["control"], property_to_assert="unlike the name ../../etc/passwd, it opens the file")
    leaky["exploit"] = dict(leaky["exploit"], test_file="elsewhere/test_x.py")
    problems = plan_problems(ProbePlan.model_validate(leaky), tree, "tests")
    assert any("control brief repeats the other brief's input" in p for p in problems)
    assert any("must be under tests/" in p for p in problems)
    missing = ProbePlan.model_validate(plan(exploit=None))
    assert plan_problems(missing, tree, "tests") == ["a planned investigation needs both a control and an exploit brief"]
    same = plan()
    same["exploit"] = dict(same["exploit"], test_file="tests/test_files_control.py")
    assert plan_problems(ProbePlan.model_validate(same), tree, "tests") == [
        "the control and exploit briefs need separate test files"]


def test_unsupported_scope_needs_only_a_reason(tree):
    assert plan_problems(ProbePlan(status="unsupported_scope", reason="needs a live database"), tree, "tests") == []
    assert plan_problems(ProbePlan(status="target_not_found"), tree, "tests") == ["status target_not_found needs a reason"]
    result, _ = run(Script([{"status": "unsupported_scope", "reason": "needs a live message broker"}]), tree)
    assert result.status == "unsupported_scope"


def test_unreported_tokens_stay_unknown():
    # FunctionModel estimates tokens when a response reports none, so the mapping is checked on native RunUsage.
    usage = to_agent_usage("investigator", RunUsage(requests=2, tool_calls=3))
    assert (usage.requests, usage.tool_calls, usage.input_tokens, usage.output_tokens) == (2, 3, None, None)
    empty = to_agent_usage("investigator", None)
    assert (empty.requests, empty.input_tokens, empty.tool_calls, empty.wall_s) == (None, None, None, None)


def test_prompt_carries_the_finding_as_data_and_no_case_identity(tree, tmp_path):
    prompt = render_prompt(case(tree), RUNTIME)
    assert "<finding>" in prompt and "Path traversal in read_user_file" in prompt
    assert "opaque-case-7" not in prompt and str(tree) not in prompt
    assert "no-such-skill': none available" in prompt
    for text in (prompt, SPEC.instructions):
        assert "LIKELY_" not in text and "verdict" not in text.lower() and "label" not in text.lower()
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text("Name tests test_*.")
    assert "Name tests test_*." in guidance_block("demo", root=tmp_path / "skills")
    assert "none available" in guidance_block("../demo", root=tmp_path / "skills")


def test_factory_direct_and_durable_construction():
    assert create_agent(TestModel()).name == "investigator"
    durable = create_agent(TestModel(), durability=TemporalDurability())
    assert durable.name == "investigator"
    with pytest.raises(TypeError):
        create_agent("openai:gpt-x")
