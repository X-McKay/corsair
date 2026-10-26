#!/usr/bin/env python3
"""Trusted in-image driver for the C integer-overflow recipe (c.integer_overflow/1).

This program is not an agent tool. It receives an operator-created, JSON-only job,
writes a FIXED C harness from the job (the model controls only one integer length),
compiles the admitted source plus that harness under AddressSanitizer with gcov line
coverage, runs the control or adversarial length, parses the sanitizer report and the
gcov record for the target file, and emits exactly one strict ``corsair.driver/1``
record on stdout. It never runs the target's Makefile or any target-authored build
step, never prints target stdout/stderr, and never prints a sanitizer address, a
length payload, or any target bytes.

Trusted assertion, and the crash/violation boundary: a VIOLATION is admitted ONLY
when AddressSanitizer emits a machine-readable report for the operator-fixed class in
a frame that names the admitted target file. A plain crash, a signal, a non-sanitizer
abort, a compile failure, or missing coverage is ERROR (operational), never VIOLATION.
The record shares the Python driver's ``corsair.driver/1`` schema so the one kernel
verifier (`EvidenceVerifier._validate_raw`) admits it unchanged, except that the
violation ``observation_kind`` is ``sanitizer_report`` rather than ``disclosure``.

Threat limit: the target remains arbitrary C in a constrained, offline container with
all capabilities dropped. The record is evidence of the fixed driver assertion under
that isolation boundary, not a defence against a hostile compiler, kernel or daemon.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

JOB_PATH = Path("/input/job.json")
WORK = Path("/work")
HARNESS = WORK / "harness.c"
PROG = WORK / "prog"
RUN_LOG = WORK / "run.log"
KIND = "c.integer_overflow/1"
# AddressSanitizer exits with this code when it halts on the first error; the harness
# itself returns 0 on a clean run. The driver maps both to its own record exit code.
ASAN_EXITCODE = 86
COMPILE_TIMEOUT_SECONDS = 60
GCOV_TIMEOUT_SECONDS = 30

# Fixed harness. {function} is the admitted callable name, {fill} the operator-fixed
# source byte, {length} the model-controlled length rendered as a decimal literal.
# The signature is fixed by the recipe kind: char *f(const char *buf, unsigned short len).
HARNESS_SOURCE = r"""
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <sanitizer/common_interface_defs.h>

extern void __gcov_dump(void);
extern char *{function}(const char *buf, unsigned short len);

/* Flush gcov counters before AddressSanitizer terminates the process, so the target
   line is still measured on the adversarial run that aborts at the sink. */
static void corsair_death_callback(void) {{ __gcov_dump(); }}

int main(void) {{
    __sanitizer_set_death_callback(corsair_death_callback);
    unsigned short len = (unsigned short){length}u;
    size_t srcn = len ? (size_t)len : (size_t)1;
    char *src = (char *)malloc(srcn);
    if (src == NULL) {{
        return 70;
    }}
    memset(src, {fill}, (size_t)len);
    char *result = {function}(src, len);
    unsigned long long observed = result ? (unsigned long long)strlen(result) : 0ULL;
    FILE *obs = fopen("/work/public.txt", "w");
    if (obs != NULL) {{
        fprintf(obs, "%llu\n", observed);
        fclose(obs);
    }}
    free(result);
    free(src);
    return 0;
}}
"""


def _driver_error(reason: str) -> int:
    print(
        json.dumps(
            {"schema_version": "corsair.driver/1", "driver_error": reason},
            separators=(",", ":"),
        )
    )
    return 2


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
    recipe = value["recipe"]
    if not isinstance(recipe, dict) or recipe.get("kind") != KIND:
        raise ValueError("recipe kind is not c.integer_overflow/1")
    payload = value["payload"]
    if type(payload) is not int or payload < 0 or payload > 0xFFFF:
        raise ValueError("payload must be a length in [0, 65535]")
    return value


def _module_path(module_file: str) -> Path:
    path = PurePosixPath(module_file)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("invalid trusted recipe module path")
    return Path("/source").joinpath(*path.parts)


def _function(recipe: dict) -> str:
    name = recipe.get("function")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("recipe function is not a C identifier")
    return name


def _fill_byte(recipe: dict) -> int:
    fill = recipe.get("fill_byte", 65)
    if type(fill) is not int or fill < 1 or fill > 126:
        raise ValueError("fill_byte must be a printable, non-NUL byte")
    return fill


def _write_harness(recipe: dict, payload: int) -> None:
    HARNESS.write_text(
        HARNESS_SOURCE.format(function=_function(recipe), fill=_fill_byte(recipe), length=payload),
        encoding="utf-8",
    )


def _compile(module_file: str) -> subprocess.CompletedProcess[bytes]:
    command = [
        "gcc",
        "-std=c11",
        "-O0",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-fno-sanitize-recover=all",
        "--coverage",
        "-o",
        str(PROG),
        str(_module_path(module_file)),
        str(HARNESS),
    ]
    return subprocess.run(
        command,
        cwd=WORK,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=COMPILE_TIMEOUT_SECONDS,
    )


def _run() -> int:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/tmp",
        "ASAN_OPTIONS": (
            f"halt_on_error=1:abort_on_error=0:exitcode={ASAN_EXITCODE}:"
            "detect_leaks=0:log_path=stderr"
        ),
        "UBSAN_OPTIONS": (
            f"halt_on_error=1:abort_on_error=0:exitcode={ASAN_EXITCODE}:print_stacktrace=1"
        ),
    }
    # DockerSandbox owns the wall-clock probe deadline and stops the whole container on
    # expiry. The driver captures the target's own stderr to a file; it never becomes
    # driver stdout.
    with RUN_LOG.open("wb") as log:
        completed = subprocess.run(
            [str(PROG)],
            cwd=WORK,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log,
            check=False,
        )
    return completed.returncode


_SANITIZER_LINE = re.compile(r"^.*ERROR: (AddressSanitizer|UndefinedBehaviorSanitizer): (\S+)")


def _sanitizer_report(module_file: str, sanitizer_class: str) -> str | None:
    """Return the matched sanitizer class only when a frame names the admitted target.

    Requiring the target file in a stack frame keeps the assertion bound to the
    finding: an incidental sanitizer error elsewhere is not this row's violation.
    """
    try:
        text = RUN_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    detected: str | None = None
    for line in text.splitlines():
        match = _SANITIZER_LINE.match(line)
        if match is not None:
            detected = match.group(2)
            break
    if detected is None or detected != sanitizer_class:
        return None
    target = PurePosixPath(module_file).name
    names_target = re.search(rf"[ /]{re.escape(target)}:\d+", text) is not None
    return sanitizer_class if names_target else None


def _coverage_lines(module_file: str) -> list[int]:
    """Executed source lines for the target file, from gcov's JSON record."""
    stem = Path(module_file).stem
    gcno = WORK / f"prog-{stem}"
    try:
        completed = subprocess.run(
            ["gcov", "--json-format", "--stdout", str(gcno)],
            cwd=WORK,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GCOV_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    executed: set[int] = set()
    target = PurePosixPath(module_file).name
    for raw in completed.stdout.decode("utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            document = json.loads(raw)
        except ValueError:
            continue
        for entry in document.get("files", []):
            if PurePosixPath(str(entry.get("file", ""))).name != target:
                continue
            for record in entry.get("lines", []):
                number = record.get("line_number")
                count = record.get("count")
                if type(number) is int and number >= 1 and type(count) is int and count > 0:
                    executed.add(number)
    return sorted(executed)


def _control_observation(recipe: dict, sanitizer: str | None) -> str:
    try:
        observed = int((WORK / "public.txt").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "invalid_control"
    expected = recipe.get("expected_control_length")
    if sanitizer is not None or type(expected) is not int or observed != expected:
        return "invalid_control"
    return "held"


def _adversarial_observation(sanitizer: str | None, run_exit: int) -> str:
    if sanitizer is not None:
        return "sanitizer_report"
    if run_exit == 0:
        return "held"
    # A non-zero run without a parseable, target-bound sanitizer report is a crash or a
    # non-sanitizer abort: operational error, never a violation.
    return "execution_error"


def _record(
    job: dict,
    *,
    native_exit: int,
    status: str,
    outcome: str,
    observation: str,
    lines: list[int],
    module_file: str,
    target_executed: bool,
) -> dict:
    counts = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}
    if status == "FAILURE":
        counts["failures"] = 1
    elif status == "ERROR":
        counts["errors"] = 1
    return {
        "schema_version": "corsair.driver/1",
        "operation_id": job["operation_id"],
        "role": job["role"],
        "source_digest": job["source_digest"],
        "submission_digest": job["submission_digest"],
        "native_exit_code": native_exit,
        "junit": {"status": status, **counts},
        "outcome": outcome,
        "observation_kind": observation,
        "target_executed": target_executed,
        "covered_lines": lines,
        "coverage_file": module_file,
    }


def main() -> int:
    try:
        job = _safe_job(json.loads(JOB_PATH.read_text(encoding="utf-8")))
    except Exception:
        return _driver_error("invalid job")

    WORK.mkdir(parents=True, exist_ok=True)
    recipe = job["recipe"]
    module_file = recipe.get("module_file")
    if not isinstance(module_file, str) or not module_file.endswith(".c"):
        return _driver_error("invalid job")

    try:
        _write_harness(recipe, int(job["payload"]))
        compiled = _compile(module_file)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        record = _record(
            job,
            native_exit=2,
            status="ERROR",
            outcome="ERROR",
            observation="compile_error",
            lines=[],
            module_file=module_file,
            target_executed=False,
        )
        print(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 2
    if compiled.returncode != 0:
        record = _record(
            job,
            native_exit=2,
            status="ERROR",
            outcome="ERROR",
            observation="compile_error",
            lines=[],
            module_file=module_file,
            target_executed=False,
        )
        print(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 2

    try:
        run_exit = _run()
    except OSError:
        run_exit = -1
    sanitizer_class = recipe.get("sanitizer_class", "heap-buffer-overflow")
    sanitizer = _sanitizer_report(
        module_file, sanitizer_class if isinstance(sanitizer_class, str) else ""
    )
    lines = _coverage_lines(module_file)

    if job["role"] == "control":
        observation = _control_observation(recipe, sanitizer)
    else:
        observation = _adversarial_observation(sanitizer, run_exit)

    if observation == "held":
        native_exit, status, outcome = 0, "PASS", "PROPERTY_HELD"
    elif observation == "sanitizer_report" and job["role"] == "adversarial":
        native_exit, status, outcome = 1, "FAILURE", "VIOLATION"
    elif observation == "invalid_control":
        native_exit, status, outcome = 3, "INVALID", "INVALID"
    else:
        native_exit, status, outcome = 2, "ERROR", "ERROR"

    record = _record(
        job,
        native_exit=native_exit,
        status=status,
        outcome=outcome,
        observation=observation,
        lines=lines,
        module_file=module_file,
        target_executed=observation in {"held", "sanitizer_report", "invalid_control"},
    )
    print(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return native_exit


if __name__ == "__main__":
    raise SystemExit(main())
