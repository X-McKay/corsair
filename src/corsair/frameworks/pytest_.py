"""Python / pytest adapter: the reference implementation of the framework contract.

The probe is a Python module defining ``CONTROL_PAYLOAD``, ``EXPLOIT_PAYLOAD`` and ``run_target(payload)``. The
driver is a pytest file with one parametrized test id per payload; each run executes one id under coverage.py,
collects repository coverage from Python children too, and records how ``run_target`` ended.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping

from .base import PROBE_DIR, RESULT_DIR, WORKDIR, PostCommand, ProbeResult
from .reports import read_coverage, read_probe

BANNED_IMPORTS = ("unittest.mock", "mock", "pytest_mock", "responses", "httpretty", "requests_mock")
REQUIRED_SYMBOLS = ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target")

COVERAGE_RC = f'''[run]
parallel = true
patch = subprocess
source = {WORKDIR}
data_file = {RESULT_DIR}/coverage
'''

COVERAGE_LAUNCHER = f'''"""Reset role-local data before enabling coverage's Python startup hook."""
import os
import sys

for entry in os.scandir("{RESULT_DIR}"):
    name = entry.name
    if name == "coverage.json":
        continue
    if (name == "coverage" or name.startswith("coverage.")
            or name in ("coverage-journal", "coverage-shm", "coverage-wal")):
        os.unlink(entry.path)

os.execv(sys.executable, [sys.executable, "-m", "coverage", "run", *sys.argv[1:]])
'''

COVERAGE_RENDERER = f'''"""Merge role data without treating the preserved JSON report as a shard."""
import os

from coverage import Coverage

paths = sorted(entry.path for entry in os.scandir("{RESULT_DIR}")
               if entry.name.startswith("coverage.") and entry.name != "coverage.json")
if not paths:
    raise RuntimeError("no coverage data files were produced")
coverage = Coverage(config_file="{PROBE_DIR}/coverage.rc")
coverage.combine(data_paths=paths, strict=True)
coverage.save()
coverage.json_report(outfile="{RESULT_DIR}/coverage.json")
'''

DRIVER = '''"""Kernel-owned driver: one native pytest test id per payload through the submitted run_target."""
import json
import os
import sys

import pytest

_DUMPS = json.dumps
_OPEN = open
_STR = str
_TYPE = type
_BOOL = bool
_TYPE_ERROR = TypeError
_ASSERTION_ERROR = AssertionError
_BASE_EXCEPTION = BaseException
_PARAMETRIZE = pytest.mark.parametrize
ROLE = os.environ["CORSAIR_ROLE"]
RESULT = os.environ["CORSAIR_RESULT"]
EXPECTED = ROLE == "control"

for _path in ("/work/.corsair", "/work"):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import corsair_probe as probe  # noqa: E402

PAYLOADS = {"control": probe.CONTROL_PAYLOAD, "exploit": probe.EXPLOIT_PAYLOAD}


def _record(result, invariant_held=None, exc=None):
    record = {"role": ROLE, "result": result, "invariant_held": invariant_held,
              "exception_type": _TYPE(exc).__name__ if exc is not None else None,
              "message": _STR(exc)[:2000] if exc is not None else None}
    with _OPEN(RESULT, "w") as handle:
        handle.write(_DUMPS(record))


@_PARAMETRIZE("role", [ROLE])
def test_probe(role):
    try:
        invariant = probe.run_target(PAYLOADS[role])
        if _TYPE(invariant) is not _BOOL:
            raise _TYPE_ERROR("run_target(payload) must return a boolean security invariant")
    except _BASE_EXCEPTION as exc:
        _record("ERROR", exc=exc)
        raise
    result = "PASS" if invariant == EXPECTED else "FAIL"
    _record(result, invariant)
    if result == "FAIL":
        raise _ASSERTION_ERROR("security invariant did not match the role expectation")
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
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_target":
            if (len(node.args.posonlyargs) + len(node.args.args) != 1 or node.args.vararg
                    or node.args.kwonlyargs or node.args.kwarg):
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
    target_suffixes = (".py",)
    guidance = "python-pytest"
    probe_file = "corsair_probe.py"

    def guard(self, probe: str):
        return ast_guard(probe)

    def driver_files(self) -> dict[str, bytes]:
        return {"test_corsair_probe.py": DRIVER.encode(), "coverage.rc": COVERAGE_RC.encode(),
                "run_coverage.py": COVERAGE_LAUNCHER.encode(), "render_coverage.py": COVERAGE_RENDERER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        # -S keeps installed startup hooks from collecting before the launcher clears old data.
        return ["python", "-S", f"{PROBE_DIR}/run_coverage.py", "-m", "pytest",
                "-p", "no:cacheprovider", "-c", "/dev/null", "--rootdir", WORKDIR, "--noconftest",
                "--import-mode=importlib", "-q", f"--junitxml={RESULT_DIR}/junit.xml",
                "-o", "junit_logging=all", "-o", "junit_log_passing_tests=true",
                f"{PROBE_DIR}/test_corsair_probe.py"]

    def post_command(self, role: str, target_file: str) -> PostCommand:
        """Merge parent/child data and render without starting another coverage collector."""
        environment = dict(self.environment(role))
        for variable in ("COVERAGE_PROCESS_START", "COVERAGE_PROCESS_CONFIG"):
            environment.pop(variable, None)
        return PostCommand(("python", f"{PROBE_DIR}/render_coverage.py"), environment)

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json", "HOME": "/tmp",
                "PYTHONPATH": f"{WORKDIR}:{PROBE_DIR}", "PYTHONDONTWRITEBYTECODE": "1",
                "COVERAGE_FILE": f"{RESULT_DIR}/coverage", "COVERAGE_RCFILE": f"{PROBE_DIR}/coverage.rc",
                "COVERAGE_PROCESS_START": f"{PROBE_DIR}/coverage.rc"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source=None) -> ProbeResult:
        return read_probe(files, hypothesis, role)
