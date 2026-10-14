"""Eval-only facts about authored non-Python tests: the language-dispatched twin of the Python AST checks.

Structure, not proof of test semantics. A test file's language comes from its planned test id grammar (the
port's own regexes). Python ids keep the AST path in ``static.py``/``admission.py`` unchanged; this module
serves the other languages:

- ``parses_and_defines_test`` and ``has_assertion`` come from the production reader the authoring stage itself
  finalizes with (``static.assertion_lines``: Jest through ``javascript.py``, Minitest through ``ruby.py``). Java
  and Perl have no production reader yet, so for them both facts are false until one lands there.
- Every other fact is lexical over the test body's text: Ruby from ``def <method>`` to the ``end`` at the same
  indentation, Jest from the esprima location of the planned callback, Java and Perl by brace matching from
  ``void <method>(`` or ``subtest <name> => sub {`` (string and line-comment aware, no regex literals). The
  checks: the plan's callee expression as written is called in the body; no skip; no constant assertion; no
  process or network use anywhere in the file; the plan's quoted adversarial literal is in the security body
  and absent from the control body; the security assertion lines are the reader's lines when the planned
  failure type is the framework's assertion error. These are patterns, not parsers: aliases, dataflow,
  comments that mention a pattern and reachability are not resolved.

``discover`` is the static host runner's discovery for Minitest and Jest files: ids come from the same
production readers plus a lexical scan for other test definitions, and it reports what loading could refuse
(a file the reader cannot parse, a ``require`` nothing in the saved source or the small listed standard
library could satisfy, ids other than the planned pair). Java and Perl files are refused, as before.
"""

import re
from os.path import dirname, normpath

from corsair.agents.test_authoring import javascript
from corsair.agents.test_authoring.ruby import ruby_assertion_lines
from corsair.agents.test_authoring.static import assertion_lines
from corsair.ports.test_runner import (
    JAVA_TEST_ID,
    JS_TEST_ID,
    PERL_TEST_ID,
    RUBY_TEST_ID,
    TEST_ID,
    JavaTestId,
    JsTestId,
    PerlTestId,
    RubyTestId,
)
from evals.test_authoring.admission import quoted_literals


def language_of(test_id: str) -> str:
    for name, grammar in (("python", TEST_ID), ("ruby", RUBY_TEST_ID), ("javascript", JS_TEST_ID),
                          ("perl", PERL_TEST_ID), ("java", JAVA_TEST_ID)):
        if grammar.fullmatch(test_id):
            return name
    raise ValueError(f"{test_id} has no known test id grammar")


# The failure type each framework's native report gives a failed assertion (the environment stage's
# assertion facts; Jest 24 reports expect() failures as Error; PR #128 names a failed TAP assertion not_ok).
ASSERTION_ERRORS = {"ruby": {"Minitest::Assertion"}, "javascript": {"Error", "AssertionError"},
                    "java": {"org.opentest4j.AssertionFailedError", "java.lang.AssertionError"},
                    "perl": {"not_ok"}}
SKIP = {"ruby": r"(?m)^\s*skip\b|\bskip\s*\(",
        "javascript": r"\b(?:test|it|describe)\.skip\b|\bx(?:it|test|describe)\s*\(",
        "java": r"@Disabled\b|@Ignore\b|\bassume(?:True|False|That)\s*\(",
        "perl": r"\bskip\s*\(|\bSKIP\s*:|\bskip_all\b|\btodo_skip\b"}
CONSTANT_ASSERT = {"ruby": r"\bassert\s*\(?\s*(?:true|1)\b|\brefute\s*\(?\s*(?:false|nil)\b"
                           r"|\bassert_equal\s*\(?\s*(true|\d+|'[^']*'|\"[^\"]*\")\s*,\s*\1\s*\)?\s*$",
                   "javascript": r"\bexpect\(\s*(true|\d+|'[^']*'|\"[^\"]*\")\s*\)\s*\.\s*to(?:Be|Equal)\(\s*\1\s*\)"
                                 r"|\bassert(?:\.ok)?\(\s*(?:true|1)\s*\)",
                   "java": r"\bassertTrue\(\s*true\s*\)|\bassertFalse\(\s*false\s*\)"
                           r"|\bassertEquals\(\s*(\d+|\"[^\"]*\")\s*,\s*\1\s*\)",
                   "perl": r"\bok\s*\(?\s*1\s*[,;)]|\bpass\s*\("}
PROCESS_OR_NETWORK = {
    "ruby": r"\bsystem\s*\(|`|%x|\bOpen3\b|\bNet::HTTP\b|\bIO\.popen\b|\bspawn\s*\(|\bexec\s*\(|\bfork\b"
            r"|\bTCPSocket\b|\bUDPSocket\b|require\s*\(?\s*['\"](?:socket|open3|net/\w+|open-uri)['\"]",
    "javascript": r"require\(\s*['\"](?:child_process|net|http|https|http2|dgram|tls|cluster|worker_threads)['\"]\s*\)"
                  r"|\bfrom\s+['\"](?:child_process|net|http|https|http2|dgram|tls)['\"]",
    "java": r"\bProcessBuilder\b|\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\b|\bjava\.net\.\w+|\bHttpClient\b",
    "perl": r"\bsystem\s*\(|`|\bqx\b|\bexec\s*\(|\bfork\b|\bIO::Socket\b|\bLWP::|\bHTTP::Tiny\b|\bIPC::"
            r"|\bopen\s*\(?\s*my\s+\$\w+\s*,\s*['\"](?:-\||\|-)"}


def _matching_brace(text: str, start: int, line_comment: str) -> int:
    """Index after the brace closing the one at ``start``; skips quoted strings and line comments."""
    depth, at = 0, start
    while at < len(text):
        char = text[at]
        if text.startswith(line_comment, at):
            at = text.find("\n", at)
            if at < 0:
                break
            continue
        if char in "'\"":
            end = at + 1
            while end < len(text) and text[end] != char:
                end += 2 if text[end] == "\\" else 1
            at = end + 1
            continue
        depth += (char == "{") - (char == "}")
        at += 1
        if depth == 0:
            return at
    raise ValueError("unbalanced braces")


def body_of(language: str, content: str, test_id: str) -> str:
    """The planned test's own text; ValueError when it cannot be located."""
    if language == "ruby":
        method = RubyTestId.parse(test_id).method
        lines = content.splitlines()
        for number, line in enumerate(lines):
            found = re.match(rf"(\s*)def\s+{re.escape(method)}\b", line)
            if found:
                closing = re.compile(rf"{found.group(1)}end\b")
                for last in range(number + 1, len(lines)):
                    if closing.match(lines[last]):
                        return "\n".join(lines[number:last + 1])
        raise ValueError(f"{test_id} is not defined in its test file")
    if language == "javascript":
        test = JsTestId.parse(test_id)
        scope = javascript._parse(content).body
        if test.suite:
            scope = javascript._statements(javascript._one(scope, javascript.SUITES, test.suite, test_id))
        callback = javascript._one(scope, javascript.TESTS, test.name, test_id)
        return "\n".join(content.splitlines()[callback.loc.start.line - 1:callback.loc.end.line])
    if language == "java":
        opener = re.search(rf"\bvoid\s+{re.escape(JavaTestId.parse(test_id).method)}\s*\([^)]*\)[^{{;]*\{{", content)
        comment = "//"
    elif language == "perl":
        name = re.escape(PerlTestId.parse(test_id).name)
        opener = re.search(rf"\bsubtest\s*\(?\s*(['\"]?){name}\1\s*(?:=>|,)\s*sub\s*\{{", content)
        comment = "#"
    else:
        raise ValueError(f"no eval body reader for {language}")
    if opener is None:
        raise ValueError(f"{test_id} is not defined in its test file")
    brace = opener.end() - 1
    return content[opener.start():_matching_brace(content, brace, comment)]


def _callee(implementation_call: str) -> str:
    return re.sub(r"\s+", "", implementation_call.split("(")[0])


def _calls(body: str, callee: str) -> bool:
    return re.search(rf"(?<![\w.:>]){re.escape(callee)}(?:\s*\(|[ \t]+[^\s=])", body) is not None


def static_facts(language: str, content: str, test_id: str, implementation_call: str) -> dict[str, bool]:
    """The Python ``static_checks`` keys this module can establish for ``language`` (no_mock and swallowing are
    Python-only; unit plans admit dependency doubles anyway)."""
    try:
        body = body_of(language, content, test_id)
        lines = assertion_lines(content, test_id)
    except ValueError as exc:
        if "has no assertion" not in str(exc):
            return {"parses_and_defines_test": False}
        body, lines = body_of(language, content, test_id), ()
    return {"parses_and_defines_test": True,
            "calls_target": _calls(body, _callee(implementation_call)),
            "no_skip": re.search(SKIP[language], content) is None,
            "no_constant_assert": re.search(CONSTANT_ASSERT[language], content, re.MULTILINE) is None,
            "has_assertion": bool(lines)}


def admission_facts(language: str, plan, files: dict[str, str], security_lines: tuple[int, ...]) -> dict[str, bool]:
    """The eval admission facts for ``language``; ``stage_admitted`` is omitted because the stage's own
    admission check reads Python only and admits every other file unread."""
    control_file, security_file = files.get(plan.control.test_path, ""), files.get(plan.security.test_path, "")
    try:
        control = body_of(language, control_file, plan.control.test_id)
        security = body_of(language, security_file, plan.security.test_id)
    except ValueError:
        return {"admission_parses": False}
    facts = {"no_process_or_network": not any(re.search(PROCESS_OR_NETWORK[language], content)
                                              for content in files.values())}
    adversarial = quoted_literals(plan.security.input) - quoted_literals(plan.control.input)
    if adversarial:
        facts["planned_input_in_security"] = all(value in security for value in adversarial)
        facts["planned_input_not_in_control"] = not any(value in control for value in adversarial)
    if plan.security_expectation.failure_type in ASSERTION_ERRORS[language]:
        try:
            readable = set(assertion_lines(security_file, plan.security.test_id))
        except ValueError:
            readable = set()
        facts["planned_failure_is_assert"] = bool(security_lines) and set(security_lines) <= readable
    return facts


# What loading can satisfy besides saved source: a small listed part of each standard library. A name outside
# these lists is reported unresolved, as the Python static runner does for an import nothing could satisfy.
RUBY_LIBRARIES = frozenset({"minitest", "minitest/autorun", "tmpdir", "tempfile", "fileutils", "json", "stringio",
                            "set", "pathname", "securerandom", "uri", "cgi", "erb", "digest", "time", "date",
                            "ostruct", "open3", "socket", "net/http", "open-uri"})
NODE_MODULES = frozenset({"assert", "fs", "path", "os", "util", "url", "querystring", "crypto", "events", "stream",
                          "child_process", "net", "http", "https", "tls", "dgram"})


def _ruby_discovery(path: str, content: str, available: set[str], include: tuple[str, ...]) -> tuple[list[str], list[str]]:
    errors = []
    for kind, name in re.findall(r"(?m)^\s*(require_relative|require)\s*\(?\s*['\"]([^'\"]+)['\"]", content):
        stem = name.removesuffix(".rb")
        candidates = ({normpath(f"{dirname(path)}/{stem}.rb")} if kind == "require_relative"
                      else {normpath(f"{root}/{stem}.rb") for root in include} | {f"{stem}.rb"})
        if not candidates & available and (kind == "require_relative" or name not in RUBY_LIBRARIES):
            errors.append(f"LoadError: cannot load such file -- {name} ({path})")
    ids, owner = [], None
    for line in content.splitlines():
        if found := re.match(r"\s*class\s+([A-Z][\w:]*)", line):
            owner = found.group(1)
        elif (found := re.match(r"\s*def\s+(test_\w+)", line)) and owner:
            ids.append(f"{path}::{owner}#{found.group(1)}")
    return ids, errors


def _js_discovery(path: str, content: str, available: set[str]) -> tuple[list[str], list[str]]:
    errors = []
    for name in re.findall(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
        if name.startswith("."):
            stem = normpath(f"{dirname(path)}/{name}")
            if not {stem, f"{stem}.js", f"{stem}/index.js"} & available:
                errors.append(f"Cannot find module '{name}' from '{path}'")
        elif name.split("/")[0] not in NODE_MODULES:
            errors.append(f"Cannot find module '{name}' from '{path}'")
    ids = []
    for statement in javascript._parse(content).body:
        call = statement.expression if statement.type == "ExpressionStatement" else None
        if call is None or call.type != "CallExpression" or call.callee.type != "Identifier" or not call.arguments \
                or call.arguments[0].type != "Literal":
            continue
        if call.callee.name in javascript.TESTS:
            ids.append(f"{path}::{call.arguments[0].value}")
        elif call.callee.name in javascript.SUITES and len(call.arguments) > 1 \
                and call.arguments[1].type in javascript.FUNCTIONS:
            for inner in javascript._statements(call.arguments[1]):
                nested = inner.expression if inner.type == "ExpressionStatement" else None
                if nested is not None and nested.type == "CallExpression" and nested.callee.type == "Identifier" \
                        and nested.callee.name in javascript.TESTS and nested.arguments \
                        and nested.arguments[0].type == "Literal":
                    ids.append(f"{path}::{call.arguments[0].value}::{nested.arguments[0].value}")
    return ids, errors


def discover(path: str, content: str, planned: tuple[str, ...], available: set[str],
             discovery_command: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Ids a Minitest or Jest file defines and what loading it could refuse."""
    language = "ruby" if path.endswith(".rb") else "javascript" if path.endswith((".js", ".cjs", ".mjs", ".jsx")) else None
    if language is None:
        raise ValueError(f"static host runner analyses Python test files only (and Minitest and Jest files), not {path}")
    for test_id in planned:
        try:
            if language == "ruby":
                ruby = RubyTestId.parse(test_id)
                ruby_assertion_lines(content, ruby.class_name, ruby.method)
            else:
                javascript.assertion_lines(content, test_id)
        except ValueError as exc:
            # A missing or assertion-free planned test still loads; the id comparison below decides discovery.
            if "defined" not in str(exc) and "has no assertion" not in str(exc):
                return [], [f"SyntaxError (static reader): {exc} ({path})"]
    if language == "ruby":
        include = tuple(token[2:] for token in discovery_command if token.startswith("-I") and len(token) > 2)
        return _ruby_discovery(path, content, available, include)
    return _js_discovery(path, content, available)
