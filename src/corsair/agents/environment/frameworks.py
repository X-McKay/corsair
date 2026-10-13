"""Operator-owned baseline admission per test framework.

Each entry checks that a native test id names exactly the given repository file, that the baseline
command targets that id, and that the run's output reports exactly one passed test (for TAP, one
passed file) and nothing skipped, xfailed, todo or errored. Output is still a workload claim; the later native runner adapter
replaces it with JUnit XML. A framework without an entry cannot be admitted ready.
"""

import re
from dataclasses import dataclass
from typing import Callable


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


def _tap_file(test_id: str) -> str | None:
    # The baseline unit for TAP is one test file, as `prove --dry` prints it; subtest ids belong to the runner.
    return test_id if re.fullmatch(r"(?!-)[\w.+-]+(?:/[\w.+-]+)*\.t", test_id) else None


# prove options whose value is the next token, and options that would list, replay or reinterpret instead of
# running exactly the named file.
_PROVE_VALUES = ("-I", "-P", "-M", "-j", "--jobs", "--source", "--rules", "--ext", "--state", "--exec", "-e",
                 "--rc", "--harness", "--formatter", "-a", "--archive")
_PROVE_REFUSED = ("--dry", "--state", "--exec", "-e", "--ext", "--rules", "--harness", "--formatter", "-a", "--archive")


def _tap_targets(command: tuple[str, ...], test_id: str) -> bool:
    # prove with exactly one file argument, the claimed one; no dry run, saved state or another interpreter.
    starts = [i for i, token in enumerate(command) if token == "prove" or token.endswith("/prove")]
    if not starts:
        return False
    arguments, files, skip = command[starts[0] + 1:], [], False
    for token in arguments:
        if skip:
            skip = False
            continue
        name = token.split("=", 1)[0]
        if name in _PROVE_REFUSED or (token[:1] == "-" and token[:2] != "--" and "D" in token[1:]):
            return False
        if token in _PROVE_VALUES:
            skip = True
        elif token[:1] != "-":
            files.append(token)
    return files == [test_id] and not skip


def _tap_passed(output: bytes) -> bool:
    # Verbose prove output (the TAP lines themselves): prove's own summary passes skips, todos and empty files.
    return (re.search(rb"^ok [0-9]+", output, re.MULTILINE) is not None
            and re.search(rb"^Files=1, Tests=[1-9][0-9]*,", output, re.MULTILINE) is not None
            and re.search(rb"^Result: PASS$", output, re.MULTILINE) is not None
            and re.search(rb"(?im)^\s*(?:not )?ok\b[^\n]*#\s*(?:skip|todo)\b|^\s*1\.\.0\b|skipped:|TODO passed|^\s*not ok\b",
                          output) is None)


FRAMEWORKS = {
    "pytest": Framework(_pytest_file, _pytest_targets,
                        lambda output: _PYTEST_SUMMARY.search(output) is not None),
    # Maven Surefire with JUnit 5 or JUnit 4 (same ids and Surefire summary); ids are `fully.qualified.Class#method`,
    # files end with the class path.
    "junit5": Framework(_junit_file, _junit_targets, _surefire_passed),
    "junit4": Framework(_junit_file, _junit_targets, _surefire_passed),
    # Perl Test::More files through prove (Test::Harness); the baseline id is one repository-relative `.t` file.
    "tap-harness": Framework(_tap_file, _tap_targets, _tap_passed),
}


def file_matches(framework: str, test_id: str, path: str) -> bool:
    expected = FRAMEWORKS[framework].file_of(test_id)
    if expected is None:
        return False
    # pytest and TAP ids are repository-relative paths; Java ids name the class path under a source root.
    return path.endswith("/" + expected) if framework in ("junit5", "junit4") else path == expected
