"""Whole-repository source tree, bounded tools and repository-mode identification (SPEC-0038), offline."""

import hashlib

import pytest
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.issue_analysis.identification_contracts import IssueIdentification
from corsair.agents.issue_analysis.repository_identification import (
    SKILL_TEXT, RepositoryDependencies, RepositoryIssueInput, create_repository_identification_agent,
    repository_identification_prompt,
)
from corsair.agents.source import (
    RepeatedRead, RepositoryLimits, SourceFile, SourceListing, SourceRead, SourceSearch, SourceTree, UnreadableSource,
)
from corsair.agents.source.repository import list_tree, search_tree
from corsair.ports.artifacts import SourceFile as SnapshotFile, SourceSnapshot

COMMIT, TREE = "a" * 40, "b" * 40
SERVLET = "\n".join([
    "package org.example;",
    "",
    "public class PageServlet {",
    "    public void doGet(Request req, Response res) {",
    "        String page = constructor.getForwardPage(req);",
    "        req.getDispatcher(page).forward(req, res);",
    "    }",
    "}",
]) + "\n"
CONSTRUCTOR = "\n".join([
    "package org.example.url;",
    "",
    "public class UrlConstructor {",
    "    public String getForwardPage(Request request) {",
    "        return request.getPathInfo();",
    "    }",
    "}",
]) + "\n"
FILES = {
    "README.md": "Example wiki. See PageServlet.\n",
    "core/src/main/java/org/example/PageServlet.java": SERVLET,
    "core/src/main/java/org/example/url/UrlConstructor.java": CONSTRUCTOR,
    "core/src/test/java/org/example/PageServletTest.java": "class PageServletTest { /* doGet */ }\n",
    "docs/guide.txt": "Line one\r\nline TWO\r\n",
}
ISSUE = "A request path can steer the page servlet's forward target to a resource under the web root."


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def tree(files=FILES, identity=(COMMIT, TREE)):
    return SourceTree.from_files(tuple(SourceFile(path=p, content=c) for p, c in files.items()), identity)


def raw(files):
    data = {path: content.encode() for path, content in files.items()}
    return SourceTree({path: len(content) for path, content in data.items()}, data.__getitem__)


def inputs(**change):
    return RepositoryIssueInput.model_validate({"case_id": "hidden-case-7", "issue": ISSUE, "scope": "component",
                                                "repository": {"commit": COMMIT, "tree": TREE}} | change)


def test_lines_use_newlines_and_crlf_and_reject_unreadable_files():
    limits = RepositoryLimits()
    source = tree()
    assert source.lines("docs/guide.txt", limits) == ("Line one", "line TWO")
    assert len(source.lines("core/src/main/java/org/example/PageServlet.java", limits)) == 8
    odd = SourceTree({"a.bin": 3, "b.txt": 2, "c.txt": 5, "d.txt": 9}, {
        "a.bin": b"a\0b", "b.txt": b"\xff\xfe", "c.txt": b"x\x0cy\nz", "d.txt": b"123456789"}.__getitem__)
    assert odd.lines("c.txt", limits) == ("x\x0cy", "z")  # form feed is content, not a line break
    for path, reason in (("a.bin", "binary"), ("b.txt", "UTF-8"), ("d.txt", "exceeds 4 bytes")):
        with pytest.raises(UnreadableSource, match=reason):
            odd.lines(path, RepositoryLimits(file_bytes=4 if path == "d.txt" else 1024))
    with pytest.raises(ValueError, match="absent"):
        source.lines("missing.py", limits)
    with pytest.raises(ValueError):
        source.lines("../etc/passwd", limits)


def test_recorded_size_must_match_loaded_bytes():
    with pytest.raises(ValueError, match="recorded size"):
        SourceTree({"a.py": 10}, lambda _: b"short").lines("a.py", RepositoryLimits())


def test_listing_counts_nested_files_and_caps_entries():
    limits = RepositoryLimits()
    root = list_tree(tree(), limits)
    assert [(e.path, e.kind, e.files) for e in root.entries] == [
        ("README.md", "file", 1), ("core", "directory", 3), ("docs", "directory", 1)]
    assert not root.truncated and root.total == 3
    nested = list_tree(tree(), limits, "core/src/main/java/org/example")
    assert [e.path for e in nested.entries] == ["core/src/main/java/org/example/PageServlet.java",
                                                "core/src/main/java/org/example/url"]
    found = list_tree(tree(), limits, pattern="*Servlet*.java")
    assert [e.path for e in found.entries] == ["core/src/main/java/org/example/PageServlet.java",
                                               "core/src/test/java/org/example/PageServletTest.java"]
    capped = list_tree(tree(), RepositoryLimits(list_entries=1), pattern="*.java")
    assert len(capped.entries) == 1 and capped.total == 3 and capped.truncated
    with pytest.raises(ValueError, match="absent"):
        list_tree(tree(), limits, "nowhere")


def test_search_is_literal_ordered_capped_and_counts_skips():
    files = FILES | {"bin/blob.dat": "x\0getForwardPage"}
    limits = RepositoryLimits(search_matches=2)
    result = search_tree(tree(files), limits, "getForwardPage")
    assert [(m.path, m.line) for m in result.matches] == [
        ("core/src/main/java/org/example/PageServlet.java", 5),
        ("core/src/main/java/org/example/url/UrlConstructor.java", 4)]
    assert (result.total_matches, result.files_with_matches, result.files_skipped, result.truncated) == (2, 2, 1, False)
    regex_like = search_tree(tree(), limits, "get.*Page")
    assert regex_like.total_matches == 0
    assert search_tree(tree(), RepositoryLimits(), "LINE two", ignore_case=True).matches[0].line == 2
    scoped = search_tree(tree(), RepositoryLimits(search_matches=1), "doGet", directory="core", pattern="*.java")
    assert scoped.total_matches == 2 and len(scoped.matches) == 1 and scoped.truncated
    for bad in ("", "   ", "a\nb", "x" * 201):
        with pytest.raises(ValueError):
            search_tree(tree(), RepositoryLimits(), bad)


def test_windows_stop_at_eighty_lines_byte_cap_or_end_of_file():
    long = {"big.py": "".join(f"line {n:04d} {'x' * 90}\n" for n in range(1, 301))}
    source = raw(long)
    assert source.window_end("big.py", 1, RepositoryLimits()) == 80
    assert source.window_end("big.py", 281, RepositoryLimits()) == 300
    capped = source.window_end("big.py", 1, RepositoryLimits(read_bytes=1000))
    assert capped == 9  # 101 bytes per line
    one_line = tree({"wide.py": "y" * 3000 + "\n"})
    with pytest.raises(UnreadableSource, match="line 1 alone exceeds the 1000-byte read cap"):
        one_line.window_end("wide.py", 1, RepositoryLimits(read_bytes=1000))
    with pytest.raises(ValueError, match="within 1..300"):
        source.window_end("big.py", 301, RepositoryLimits())


def test_limits_have_operator_ceilings():
    for bad in ({"list_entries": 0}, {"run_bytes": 2 * 1024 * 1024}, {"read_bytes": 4096, "run_bytes": 1024},
                {"search_matches": True}):
        with pytest.raises(ValueError):
            RepositoryLimits(**bad)


def test_snapshot_tree_reads_verified_artifacts_and_hands_off_inline_files(tmp_path):
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    with LocalArtifacts(root, max_bytes=1 << 20) as store:
        files = tuple(SnapshotFile(path, "100644", "0" * 40, store.put(content.encode()))
                      for path, content in FILES.items())
        manifest = store.put(b"{}")
        source = SourceTree.from_snapshot(SourceSnapshot(COMMIT, TREE, files, manifest), store)
        assert source.identity == (COMMIT, TREE) and len(source.sizes) == len(FILES)
        excerpt = source.excerpt("core/src/main/java/org/example/url/UrlConstructor.java", 4, 6, RepositoryLimits())
        assert excerpt.quote.splitlines()[1].strip() == "return request.getPathInfo();"
        handoff = source.source_files(("core/src/main/java/org/example/url/UrlConstructor.java",), RepositoryLimits())
        assert handoff[0].content == CONSTRUCTOR
    many = raw({f"f{n}.py": "x" * 5000 + "\n" for n in range(14)})
    with pytest.raises(ValueError, match="65536"):
        many.source_files(tuple(many.sizes), RepositoryLimits())


def test_dependencies_refuse_a_tree_from_another_commit():
    with pytest.raises(ValueError, match="identity"):
        RepositoryDependencies(inputs(), tree(identity=("c" * 40, TREE)))
    with pytest.raises(ValueError, match="identity"):
        RepositoryDependencies(inputs(), tree(identity=None))


def ready(path="core/src/main/java/org/example/url/UrlConstructor.java", symbol="getForwardPage", start=4, end=6):
    return {"status": "ready", "scope": "component", "reason": None,
            "target": {"symbol": symbol, "source": {"path": path, "start_line": start, "end_line": end}}}


def scripted(steps, final, seen=None):
    """Plays the tool calls in order, then the final draft; records each step's offered tools and results."""
    seen = seen if seen is not None else []

    async def respond(messages, info):
        assert "sole task" in info.instructions and SKILL_TEXT.strip() in info.instructions
        returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        seen.append(({t.name for t in info.function_tools}, returns))
        step = len(seen) - 1
        if step < len(steps):
            name, args = steps[step]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, final)])
    return FunctionModel(respond), seen


def run(model, deps=None, **kwargs):
    deps = deps or RepositoryDependencies(inputs(), tree())
    return create_repository_identification_agent(model, output_retries=0).run_sync(
        repository_identification_prompt(deps.inputs, deps.source_tree, deps.source_limits), deps=deps,
        usage_limits=UsageLimits(request_limit=8, tool_calls_limit=6), **kwargs)


def test_search_then_read_grounds_a_target_without_case_labels():
    model, seen = scripted([
        ("search_source", {"text": "getForwardPage", "pattern": "*.java"}),
        ("read_source", {"path": "core/src/main/java/org/example/url/UrlConstructor.java", "start_line": 1}),
    ], ready())
    result = run(model)
    assert seen[0][0] == {"list_source", "search_source", "read_source"}
    assert isinstance(seen[1][1][0].content, SourceSearch) and isinstance(seen[2][1][0].content, SourceRead)
    target = result.output.target
    assert (target.symbol, target.source.start_line, target.source.end_line) == ("getForwardPage", 4, 6)
    assert "request.getPathInfo()" in target.source.quote and result.output.reported_issue == ISSUE
    prompt = repository_identification_prompt(inputs(), tree(), RepositoryLimits())
    assert "hidden-case-7" not in prompt and "getPathInfo" not in prompt
    assert "core/ (3 files)" in prompt and "5 files at the commit" in prompt


def test_search_matches_alone_do_not_authorize_a_citation():
    model, _ = scripted([("search_source", {"text": "getForwardPage"})], ready())
    with pytest.raises(UnexpectedModelBehavior):
        run(model)


def test_repeated_window_returns_a_notice_and_the_first_read_still_authorizes():
    path = "core/src/main/java/org/example/url/UrlConstructor.java"
    model, seen = scripted([("read_source", {"path": path}), ("read_source", {"path": path, "start_line": 3})], ready())
    result = run(model)
    repeated = seen[2][1][0].content
    assert isinstance(repeated, RepeatedRead) and (repeated.start_line, repeated.end_line) == (3, 7)
    assert result.output.target.source.start_line == 4


def test_previous_run_reads_do_not_authorize_or_count_as_repeats():
    path = "core/src/main/java/org/example/url/UrlConstructor.java"
    model, _ = scripted([("read_source", {"path": path})], ready())
    prior = run(model)
    model, seen = scripted([("read_source", {"path": path})], ready())
    run(model, message_history=prior.all_messages())
    assert isinstance(seen[1][1][0].content, SourceRead)
    model, _ = scripted([], ready())
    with pytest.raises(UnexpectedModelBehavior):
        run(model, message_history=prior.all_messages())


def test_spent_byte_budget_withdraws_every_source_tool():
    limits = RepositoryLimits(read_bytes=200, run_bytes=300)
    deps = RepositoryDependencies(inputs(), tree(), limits)
    path = "core/src/main/java/org/example/url/UrlConstructor.java"
    model, seen = scripted([("read_source", {"path": path}), ("list_source", {})], ready())
    with pytest.raises(UnexpectedModelBehavior):
        run(model, deps)  # the second call names a withdrawn tool
    assert seen[0][0] == {"list_source", "search_source", "read_source"} and seen[1][0] == set()


def test_invented_paths_end_the_run():
    model, _ = scripted([("read_source", {"path": "core/Invented.java"})], ready())
    with pytest.raises(UnexpectedModelBehavior):
        run(model)


@pytest.mark.parametrize("change", [
    {"scope": "application_path"},
    {"target": {"symbol": "doGet", "source": {"path": "core/src/main/java/org/example/url/UrlConstructor.java",
                                              "start_line": 4, "end_line": 6}}},
    {"target": {"symbol": "getForwardPage", "source": {"path": "core/src/main/java/org/example/url/UrlConstructor.java",
                                                       "start_line": 4, "end_line": 9}}},
])
def test_finalizer_refuses_scope_symbol_and_range_inventions(change):
    model, _ = scripted([("read_source", {"path": "core/src/main/java/org/example/url/UrlConstructor.java"})],
                        ready() | change)
    with pytest.raises(UnexpectedModelBehavior):
        run(model)


def test_abstention_needs_no_read():
    model, _ = scripted([("list_source", {"directory": "core"})],
                        {"status": "missing_information", "scope": "component", "target": None,
                         "reason": "The report does not name the request handling component."})
    assert run(model).output.target is None


def test_tool_results_are_typed_contracts():
    model, seen = scripted([("list_source", {"pattern": "*.java"})], {"status": "unsupported", "scope": "component",
                                                                     "target": None, "reason": "Out of scope."})
    run(model)
    listing = seen[1][1][0].content
    assert isinstance(listing, SourceListing) and listing.total == 3
    digest = hashlib.sha256(inputs().model_dump_json().encode()).hexdigest()
    assert inputs().input_digest == digest


def test_smoke_case_keeps_oracles_out_of_agent_inputs():
    from evals.repository_identification.evaluate import dataset, selection_checks
    case = dataset().cases[0]
    assert set(case.inputs.model_dump()) == {"case_id", "issue", "scope", "repository"}
    assert "getForwardPage" not in case.inputs.issue and "DefaultURLConstructor" not in case.inputs.issue
    target = case.metadata.targets[0]
    excerpt = {"path": target.path, "start_line": 278, "end_line": 281, "quote": "x"}
    output = IssueIdentification.model_validate({"status": "ready", "scope": "component", "reason": None,
                                                 "reported_issue": case.inputs.issue,
                                                 "target": {"symbol": target.symbol, "source": excerpt}})
    assert all(selection_checks(case.inputs, output, case.metadata).values())
    wrong = output.model_copy(update={"target": output.target.model_copy(update={"symbol": "doGet"})})
    assert not selection_checks(case.inputs, wrong, case.metadata)["target_selection"]


def test_live_run_scores_the_selection():
    from evals.repository_identification.evaluate import LiveBudget, MatchesRepositorySelection, live_evaluators
    assert any(isinstance(evaluator, MatchesRepositorySelection) for evaluator in live_evaluators(LiveBudget()))


def test_file_size_limit_applies_on_every_call_not_only_the_first():
    source = raw({"a.py": "x = 1\n" * 10})
    assert len(source.lines("a.py", RepositoryLimits())) == 10
    with pytest.raises(UnreadableSource, match="exceeds 8 bytes"):
        source.lines("a.py", RepositoryLimits(file_bytes=8))
    strict_first = raw({"b.py": "y\n" * 10})
    with pytest.raises(UnreadableSource):
        strict_first.lines("b.py", RepositoryLimits(file_bytes=8))
    assert len(strict_first.lines("b.py", RepositoryLimits())) == 10


def test_paths_beyond_the_citation_contract_are_unreadable_not_crashing():
    long_path = "/".join(["d" * 60] * 5) + "/x.py"
    source = raw({long_path: "z\n"})
    assert list_tree(source, RepositoryLimits(), pattern="*.py").entries[0].path == long_path
    with pytest.raises(UnreadableSource, match="256"):
        source.window_end(long_path, 1, RepositoryLimits())
    assert search_tree(source, RepositoryLimits(), "z").files_skipped == 1


def test_inline_handoff_keeps_exact_text():
    source = raw({"crlf.txt": "a\r\nb", "empty.py": ""})
    files = source.source_files(("crlf.txt", "empty.py"), RepositoryLimits())
    assert [f.content for f in files] == ["a\r\nb", ""]


def test_search_refuses_an_absent_directory():
    with pytest.raises(ValueError, match="absent"):
        search_tree(tree(), RepositoryLimits(), "doGet", directory="invented")


def test_a_single_line_never_exceeds_the_read_cap():
    small = tree({"a.py": "x" * 1000 + "\nok\n"})
    with pytest.raises(UnreadableSource, match="read cap"):
        small.window_end("a.py", 1, RepositoryLimits(read_bytes=10, run_bytes=10))
    assert small.window_end("a.py", 2, RepositoryLimits(read_bytes=10, run_bytes=10)) == 2
    # 8,000 characters under the 16,384-character line bound, 24,000 UTF-8 bytes over the default cap.
    wide = raw({"u.py": "\u20ac" * 8000 + "\n"})
    assert len(wide.lines("u.py", RepositoryLimits())[0]) == 8000
    with pytest.raises(UnreadableSource, match="16384-byte read cap"):
        wide.window_end("u.py", 1, RepositoryLimits())


def test_read_tool_refuses_an_oversized_line_instead_of_returning_it():
    deps = RepositoryDependencies(inputs(), tree(FILES | {"big.py": "x" * 1000 + "\n"}),
                                  RepositoryLimits(read_bytes=100))
    model, _ = scripted([("read_source", {"path": "big.py"})], ready())
    with pytest.raises(UnexpectedModelBehavior, match="read_source"):
        run(model, deps)
