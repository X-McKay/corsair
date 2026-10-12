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


def _junit_targets(command: tuple[str, ...], test_id: str) -> bool:
    simple = test_id.rsplit(".", 1)[-1]
    return any(token.endswith("=" + simple) or token.endswith("=" + test_id) for token in command)


def _surefire_passed(output: bytes) -> bool:
    return (re.search(rb"^\[INFO\] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0$", output, re.MULTILINE) is not None
            and re.search(rb"^\[INFO\] BUILD SUCCESS$", output, re.MULTILINE) is not None)


FRAMEWORKS = {
    "pytest": Framework(_pytest_file, lambda command, test_id: test_id in command,
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
