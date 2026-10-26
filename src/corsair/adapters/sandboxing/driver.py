#!/usr/bin/env python3
"""Trusted in-image driver for the initial Python secret-disclosure recipe.

This program is intentionally not an agent tool.  It receives an operator-created,
JSON-only job, writes a fixed pytest test, runs it through coverage.py, and emits one
strict JSON record on stdout.  Target stdout/stderr are captured by pytest and never
become driver output.  The driver does not print target values, exception messages,
or the random private fixture.

Threat limit: the target remains arbitrary Python within a constrained container.  The
record is evidence of the fixed driver assertion under that isolation boundary, not a
proof against a hostile interpreter/kernel/daemon or an arbitrary build dependency.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as element_tree
from contextlib import suppress
from pathlib import Path, PurePosixPath

JOB_PATH = Path("/input/job.json")
WORK = Path("/work")
JUNIT = WORK / "junit.xml"
COVERAGE = WORK / "coverage.json"
TEST = WORK / "test_recipe.py"
COVERAGE_REPORT_TIMEOUT_SECONDS = 30

# Each recipe kind has one fixed test template. A single violation marker per kind is
# written by this trusted code only when its own assertion genuinely fails, so a target
# cannot forge a violation by failing pytest some other way. The verifier admits exactly
# these markers; keep them in sync with steps/verification.py.
VIOLATION_MARKERS = {"disclosure", "sentinel_created"}


# Shared helpers loaded into every in-container test template.
_COMMON_PREFIX = r"""
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath

JOB = json.loads(Path("/input/job.json").read_text(encoding="utf-8"))


def _module_path():
    raw = JOB["recipe"]["module_file"]
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise RuntimeError("invalid trusted recipe module path")
    return Path("/source").joinpath(*path.parts)


def _load_target():
    module_path = _module_path()
    spec = importlib.util.spec_from_file_location("corsair_recipe_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("target module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = getattr(module, JOB["recipe"]["function"], None)
    if not callable(target):
        raise RuntimeError("recipe function is absent or not callable")
    return target


def _invoke():
    arguments = dict(JOB["recipe"]["fixed_kwargs"])
    arguments[JOB["recipe"]["payload_parameter"]] = JOB["payload"]
    return _load_target()(**arguments)


def _observation(kind):
    Path("/work/observation.json").write_text(json.dumps({"kind": kind}))


def _qualified(exc):
    return f"{type(exc).__module__}.{type(exc).__qualname__}"
"""


_DISCLOSURE_TEST = r"""
def _render(value):
    # The relevant property is the real secret occurring in a returned JSON value,
    # not a representation, a marker, or an agent-provided expected string.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _secret():
    return Path("/fixtures/private/secret.txt").read_text(encoding="utf-8")


def test_operator_owned_recipe_assertions():
    if JOB["role"] == "control":
        result = _invoke()
        rendered = _render(result)
        valid = _secret() not in rendered and result == JOB["recipe"]["expected_control"]
        _observation("held" if valid else "invalid_control")
        assert valid, "control did not preserve expected public behavior"
        return

    try:
        result = _invoke()
    except BaseException as exc:
        # pytest.Failed and SystemExit bypass Exception. A target must not turn
        # its own failure signal plus a forged marker into observer disclosure.
        if _qualified(exc) not in JOB["recipe"]["allowed_exceptions"]:
            _observation("execution_error")
            raise RuntimeError("unexpected target exception") from None
        _observation("held")
        return
    rendered = _render(result)
    disclosed = _secret() in rendered
    _observation("disclosure" if disclosed else "held")
    assert not disclosed, "adversarial result disclosed the private fixture"
"""


_SENTINEL_TEST = r"""
SENTINEL = JOB["recipe"]["sentinel_path"]


def _sentinel_created():
    return os.path.exists(SENTINEL)


def test_operator_owned_recipe_assertions():
    # Each role runs in a fresh container, so the sentinel never pre-exists; remove any
    # stray path defensively before invoking so only this invocation can create it.
    try:
        os.remove(SENTINEL)
    except OSError:
        pass

    if JOB["role"] == "control":
        try:
            _invoke()
        except BaseException:
            # The benign control payload must exercise normal behavior, not raise.
            _observation("invalid_control")
            assert False, "control payload did not preserve normal behavior"
        if _sentinel_created():
            _observation("invalid_control")
            assert False, "benign control payload created the operator sentinel file"
        _observation("held")
        return

    try:
        _invoke()
    except BaseException as exc:
        # A command/code-execution payload may legitimately raise after its side
        # effect; a disallowed exception without the side effect is an observer error.
        if _qualified(exc) not in JOB["recipe"]["allowed_exceptions"] and not _sentinel_created():
            _observation("execution_error")
            raise RuntimeError("unexpected target exception") from None
    created = _sentinel_created()
    _observation("sentinel_created" if created else "held")
    assert not created, "adversarial payload created the operator sentinel file"
"""


TEST_TEMPLATES = {
    "python.secret_disclosure/1": _COMMON_PREFIX + _DISCLOSURE_TEST,
    "python.command_sentinel/1": _COMMON_PREFIX + _SENTINEL_TEST,
}

# Retained name for the initial recipe's template; tests and readers reference it.
TEST_SOURCE = TEST_TEMPLATES["python.secret_disclosure/1"]


def _safe_job(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("job must be an object")
    required = {
        "schema_version",
        "operation_id",
        "role",
        "source_digest",
        "submission_digest",
        "recipe",
        "payload",
    }
    if set(value) != required or value.get("schema_version") != "corsair.driver-job/1":
        raise ValueError("job has an unsupported schema")
    if value["role"] not in {"control", "adversarial"}:
        raise ValueError("unsupported role")
    if not isinstance(value["recipe"], dict):
        raise ValueError("recipe must be an object")
    if value["recipe"].get("kind") not in TEST_TEMPLATES:
        raise ValueError("unsupported recipe kind")
    return value


def _junit_status(exit_code: int) -> tuple[str, dict[str, int]]:
    try:
        root = element_tree.parse(JUNIT).getroot()
        cases = root.findall(".//testcase")
        if len(cases) != 1:
            return "INVALID", {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
        case = cases[0]
        failures = len(case.findall("failure"))
        errors = len(case.findall("error"))
        skipped = len(case.findall("skipped"))
        counts = {"tests": 1, "failures": failures, "errors": errors, "skipped": skipped}
        if exit_code == 0 and not failures and not errors and not skipped:
            return "PASS", counts
        if exit_code != 0 and failures == 1 and not errors and not skipped:
            return "FAILURE", counts
        if exit_code != 0 and errors == 1 and not failures and not skipped:
            return "ERROR", counts
        return "INVALID", counts
    except (OSError, element_tree.ParseError):
        return "MISSING", {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


def _coverage_lines(module_file: str) -> list[int]:
    try:
        document = json.loads(COVERAGE.read_text(encoding="utf-8"))
        expected = str(Path("/source") / PurePosixPath(module_file))
        entry = document.get("files", {}).get(expected, {})
        lines = entry.get("executed_lines", [])
        if not isinstance(lines, list) or any(type(line) is not int or line < 1 for line in lines):
            return []
        return sorted(set(lines))
    except (OSError, TypeError, ValueError):
        return []


def _child_environment() -> dict[str, str]:
    """Return the complete, fixed environment for the pytest and coverage children."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "COVERAGE_FILE": str(WORK / ".coverage"),
        # Line measurement through PEP 669 sys.monitoring. The default C tracer traces
        # every pytest/stdlib frame before discarding it as outside --source, which
        # roughly doubled each role's in-container time; executed lines are identical.
        # If sys.monitoring were unavailable, coverage.py falls back to its default core.
        "COVERAGE_CORE": "sysmon",
    }


def main() -> int:
    try:
        job = _safe_job(json.loads(JOB_PATH.read_text(encoding="utf-8")))
    except Exception:
        # There is no secret-bearing input in this message, but do not reflect job
        # parser errors that could contain an untrusted value.
        print(
            json.dumps(
                {"schema_version": "corsair.driver/1", "driver_error": "invalid job"},
                separators=(",", ":"),
            )
        )
        return 2

    WORK.mkdir(parents=True, exist_ok=True)
    TEST.write_text(textwrap.dedent(TEST_TEMPLATES[job["recipe"]["kind"]]), encoding="utf-8")
    environment = _child_environment()
    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--source=/source",
        "-m",
        "pytest",
        "-q",
        f"--junitxml={JUNIT}",
        str(TEST),
    ]
    try:
        # DockerSandbox owns the wall-clock probe deadline and stops the whole
        # container on expiry. Do not add a second target-execution timeout here.
        completed = subprocess.run(
            command,
            cwd=WORK,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        exit_code = completed.returncode
    except OSError:
        exit_code = 2

    # Coverage reporting happens only after pytest exits, so a normal target return
    # cannot write the driver record. Its allowance is bounded here, while DockerSandbox's
    # container deadline continues to govern the whole driver process. Failure to produce
    # coverage remains invalid.
    with suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", str(COVERAGE)],
            cwd=WORK,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=COVERAGE_REPORT_TIMEOUT_SECONDS,
        )

    status, junit = _junit_status(exit_code)
    try:
        observed = json.loads((WORK / "observation.json").read_text()).get("kind")
    except (OSError, ValueError, AttributeError):
        observed = None
    if status == "PASS" and observed == "held":
        outcome = "PROPERTY_HELD"
    elif status == "FAILURE" and observed in VIOLATION_MARKERS and job["role"] == "adversarial":
        outcome = "VIOLATION"
    elif status == "FAILURE" and observed == "invalid_control":
        outcome, status = "INVALID", "INVALID"
    else:
        outcome, status = "ERROR", "ERROR"
    record = {
        "schema_version": "corsair.driver/1",
        "operation_id": job["operation_id"],
        "role": job["role"],
        "source_digest": job["source_digest"],
        "submission_digest": job["submission_digest"],
        "native_exit_code": exit_code,
        "junit": {"status": status, **junit},
        "outcome": outcome,
        "observation_kind": observed,
        "target_executed": observed in {"held", "invalid_control"} | VIOLATION_MARKERS,
        "covered_lines": _coverage_lines(job["recipe"].get("module_file", "")),
        "coverage_file": job["recipe"].get("module_file", ""),
    }
    print(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    # This is deliberately pytest's native status, not a boolean success inversion.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
