"""Operator-owned baseline admission per test framework.

Each entry checks that a native test id names exactly the given repository file, that the baseline
command targets that id, and that the run's output reports exactly one passed test (for the file-unit
frameworks TAP, Jest and Minitest, one file whose tests all passed) and nothing skipped, xfailed, todo or errored. Output is still a workload claim; the later native runner adapter
replaces it with JUnit XML. A framework without an entry cannot be admitted ready.
"""

import json
import re
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import SmokeTest


@dataclass(frozen=True)
class Framework:
    file_of: Callable[[str], str | None]
    targets: Callable[[tuple[str, ...], str], bool]
    passed: Callable[[bytes], bool]


def _pytest_file(test_id: str) -> str | None:
    file, sep, name = test_id.partition("::")
    return file if sep and file and name else None


_PYTEST_SUMMARY = re.compile(rb"^(?:=+ )?1 passed(?:, [1-9][0-9]* warnings?)? in [0-9.]+s(?: \([0-9:]+\))?(?: =+)?$", re.MULTILINE)


def _junit_file(test_id: str) -> str | None:
    match = re.fullmatch(r"((?:[A-Za-z_$][\w$]*\.)*[A-Za-z_$][\w$]*)#[A-Za-z_$][\w$]*", test_id)
    return match[1].replace(".", "/") + ".java" if match else None


def _pytest_targets(command: tuple[str, ...], test_id: str) -> bool:
    # Exactly one node-id selector, the claimed one; no deselection or filtering among pytest's arguments.
    starts = [i for i, token in enumerate(command) if token == "pytest" or token.endswith("/pytest")]
    if not starts:
        return False
    arguments = command[starts[0] + 1:]
    filters = ("-k", "-m", "--deselect", "--ignore", "--ignore-glob", "--lf", "--last-failed", "--ff", "--sw", "--stepwise")
    return ([t for t in arguments if "::" in t] == [test_id] and "::" not in "".join(command[:starts[0] + 1])
            and not any(t.split("=", 1)[0] in filters or t[:2] in ("-k", "-m") for t in arguments))


def _junit_targets(command: tuple[str, ...], test_id: str) -> bool:
    # Exactly one Surefire selector, naming only the claimed method by qualified or simple class name.
    selectors = [token for token in command if token.startswith("-Dtest=") or token.startswith("-Dsurefire.") or token.startswith("-Dit.test=")]
    simple = test_id.rsplit(".", 1)[-1]
    return selectors in (["-Dtest=" + test_id], ["-Dtest=" + simple])


def _surefire_passed(output: bytes) -> bool:
    return (re.search(rb"^\[INFO\] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0$", output, re.MULTILINE) is not None
            and re.search(rb"^\[INFO\] BUILD SUCCESS$", output, re.MULTILINE) is not None)


def _file_id(*suffixes: str) -> Callable[[str], str | None]:
    """File-unit frameworks (TAP, Jest, Minitest): the baseline id is one plain repository-relative test file; the
    runners' finer ids (`file.t#subtest`, `file.js::name`, `file.rb::Class#test`) belong to the runners."""
    def file_of(test_id: str) -> str | None:
        parts = test_id.split("/")
        plain = all(re.fullmatch(r"(?!-)[\w.+-]+", part) and part not in (".", "..") for part in parts)
        return test_id if plain and test_id.endswith(suffixes) else None
    return file_of


@dataclass(frozen=True)
class OneFile:
    """A baseline command that runs exactly one named test file under a runner and nothing else.

    `tools` name the runner token; `values` are options whose value is the next token; `refused` are options (by
    name before any `=`) that would list, filter, replay, reinterpret or load code that could rewrite the output;
    `short` are single-dash letters refused inside a bundle (`-vD`), except in an attached `keep` option such as
    `-Ilib`; `required` must all appear. `before`, when set, is the only options allowed between the runner token and
    the file, each with its value attached or next (for Ruby, whose options there can change directory or run
    another script).
    """
    tools: tuple[str, ...]
    values: tuple[str, ...]
    refused: tuple[str, ...]
    short: str
    keep: tuple[str, ...]
    required: tuple[str, ...]
    before: tuple[str, ...] | None = None

    def __call__(self, command: tuple[str, ...], test_id: str) -> bool:
        starts = [i for i, token in enumerate(command) if any(token == t or token.endswith("/" + t) for t in self.tools)]
        if not starts:
            return False
        arguments, files, skip = command[starts[0] + 1:], [], False
        for token in arguments:
            if skip:
                skip = False
                continue
            if self.before is not None and not files and token[:1] == "-":
                if token in self.before:
                    skip = True
                    continue
                if not token.startswith(self.before):
                    return False
                continue
            name = token.split("=", 1)[0]
            bundle = token[:1] == "-" and token[:2] != "--" and not token.startswith(self.keep)
            if name in self.refused or (bundle and any(letter in self.short for letter in name[1:])):
                return False
            if token in self.values:
                skip = True
            elif token[:1] != "-":
                files.append(token)
        return files == [test_id] and not skip and all(flag in arguments for flag in self.required)


# prove: `--norc` is required, since prove otherwise reads the project's `.proverc`, which can add options unseen.
_tap_targets = OneFile(tools=("prove",), values=("-I", "-j", "--jobs"),
                       refused=("--dry", "--state", "--exec", "-e", "--ext", "--rules", "--harness", "--formatter", "-a",
                                "--archive", "--rc", "--source", "--plugin", "--module", "-P", "-M"),
                       short="DPMae", keep=("-I",), required=("--norc",))
# Jest: `--runTestsByPath` makes the file argument a path, not a pattern; `--json` puts the results on stdout.
# `-c/--config` is refused: an inline or file config can change test matching, roots and reporters.
_jest_targets = OneFile(tools=("jest", "jest.js"), values=("-w", "--maxWorkers", "--testTimeout"),
                        refused=("-c", "--config", "-t", "--testNamePattern", "--testPathPattern", "--testPathIgnorePatterns", "--listTests",
                                 "-o", "--onlyChanged", "--changedSince", "--findRelatedTests", "--lastCommit", "--watch",
                                 "--watchAll", "--passWithNoTests", "--testRegex", "--testMatch", "--outputFile",
                                 "--rootDir", "--roots", "--projects", "--testRunner", "--reporters"),
                        short="tocb", keep=(), required=("--runTestsByPath", "--json"))
# Ruby loading one Minitest file: only `-I` and `-r` before the file (others such as `-C` or `-s` change what runs);
# after it, Minitest's own `-n/--name` and `-e/--exclude` filters are refused.
_minitest_targets = OneFile(tools=("ruby",), values=("--seed", "-s"),
                            refused=("-e", "-n", "--name", "-x", "--exclude"), short="enx", keep=(),
                            required=(), before=("-I", "-r"))


def _tap_passed(output: bytes) -> bool:
    # Verbose prove output (the TAP lines themselves): prove's own summary passes skips, todos and empty files.
    return (re.search(rb"^ok [0-9]+", output, re.MULTILINE) is not None
            and re.search(rb"^Files=1, Tests=[1-9][0-9]*,", output, re.MULTILINE) is not None
            and re.search(rb"^Result: PASS$", output, re.MULTILINE) is not None
            and re.search(rb"(?im)^\s*(?:not )?ok\b[^\n]*#\s*(?:skip|todo)\b|^\s*1\.\.0\b|skipped:|TODO passed|^\s*not ok\b",
                          output) is None)


def _jest_passed(output: bytes) -> bool:
    # Jest's `--json` report: one suite, at least one test, every test passed; skipped (pending) and todo do not pass.
    try:
        report = json.loads(output)
    except ValueError:
        return False
    if type(report) is not dict or report.get("success") is not True or not isinstance(report.get("testResults"), list):
        return False
    counts = {key: report.get(key) for key in ("numTotalTestSuites", "numPassedTestSuites", "numTotalTests", "numPassedTests",
                                                 "numFailedTests", "numPendingTests", "numTodoTests",
                                                 "numRuntimeErrorTestSuites")}
    if any(type(value) is not int for value in counts.values()):
        return False
    results = report["testResults"]
    assertions = results[0].get("assertionResults") if len(results) == 1 and isinstance(results[0], dict) else None
    return (counts["numTotalTestSuites"] == counts["numPassedTestSuites"] == 1 and counts["numTotalTests"] >= 1
            and counts["numPassedTests"] == counts["numTotalTests"]
            and counts["numFailedTests"] == counts["numPendingTests"] == counts["numTodoTests"] == 0
            and counts["numRuntimeErrorTestSuites"] == 0 and isinstance(assertions, list)
            and len(assertions) == counts["numTotalTests"]
            and all(isinstance(a, dict) and a.get("status") == "passed" for a in assertions))


# Minitest's summary line: at least one run, and no failure, error or skip.
_MINITEST_SUMMARY = re.compile(rb"^[1-9][0-9]* runs?, [0-9]+ assertions?, 0 failures?, 0 errors?, 0 skips?$", re.MULTILINE)


FRAMEWORKS = {
    "pytest": Framework(_pytest_file, _pytest_targets,
                        lambda output: _PYTEST_SUMMARY.search(output) is not None),
    # Maven Surefire with JUnit 5 or JUnit 4 (same ids and Surefire summary); ids are `fully.qualified.Class#method`,
    # files end with the class path.
    "junit5": Framework(_junit_file, _junit_targets, _surefire_passed),
    "junit4": Framework(_junit_file, _junit_targets, _surefire_passed),
    # Perl Test::More files through prove (Test::Harness); the baseline id is one repository-relative `.t` file.
    "tap-harness": Framework(_file_id(".t"), _tap_targets, _tap_passed),
    # Jest test files run by path with a JSON report; the baseline id is one repository-relative test file.
    "jest": Framework(_file_id(".js", ".jsx", ".mjs", ".cjs"), _jest_targets, _jest_passed),
    # One Minitest file loaded by Ruby (directly or under `bundle exec`); the baseline id is that `.rb` file.
    "minitest": Framework(_file_id(".rb"), _minitest_targets,
                          lambda output: len(_MINITEST_SUMMARY.findall(output)) == 1),
}


def file_matches(framework: str, test_id: str, path: str) -> bool:
    expected = FRAMEWORKS[framework].file_of(test_id)
    if expected is None:
        return False
    # pytest and file-unit ids are repository-relative paths; Java ids name the class path under a source root.
    return path.endswith("/" + expected) if framework in ("junit5", "junit4") else path == expected


def project_tests(framework: str, smoke: "SmokeTest", discovery: bytes) -> list[str]:
    """SPEC-0071: test references in a discovery output other than the smoke test, so a smoke baseline is admitted only
    when the run's own discovery found no project test. A token is a test reference when the framework's id grammar
    names a file for it; absolute paths (Jest's `--listTests`) are compared by their trailing repository path."""
    file_of, smoke_file = FRAMEWORKS[framework].file_of, FRAMEWORKS[framework].file_of(smoke.test_id)
    others = []
    for token in dict.fromkeys(discovery.decode("utf-8", "replace").split()):
        relative = token.lstrip("/")
        named = file_of(token) or (file_of(relative) if token.startswith("/") else None)
        if named is None or token == smoke.test_id or named == smoke_file or relative.endswith("/" + smoke.path):
            continue
        others.append(token)
    return others
