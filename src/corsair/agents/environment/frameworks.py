"""Operator-owned baseline admission per test framework.

Each entry checks that a native test id names exactly the given repository file, that the baseline
command targets that id, and that the run's output reports exactly one passed test and nothing
skipped, xfailed or errored. Output is still a workload claim; the later native runner adapter
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


_PYTEST_SUMMARY = re.compile(rb"^(?:=+ )?1 passed in [0-9.]+s(?: \([0-9:]+\))?(?: =+)?$", re.MULTILINE)


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


FRAMEWORKS = {
    "pytest": Framework(_pytest_file, _pytest_targets,
                        lambda output: _PYTEST_SUMMARY.search(output) is not None),
    # Maven Surefire with JUnit 5; ids are `fully.qualified.Class#method`, files end with the class path.
    "junit5": Framework(_junit_file, _junit_targets, _surefire_passed),
}


def file_matches(framework: str, test_id: str, path: str) -> bool:
    expected = FRAMEWORKS[framework].file_of(test_id)
    if expected is None:
        return False
    # pytest ids are repository-relative paths; Java ids name the class path under a source root.
    return path == expected if framework == "pytest" else path.endswith("/" + expected)
