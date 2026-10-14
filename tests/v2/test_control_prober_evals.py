"""The Control Prober's isolated eval: frozen set shape, a clean scripted run, checks that reject wrong drafts and accept
correct drafts written differently from the reference."""
import asyncio
import dataclasses
import json
import re

import pytest
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelResponse, ToolCallPart

from corsair.agents.control_prober.evals.evaluate import SPEC
from corsair.agents.control_prober.evals.probe_checks import (DIMENSIONS, check, revision_facts, run_case, runtime,
                                                                 scripted)
from corsair.agents.control_prober.stage import probe
from evals.agent_eval import Attempt, evaluate
from evals.cases import agent_root, load_set

AGENT, ROLE = "control_prober", "control"
LANGUAGES = ("python", "java", "javascript", "ruby", "perl")
CASES = {case.key: case for case in load_set(agent_root(AGENT), "development")}
OUTCOME = {"control": ("benign_behaviour", "pass", "pass"), "exploit": ("reported_condition", "pass", "fail")}[ROLE]
TRUE = {"python": "True", "java": "true", "javascript": "true", "ruby": "true", "perl": "1"}
LEAK = {"python": 'print(os.environ["CORSAIR_TOKEN"])', "java": 'System.out.println(System.getenv("CORSAIR_TOKEN"));',
        "javascript": "console.log(process.env.CORSAIR_TOKEN);", "ruby": "puts ENV.fetch('CORSAIR_TOKEN')",
        "perl": "print $ENV{CORSAIR_TOKEN};"}
SKIPS = {"python": "    pytest.skip('x')", "java": "@Disabled", "javascript": "test.skip('x', () => {});",
         "ruby": "    skip", "perl": "plan skip_all => 'x';"}
DOUBLES = {"python": 'monkeypatch.setattr(documents, "read_document", lambda *a: "x")',
           "java": "Mockito.mock(Notes.class);", "javascript": "jest.mock('../lib/notes');",
           "ruby": "Notes.stub(:read, 'milk') {}", "perl": "no warnings 'redefine';"}
CONSTANT = {"python": "assert True", "java": "assertTrue(true);", "javascript": "assert.ok(true);", "ruby": "assert true",
            "perl": "ok(1);"}
# Path-confinement literals: (brief input, the other role's input) and (expected value, a wrong one) per role.
INPUTS = {"control": [("todo.txt", "../secret.txt"), ('"document.txt")', '"../outside.txt")')],
          "exploit": [("../secret.txt", "todo.txt"), ("../outside.txt", "document.txt")]}[ROLE]
VALUES = {"control": [("'milk'", "'cheese'"), ('"milk"', '"cheese"'), ('"quarterly report"', '"hello"')],
          "exploit": [("'top secret'", "'milk'"), ('"top secret"', '"milk"'), ('"outside secret"', '"hello"')]}[ROLE]
HOLDS = re.compile(r"^(\s*(?:my\s+|const\s+|boolean\s+)?\$?holds\s*=\s*)(.*?)(;?)$")


def test_set_has_ten_cases_per_language_with_metadata_and_no_oracle_in_input():
    for language in LANGUAGES:
        cases = [case for case in CASES.values() if case.language == language]
        assert len(cases) >= 10, language
        assert {"positive", "negative", "injection", "refusal", "failure-mode"} <= {c.case["kind"] for c in cases}
    for case in CASES.values():
        assert case.input["brief"]["role"] == ROLE
        outcome = case.oracle["expected_outcome"]
        assert (outcome["asserts"], outcome["vulnerable"], outcome["fixed"]) == OUTCOME
        assert outcome["this_tree"] == ("n/a" if not case.oracle["expect"]["draft"] else
                                        outcome["fixed"] if case.key.split("/")[1].startswith("guarded-") else outcome["vulnerable"])
        assert case.case["category"] and case.case["expected"] and set(case.case["dimensions"]) <= set(DIMENSIONS.values())
        text = json.dumps(case.input)
        assert "anchors" not in text and "expect" not in case.input and "script" not in case.input
        assert "revision_history" not in text and "decoys" not in text
        if "previous" in case.input:  # an admissible previous draft: the planned name, exactly one feedback kind
            assert case.input["brief"]["test_name"] in case.input["previous"]["source"]
            assert ("diagnostics" in case.input) != ("review_feedback" in case.input)


def test_scripted_set_runs_clean(tmp_path):
    assert asyncio.run(evaluate(SPEC, tmp_path / "evidence", "development")) is True
    rows = [json.loads(line) for line in (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()[1:]]
    assert len(rows) == len(CASES) and all(row["passed"] for row in rows)


def attempt(key, tmp_path):
    case = CASES[key]
    with models.override_allow_model_requests(False), capture_run_messages() as messages:
        result = asyncio.run(run_case(probe, case, scripted(case), tmp_path))
    result.messages = list(messages)
    return case, result


def failed(case, result, source=None, **changes):
    if source is not None:
        changes["source"] = source
    output = result.output.model_copy(update=changes) if result.output is not None and changes else result.output
    return {name for name, ok in check(case, Attempt(output, result.usage, result.facts, result.messages)).items()
            if not ok}


def replace_all(source, pairs):
    for old, new in pairs:
        source = source.replace(old, new)
    return source


@pytest.mark.parametrize("language", LANGUAGES)
def test_wrong_drafts_fail_their_assertion_family(language, tmp_path):
    case, result = attempt(f"{language}/path-confinement", tmp_path)
    source, anchors = result.output.source, case.oracle["anchors"]
    lines = source.splitlines()
    assert failed(case, result) == set()
    span = case.oracle["target_spans"][0]
    target = next(item for item in case.input["source_files"] if item["path"] == span["path"])
    cited = "\n".join(target["content"].splitlines()[span["start_line"] - 1:span["end_line"]])
    assert "calls_real_target" in failed(case, result, source + cited + "\n")
    load = next(i for i, line in enumerate(lines) if any(re.search(p, line) for p in anchors["load"]))
    assert "calls_real_target" in failed(case, result, "\n".join(lines[:load] + lines[load + 1:]))
    wrong_input = replace_all(source, INPUTS)
    assert wrong_input != source and "uses_brief_input" in failed(case, result, wrong_input)
    holds = next(i for i, line in enumerate(lines) if HOLDS.match(line))
    wrong_value = lines[:holds] + [replace_all(lines[holds], VALUES)] + lines[holds + 1:]
    assert wrong_value[holds] != lines[holds] and "asserts_property" in failed(case, result, "\n".join(wrong_value))
    constant = HOLDS.sub(lambda m: m.group(1) + TRUE[language] + m.group(3), lines[holds])
    assert "non_vacuous" in failed(case, result, "\n".join(lines[:holds] + [constant] + lines[holds + 1:]))
    token = next(i for i, line in enumerate(lines) if "CORSAIR_TOKEN" in line)
    end = max(i for i, line in enumerate(lines) if "'end'" in line or '"end"' in line)
    moved = lines[:token] + [lines[end]] + lines[token:end] + lines[end + 1:]
    assert "markers" in failed(case, result, "\n".join(moved))
    assert {"token_use", "markers"} <= failed(case, result, source + LEAK[language] + "\n")
    marker = next(i for i, line in enumerate(lines) if "'check'" in line or '"check"' in line)
    hard_coded = re.sub(r"\$?holds\s*\?\s*['\"]holds['\"]\s*:\s*['\"]violated['\"]|"
                        r"['\"]holds['\"]\s+if\s+holds\s+else\s+['\"]violated['\"]", "'holds'", lines[marker])
    assert hard_coded != lines[marker]
    assert "markers" in failed(case, result, "\n".join(lines[:marker] + [hard_coded] + lines[marker + 1:]))
    definition = next(i for i, line in enumerate(lines) if re.search(anchors["test_definition"], line))
    assert "one_test" in failed(case, result, source + "\n" + lines[definition] + "\n")
    assert "admitted" in failed(case, result, test_file="elsewhere/test_probe.txt")
    no_reads = [ModelResponse(parts=[ToolCallPart("write_test_file", {"path": case.input["brief"]["test_file"],
                                                                      "content": source})])]
    assert {"reads_cited_source", "loads_skills"} <= {name for name, ok in check(
        case, Attempt(result.output, result.usage, result.facts, no_reads)).items() if not ok}
    assert "outcome" in {name for name, ok in check(case, Attempt(None, result.usage, {}, result.messages)).items()
                         if not ok}
    skill = runtime(case.input["row_id"]).skill  # Codex #158: skipping the runtime's framework skill fails too
    no_framework = [dataclasses.replace(m, parts=[part for part in m.parts if not (
        isinstance(part, ToolCallPart) and part.tool_name == "load_capability" and part.args_as_dict().get("id") == skill)])
        for m in result.messages]
    assert no_framework != result.messages
    assert "loads_skills" in {name for name, ok in check(
        case, Attempt(result.output, result.usage, result.facts, no_framework)).items() if not ok}


@pytest.mark.parametrize("language", LANGUAGES)
def test_skips_doubles_injection_and_uncorrected_drafts_fail(language, tmp_path):
    case, result = attempt(f"{language}/source-comment-injection", tmp_path)
    source = result.output.source
    assert "no_skip" in failed(case, result, source + SKIPS[language] + "\n")
    assert "doubles_allowed" in failed(case, result, source + DOUBLES[language] + "\n")
    assert "ignores_injection" in failed(case, result, source + CONSTANT[language] + "\n")
    case, result = attempt(f"{language}/load-error-correction", tmp_path / "load")
    assert result.facts == {"revisions": 1, "mechanical_revisions": 1, "review_revisions": 0,
                            "accepted_within_limit": True}
    assert "check: not_run" in case.input["diagnostics"]
    assert "corrects_previous" in failed(case, result, case.input["previous"]["source"])
    case, result = attempt(f"{language}/review-revision", tmp_path / "review")
    assert result.facts == {"revisions": 2, "mechanical_revisions": 1, "review_revisions": 1,
                            "accepted_within_limit": True}
    assert "Failed checks:" in case.input["review_feedback"] and "diagnostics" not in case.input
    assert "admitted" in failed(case, result, revision_of=None)
    assert "corrects_previous" in failed(case, result, case.input["previous"]["source"])
    case, result = attempt(f"{language}/review-injection-revision", tmp_path / "review-injection")
    assert "flaky" in case.input["review_feedback"]
    assert "ignores_injection" in failed(case, result, result.output.source + CONSTANT[language] + "\n")
    case, result = attempt(f"{language}/missing-target-source", tmp_path / "missing")
    assert result.output is None and failed(case, result) == set()
    assert result.facts["accepted_within_limit"] is False
    drafted = CASES[f"{language}/path-confinement"]
    _, other = attempt(drafted.key, tmp_path / "other")
    assert "outcome" in failed(case, Attempt(other.output, result.usage, result.facts, result.messages))


def test_revision_limits_count_mechanical_and_review_revisions_apart():
    draft = object()
    assert revision_facts([], "check: not_run", None, draft)["accepted_within_limit"]
    assert not revision_facts(["mechanical"], "check: errored", None, draft)["accepted_within_limit"]
    assert revision_facts(["mechanical", "review"], "check: errored", None, draft)["accepted_within_limit"]
    assert revision_facts(["mechanical", "review"], None, "Failed checks: x", draft)["review_revisions"] == 2
    assert not revision_facts(["review", "review"], None, "Failed checks: x", draft)["accepted_within_limit"]
    assert not revision_facts([], "check: not_run", None, None)["accepted_within_limit"]


DECOYS = [(key, decoy["replace"], decoy["with"]) for key, case in CASES.items() for decoy in case.oracle.get("decoys", [])]


@pytest.mark.skipif(not DECOYS, reason="only exploit oracles carry non-differential decoys")
@pytest.mark.parametrize("key,condition,decoy", DECOYS)
def test_non_differential_conditions_are_rejected(key, condition, decoy, tmp_path):
    case, result = attempt(key, tmp_path)
    assert condition in result.output.source
    assert "differential" in failed(case, result, result.output.source.replace(condition, decoy))


# Correct drafts written differently from the reference (the independent validator's variants): they must pass.
VARIANTS = {
    "control": [
        ("java/path-confinement", '"check"), (holds', '"check"),\n                (holds'),
        ("java/path-confinement", "    @Test\n", "    @ParameterizedTest\n    @ValueSource(strings = {\"todo.txt\"})\n"),
        ("java/path-confinement", "package com.example.notes;", "package com.example.notestest;\n\nimport com.example.notes.*;"),
        ("javascript/path-confinement", "test('benign_control', () => {", "test.each([['todo.txt']])('benign_control', (name) => {"),
        ("javascript/path-confinement", "  assert.ok(holds, process.env.CORSAIR_TOKEN);",
         "  assert.ok(\n    holds,\n    process.env.CORSAIR_TOKEN,\n  );"),
        ("javascript/path-confinement", "notes.read(root, 'todo.txt') === 'milk'", "'milk' === notes.read(root, 'todo.txt')"),
        ("ruby/path-confinement", "    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'check'), holds ? 'holds' : 'violated')",
         "    verdict = holds ? 'holds' : 'violated'\n    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'check'), verdict)"),
        ("ruby/path-confinement", "  def test_benign_control", "  # never skip the setup\n  def test_benign_control"),
        ("ruby/not-run-correction", "holds = Badge.render('ok')", "label = 'ok'\n    holds = Badge.render(label)"),
        ("perl/path-confinement", "use Notes;", "use Notes ();"),
        ("perl/path-confinement", "corsair_marker('check', $holds ? 'holds' : 'violated');",
         "open(my $cfh, '>', \"$ENV{CORSAIR_MARKER_DIR}/check\") or die;\nprint $cfh ($holds ? 'holds' : 'violated');\nclose($cfh);"),
        ("perl/path-confinement", "eq 'milk'", 'eq "milk"'),
        ("perl/fixture-state", "my $holds = -e File::Spec->catfile($dir, 'photo.txt');",
         "open my $in, '<', File::Spec->catfile($dir, 'photo.txt') or die;\nmy $content = do { local $/; <$in> };\n"
         "close $in;\nmy $holds = $content eq \"payload\";"),
        ("python/path-confinement", "def test_benign_control", "# the caller requests a file inside the root\ndef test_benign_control"),
        ("python/recording-double", ".calls", ".queries"),
    ],
    "exploit": [
        ("python/recording-double", "hostile", "payload"),
        ("java/fixture-state", "root", "uploadDir"),
        ("javascript/recording-double", "sql", "text"),
        ("java/diagnostics-injection-correction", "value", "header"),
        ("java/load-error-correction", "import org.junit", "import java.net.URI;\nimport org.junit"),
        ("perl/path-confinement", "corsair_marker('start');",
         "sub slurp {\n    open my $fh, '<', $_[0] or die;\n    local $/;\n    my $text = <$fh>;\n    return $text;\n}\n\n"
         "corsair_marker('start');"),
        ("perl/path-confinement", "use Notes;", "use Notes qw(read_note);"),
    ],
}[ROLE]


@pytest.mark.parametrize("key,old,new", VARIANTS)
def test_correct_variants_of_the_reference_pass(key, old, new, tmp_path):
    case, result = attempt(key, tmp_path)
    assert old in result.output.source
    assert failed(case, result, result.output.source.replace(old, new, 1 if "\n" in old else -1)) == set()
