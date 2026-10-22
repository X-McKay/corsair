"""Python / pytest adapter: the reference implementation of the framework contract.

The probe is a Python module defining ``CONTROL_PAYLOAD``, ``EXPLOIT_PAYLOAD`` and ``run_target(payload)``. The
driver is a pytest file with one parametrized test id per payload; each run executes one id under coverage.py,
restricted to the target file, and writes a JSON record classifying how ``run_target`` ended.
"""
from __future__ import annotations

import ast
import json
import posixpath
import xml.etree.ElementTree as ET
from collections.abc import Mapping

from .base import PROBE_DIR, RESULT_DIR, WORKDIR, ProbeResult

BANNED_IMPORTS = ("unittest.mock", "mock", "pytest_mock", "responses", "httpretty", "requests_mock")
REQUIRED_SYMBOLS = ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target")

DRIVER = '''"""Kernel-owned driver: one native pytest test id per payload through the submitted run_target."""
import json
import os
import sys
import traceback

import pytest

for _path in ("/work/.corsair", "/work"):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import corsair_probe as probe  # noqa: E402

ROLE = os.environ["CORSAIR_ROLE"]
RESULT = os.environ["CORSAIR_RESULT"]
PAYLOADS = {"control": probe.CONTROL_PAYLOAD, "exploit": probe.EXPLOIT_PAYLOAD}


def _record(outcome, exc=None):
    frames = traceback.extract_tb(exc.__traceback__) if exc is not None else []
    deepest = frames[-1].filename if frames else ""
    record = {"role": ROLE, "outcome": outcome, "exception_type": type(exc).__name__ if exc is not None else None,
              "message": str(exc)[:2000] if exc is not None else None,
              "raised_in_probe": deepest.endswith("corsair_probe.py")}
    if outcome == "violated" and not record["raised_in_probe"]:
        record["outcome"] = "errored"
    with open(RESULT, "w") as handle:
        json.dump(record, handle)


@pytest.mark.parametrize("role", [ROLE])
def test_probe(role):
    try:
        probe.run_target(PAYLOADS[role])
    except AssertionError as exc:
        _record("violated", exc)
        raise
    except BaseException as exc:
        _record("errored", exc)
        raise
    _record("holds")
'''


def ast_guard(probe: str):
    from ..kernel import Gate, GateVerdict

    try:
        tree = ast.parse(probe)
    except SyntaxError as error:
        return GateVerdict(passed=False, stage=Gate.AST_GUARD, reason=f"probe does not parse: {error}")
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            module = getattr(node, "module", None) or ""
            for banned in BANNED_IMPORTS:
                if module == banned or module.startswith(banned + ".") or banned in names:
                    return GateVerdict(passed=False, stage=Gate.AST_GUARD,
                                       reason=f"probe imports a mocking library ({banned}); doubles may replace "
                                              "dependencies only through the target's own seams, never patch them")
        elif isinstance(node, ast.FunctionDef) and node.name == "run_target":
            if len(node.args.args) != 1 or node.args.vararg or node.args.kwonlyargs:
                return GateVerdict(passed=False, stage=Gate.AST_GUARD,
                                   reason="run_target must take exactly one positional argument, the payload")
            defined.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            defined.update(t.id for t in targets if isinstance(t, ast.Name))
    missing = [name for name in REQUIRED_SYMBOLS if name not in defined]
    if missing:
        return GateVerdict(passed=False, stage=Gate.AST_GUARD,
                           reason=f"probe must define {', '.join(missing)} at module level")
    return GateVerdict(passed=True, stage=Gate.AST_GUARD, reason="structural contract satisfied")


class Pytest:
    name = "pytest"
    language = "python"
    probe_file = "corsair_probe.py"

    def guard(self, probe: str):
        return ast_guard(probe)

    def driver_files(self) -> dict[str, bytes]:
        return {"test_corsair_probe.py": DRIVER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        return ["python", "-m", "coverage", "run", f"--include={WORKDIR}/{target_file}", "-m", "pytest",
                "-p", "no:cacheprovider", "-c", "/dev/null", "--rootdir", WORKDIR, "--noconftest",
                "--import-mode=importlib", "-q", f"--junitxml={RESULT_DIR}/junit.xml",
                "-o", "junit_logging=all", "-o", "junit_log_passing_tests=true",
                f"{PROBE_DIR}/test_corsair_probe.py"]

    def after_command(self) -> list[str] | None:
        """Run after the test command in the same container, to render the coverage report."""
        return ["python", "-m", "coverage", "json", "-o", f"{RESULT_DIR}/coverage.json"]

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json", "HOME": "/tmp",
                "PYTHONPATH": f"{WORKDIR}:{PROBE_DIR}", "PYTHONDONTWRITEBYTECODE": "1",
                "COVERAGE_FILE": f"{RESULT_DIR}/coverage"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        from ..kernel import Outcome

        tests, native = read_junit(files.get(f"{RESULT_DIR}/junit.xml"))
        record = files.get(f"{RESULT_DIR}/result.json")
        covered_target, covered_lines = read_coverage(files.get(f"{RESULT_DIR}/coverage.json"), hypothesis)
        exception_type = message = None
        if record is None or tests == 0:
            outcome = Outcome.NOT_RUN
            message = native or "the test never ran (collection or import error)"
        else:
            parsed = json.loads(record)
            outcome = Outcome(parsed["outcome"])
            exception_type, message = parsed.get("exception_type"), parsed.get("message")
            if (outcome is Outcome.HOLDS) != (native is None):
                outcome, message = Outcome.ERRORED, f"native report disagrees with the driver record: {native}"
        return ProbeResult(outcome, exception_type, message, tests, covered_target, covered_lines)


def read_junit(data: bytes | None) -> tuple[int, str | None]:
    """(number of test cases, the first failure or error text or None). Shared by every JUnit-emitting adapter."""
    if not data:
        return 0, None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return 0, "unreadable JUnit report"
    count, first = 0, None
    for case in root.iter("testcase"):
        count += 1
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None and first is None:
                first = f"{kind}: {(node.get('message') or '')[:500]}"
    if count == 0:
        for node in root.iter("error"):
            return 0, f"error: {(node.get('message') or node.text or '')[:500]}"
    return count, first


def read_coverage(data: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """coverage.py JSON: whether the target file executed and which hypothesis lines did."""
    if not data:
        return None, ()
    try:
        report = json.loads(data)
    except json.JSONDecodeError:
        return None, ()
    target = hypothesis.target_file
    for path, info in report.get("files", {}).items():
        if posixpath.normpath(path).endswith(target):
            executed = set(info.get("executed_lines", []))
            return bool(executed), tuple(sorted(executed & set(hypothesis.target_lines)))
    return False, ()
