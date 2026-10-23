"""One shared Python driver; foreign-runtime adapters replace only target coverage."""

from __future__ import annotations

import ast
import posixpath
import xml.etree.ElementTree as ET
from collections.abc import Mapping

from corsair.adapters.frameworks.evidence import load_json
from corsair.ports.framework import PROBE_DIR, RESULT_DIR, WORKDIR, ProbeResult

BANNED_IMPORTS = ("unittest.mock", "mock", "pytest_mock", "responses", "httpretty", "requests_mock")
REQUIRED_SYMBOLS = ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target")

DRIVER = '''"""Kernel-owned driver: one native pytest test id per payload."""
import json
import os
import sys
import traceback

import pytest

for _path in ("/work/.corsair", "/work"):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import corsair_probe as probe

ROLE = os.environ["CORSAIR_ROLE"]
RESULT = os.environ["CORSAIR_RESULT"]
PAYLOADS = {"control": probe.CONTROL_PAYLOAD, "exploit": probe.EXPLOIT_PAYLOAD}


def _record(outcome, exc=None):
    frames = traceback.extract_tb(exc.__traceback__) if exc is not None else []
    deepest = frames[-1].filename if frames else ""
    record = {"role": ROLE, "outcome": outcome, "exception_type": type(exc).__name__ if exc is not None else None,
              "message": str(exc)[:2000] if exc is not None else None,
              "raised_in_probe": deepest == "/work/.corsair/corsair_probe.py"}
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
    """Check syntax, top-level ownership, arity and obvious unfair tests; never execute a probe."""
    from corsair.domain.verification import Gate, GateVerdict

    def reject(reason: str):
        return GateVerdict(passed=False, stage=Gate.AST_GUARD, reason=reason)

    try:
        tree = ast.parse(probe)
    except (SyntaxError, ValueError, RecursionError) as error:
        return reject(f"probe does not parse: {error}")
    definitions: dict[str, list[ast.AST]] = {name: [] for name in REQUIRED_SYMBOLS}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in definitions:
                definitions[node.name].append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in definitions:
                    definitions[target.id].append(node)
    missing = [name for name, nodes in definitions.items() if not nodes]
    if missing:
        return reject(f"probe must define {', '.join(missing)} at module level")
    if any(len(nodes) != 1 for nodes in definitions.values()):
        return reject("required symbols must each be defined exactly once at module level")
    driver = definitions["run_target"][0]
    if not isinstance(driver, ast.FunctionDef):
        return reject("run_target must be one synchronous function")
    args = driver.args
    if (
        len(args.posonlyargs) + len(args.args) != 1
        or args.vararg
        or args.kwarg
        or args.kwonlyargs
        or args.defaults
        or driver.decorator_list
    ):
        return reject("run_target must take exactly one positional argument, without defaults or decorators")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [a.name for a in node.names] + [f"{module}.{a.name}" for a in node.names] + [module]
            if any(
                name == banned or name.startswith(banned + ".") for name in names for banned in BANNED_IMPORTS
            ):
                return reject(
                    "probe imports a mocking library; exercise the real target through its public seam"
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in REQUIRED_SYMBOLS and node is not driver:
                return reject("required symbols cannot be nested or replaced")
            if any(
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in REQUIRED_SYMBOLS[:2]
                for child in ast.walk(node)
            ):
                return reject(
                    "driver and helpers must not reference payload identities; apply one invariant to both"
                )
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id in definitions
        ):
            if not any(node is child for owner in definitions[node.id] for child in ast.walk(owner)):
                return reject("required symbols cannot be rebound or deleted")
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant):
            return reject("constant assertions do not test the security invariant")
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
        return [
            "python",
            "-m",
            "coverage",
            "run",
            f"--include={WORKDIR}/{target_file}",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-c",
            "/dev/null",
            "--rootdir",
            WORKDIR,
            "--noconftest",
            "--import-mode=importlib",
            "-q",
            f"--junitxml={RESULT_DIR}/junit.xml",
            "-o",
            "junit_logging=all",
            "-o",
            "junit_log_passing_tests=true",
            f"{PROBE_DIR}/test_corsair_probe.py",
        ]

    def after_command(self) -> list[str] | None:
        return ["python", "-m", "coverage", "json", "-o", f"{RESULT_DIR}/coverage.json"]

    def environment(self, role: str) -> Mapping[str, str]:
        return {
            "CORSAIR_ROLE": role,
            "CORSAIR_RESULT": f"{RESULT_DIR}/result.json",
            "HOME": "/tmp",
            "PYTHONPATH": f"{WORKDIR}:{PROBE_DIR}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "COVERAGE_FILE": f"{RESULT_DIR}/coverage",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        from corsair.domain.verification import Outcome

        tests, native = read_junit(files.get(f"{RESULT_DIR}/junit.xml"))
        record = files.get(f"{RESULT_DIR}/result.json")
        covered_target, covered_lines = read_coverage(files.get(f"{RESULT_DIR}/coverage.json"), hypothesis)
        exception_type = message = None
        outcome = Outcome.NOT_RUN
        if record is None or tests == 0:
            message = native or "the test never ran (collection or import error)"
        else:
            try:
                parsed = load_json(record)
                outcome = Outcome(parsed["outcome"])
                exception_type, message = parsed.get("exception_type"), parsed.get("message")
                role = parsed["role"]
                if role not in ("control", "exploit") or tests != 1:
                    raise ValueError("expected exactly one control or exploit test")
                if outcome is Outcome.VIOLATED and (
                    parsed.get("raised_in_probe") is not True or exception_type != "AssertionError"
                ):
                    raise ValueError("violation must be the probe's own assertion")
                if (outcome is Outcome.HOLDS) != (native is None):
                    raise ValueError(f"native report disagrees with the driver record: {native}")
                root = ET.fromstring(files[f"{RESULT_DIR}/junit.xml"])
                test = next(root.iter("testcase"))
                if test.get("name") != f"test_probe[{role}]":
                    raise ValueError("native test id disagrees with the recorded payload role")
                if message is not None and not isinstance(message, str):
                    raise ValueError("invalid driver message")
            except (ValueError, TypeError, KeyError, StopIteration, ET.ParseError) as error:
                outcome, message = Outcome.ERRORED, f"invalid probe evidence: {error}"[:2000]
        return ProbeResult(outcome, exception_type, message, tests, covered_target, covered_lines)


def read_junit(data: bytes | None) -> tuple[int, str | None]:
    """Count native test cases and identify the first failure; malformed reports never pass."""
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


def target_path(path: str, target: str) -> bool:
    """Bind a report entry to one exact source path, never a basename or suffix."""
    if not isinstance(path, str) or ".." in path.split("/"):
        return False
    absolute = posixpath.normpath(path if path.startswith("/") else f"{WORKDIR}/{path}")
    return absolute == f"{WORKDIR}/{target}"


def read_coverage(data: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """Read coverage.py JSON; missing, malformed and duplicate target entries fail closed."""
    if not data:
        return None, ()
    try:
        report = load_json(data)
        matching = [
            info for path, info in report["files"].items() if target_path(path, hypothesis.target_file)
        ]
        if len(matching) != 1:
            return False, ()
        lines = matching[0]["executed_lines"]
        if not isinstance(lines, list) or any(type(line) is not int or line < 1 for line in lines):
            return None, ()
        executed = set(lines)
        return bool(executed), tuple(sorted(executed & set(hypothesis.target_lines)))
    except (ValueError, TypeError, KeyError, AttributeError):
        return None, ()
