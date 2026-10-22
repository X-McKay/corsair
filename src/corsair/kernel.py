"""The verdict kernel: deterministic gates around one differential probe, run in twin sandboxes.

A submission is a hypothesis, a build script and one probe module that defines ``CONTROL_PAYLOAD``,
``EXPLOIT_PAYLOAD`` and ``run_target(payload)``. The kernel never trusts the producer's workspace: it replays the
build script in a clean container, seals the result as an image, and runs each payload alone in a fresh offline
container from that image, on the vulnerable revision and, when the case has one, the fixed revision.

Gates, in order; the first failure is returned to the producer as a ``GateVerdict``:

1. ``ast_guard``: the probe parses, defines the three symbols and imports no mocking library.
2. ``build_replay``: the build script succeeds in a clean container (network only during this step).
3. ``control_run`` / ``control_coverage``: ``run_target(CONTROL_PAYLOAD)`` holds on the vulnerable revision and
   executes the hypothesis' target lines.
4. ``exploit_run`` / ``exploit_coverage``: ``run_target(EXPLOIT_PAYLOAD)`` violates the probe's own invariant
   assertion on the vulnerable revision (an ``AssertionError`` raised from the probe, not from application code) and
   executes the target lines.
5. ``blind_audit``: a stateless auditor that sees the hypothesis and probe only, never an outcome.

Polarity: ``violated`` means the probe's safety invariant failed, i.e. the reported condition occurred. The fixed
revision is run after the gates and never rejects a submission; it decides fix verification.

The two payloads run as two native pytest test ids (``test_probe[control]``, ``test_probe[exploit]``) through one
driver, so "exactly two native probes through the same seam" holds by construction. The runner records the native
JUnit report, a coverage report for the target file and a small classification file; the kernel reads nothing else.
"""
from __future__ import annotations

import ast
import hashlib
import json
import posixpath
import shlex
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .artifacts import ArtifactRef, ArtifactStore
from .case import Case, Frozen, Revision, SafePath
from .matrix import Row
from .sandbox.port import Exec, Sandboxes, SandboxExists, SandboxSpec, labels, sandbox_name

BUILD_TIMEOUT_S = 1800.0
PROBE_TIMEOUT_S = 300.0
TAIL = 4000
ENV_REPOSITORY = "corsair-lite-env"
ENV_SCHEMA = "corsair-lite/env/3"
"""Part of every environment key; bump it when what a sealed environment contains or who owns it changes."""
WORKDIR = "/work"
PROBE_DIR = f"{WORKDIR}/.corsair"
RESULT_DIR = "/tmp/corsair"
BANNED_IMPORTS = ("unittest.mock", "mock", "pytest_mock", "responses", "httpretty", "requests_mock")
REQUIRED_SYMBOLS = ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target")

Role = Literal["control", "exploit"]
RevisionName = Literal["vulnerable", "fixed"]


class Hypothesis(Frozen):
    target_file: SafePath = Field(description="Path of the vulnerable source file, relative to the repository root")
    target_symbol: str = Field(min_length=1, max_length=256, description="Function or method holding the flaw")
    target_lines: tuple[int, ...] = Field(min_length=1, max_length=64, description="Lines that both payloads must execute")
    root_cause: str = Field(min_length=1, max_length=2_000, description="The mechanism of the bug, one or two sentences")
    expected_violation: str = Field(min_length=1, max_length=1_000,
                                    description="What the invariant assertion observes when EXPLOIT_PAYLOAD runs")

    @field_validator("target_lines")
    @classmethod
    def _positive(cls, lines: tuple[int, ...]) -> tuple[int, ...]:
        if any(line < 1 for line in lines):
            raise ValueError("target lines are 1-based")
        return tuple(sorted(set(lines)))


class Submission(Frozen):
    hypothesis: Hypothesis
    build_script: str = Field(default="", max_length=16_000,
                              description="bash run once in a clean container with network, from the repository "
                                          "root; empty when the project needs nothing installed")
    probe: str = Field(min_length=1, max_length=32_000,
                       description="One Python module defining CONTROL_PAYLOAD, EXPLOIT_PAYLOAD and "
                                   "run_target(payload) -> None, whose invariant assertion fails only when the "
                                   "reported condition occurs")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class Gate(StrEnum):
    TARGET_BINDING = "target_binding"
    AST_GUARD = "ast_guard"
    BUILD_REPLAY = "build_replay"
    CONTROL_RUN = "control_run"
    CONTROL_COVERAGE = "control_coverage"
    EXPLOIT_RUN = "exploit_run"
    EXPLOIT_COVERAGE = "exploit_coverage"
    BLIND_AUDIT = "blind_audit"
    FIX_RUN = "fix_run"
    INFRA = "infra"
    VERIFIED = "verified"


class GateVerdict(Frozen):
    passed: bool
    stage: Gate
    reason: str = Field(max_length=4_000)
    stdout_tail: str = Field(default="", max_length=TAIL)
    stderr_tail: str = Field(default="", max_length=TAIL)


class Outcome(StrEnum):
    HOLDS = "holds"          # run_target returned: the invariant held
    VIOLATED = "violated"    # the probe's own assertion failed: the reported condition occurred
    ERRORED = "errored"      # another exception, or an assertion raised by application code
    NOT_RUN = "not_run"      # the test never ran (import or collection error, no test found)
    INFRA = "infra"          # timeout, container failure or unreadable results


class ProbeRun(Frozen):
    revision: RevisionName
    role: Role
    outcome: Outcome
    exception_type: str | None = None
    message: str | None = Field(default=None, max_length=2_000)
    exit_code: int | None
    junit_tests: int = Field(ge=0, description="Test cases the native JUnit report lists")
    covered_target: bool | None = Field(default=None, description="The target file executed at all; None unknown")
    covered_lines: tuple[int, ...] = Field(default=(), description="Hypothesis lines the run executed")
    duration_s: float | None = None
    output: ArtifactRef | None = None
    junit: ArtifactRef | None = None
    cleanup_confirmed: bool | None = None


class AuditResult(Frozen):
    valid: bool
    reason: str = Field(max_length=2_000)


class Label(StrEnum):
    LIKELY_EXPLOITABLE = "LIKELY_EXPLOITABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNABLE_TO_RUN = "UNABLE_TO_RUN"
    ERROR = "ERROR"


class Fix(StrEnum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    NOT_APPLICABLE = "not_applicable"


class Verdict(Frozen):
    label: Label
    rule: str
    reason: str = Field(max_length=2_000)
    fix: Fix
    fix_reason: str = Field(default="", max_length=2_000)
    submission_sha256: str | None = None
    environment_image: str | None = None
    runs: tuple[ProbeRun, ...] = ()
    audit: AuditResult | None = None


class Evaluation(Frozen):
    """What one submission produced: the first failed gate, or ``verified`` with a verdict.

    One gate can fail while a verdict exists: ``fix_run``. The vulnerable-revision gates passed, so the label stands,
    but the exploit payload raised something other than the probe's assertion on the fixed revision, so the fix could
    not be verified and the producer may correct the probe within its budget.
    """

    submission: Submission
    submission_sha256: str
    gate: GateVerdict
    verdict: Verdict | None = None
    runs: tuple[ProbeRun, ...] = ()
    duration_s: float


# --- gate 0: the hypothesis is about the reported target -------------------------------------------------------------


def reported_target_present(case: Case) -> str | None:
    """None when the finding names no file or the file exists in the vulnerable tree; otherwise the reason the case
    cannot be investigated at all. Decided by trusted code before any model call."""
    path = case.finding.file_path
    if path is None:
        return None
    if not (Path(case.revision.source) / path).is_file():
        return f"the reported file {path} does not exist in the vulnerable revision"
    return None


def target_binding(case: Case, hypothesis: Hypothesis) -> GateVerdict:
    """The hypothesis must be about the file the finding reports. A finding that names no file accepts any existing
    file. The symbol is not checked structurally: a flaw may live in a helper the reported symbol calls, and the
    blind auditor judges relevance; the file is the binding trusted code can enforce."""
    reported = case.finding.file_path
    if reported is not None and hypothesis.target_file != reported:
        return GateVerdict(passed=False, stage=Gate.TARGET_BINDING,
                           reason=f"the finding reports {reported}; the hypothesis targets {hypothesis.target_file}. "
                                  "Investigate the reported file; if the reported condition cannot occur there, stop "
                                  "and say so instead of substituting another target")
    if not (Path(case.revision.source) / hypothesis.target_file).is_file():
        return GateVerdict(passed=False, stage=Gate.TARGET_BINDING,
                           reason=f"{hypothesis.target_file} does not exist in the vulnerable revision")
    return GateVerdict(passed=True, stage=Gate.TARGET_BINDING, reason="hypothesis bound to the reported target")


# --- gate 1: the structural guard ----------------------------------------------------------------------------------


def ast_guard(probe: str) -> GateVerdict:
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


# --- the in-container runner -----------------------------------------------------------------------------------------

TEST_FILE = '''"""Kernel-owned driver: one native pytest test id per payload through the submitted run_target."""
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


def _tail(data: bytes) -> str:
    return data[-TAIL:].decode(errors="replace")


def _failure(result: Exec, what: str) -> str:
    if result.timed_out:
        return f"{what} timed out"
    if result.container_failed:
        return f"{what}: container failed"
    return f"{what} exited {result.exit_code}"


def environment_key(row: Row, tree_sha256: str, build_script: str) -> str:
    build_sha = hashlib.sha256(build_script.encode()).hexdigest()
    return hashlib.sha256(json.dumps([ENV_SCHEMA, row.id, row.image, tree_sha256, build_sha]).encode()).hexdigest()


class Kernel:
    def __init__(self, backend: Sandboxes, row: Row, case: Case, *, artifacts: ArtifactStore,
                 auditor: Callable[[Submission], Awaitable[AuditResult]] | None = None, run_id: str | None = None,
                 build_timeout: float = BUILD_TIMEOUT_S, probe_timeout: float = PROBE_TIMEOUT_S):
        self.backend = backend
        self.row = row
        self.case = case
        self.artifacts = artifacts
        self.auditor = auditor
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.build_timeout = build_timeout
        self.probe_timeout = probe_timeout
        self._attempt = 0
        if row.framework != "pytest":
            raise ValueError(f"the kernel supports pytest rows only; row {row.id} is {row.framework}")

    # -- gate 2: build replay -----------------------------------------------------------------------------------------

    def build(self, revision: Revision, name: RevisionName, build_script: str) -> tuple[str | None, GateVerdict]:
        """Replay the build script in a clean container and seal the result as an image; cached by exact key."""
        key = environment_key(self.row, revision.tree_sha256, build_script)
        tag = f"{ENV_REPOSITORY}:{key[:32]}"
        if self.backend.find_environment(tag, key) is not None:
            return tag, GateVerdict(passed=True, stage=Gate.BUILD_REPLAY, reason=f"environment cache hit {tag}")
        spec = SandboxSpec(image=self.row.image, workdir=WORKDIR,
                           labels=labels(self.run_id, "build", revision=name, env=key[:16]),
                           network="build" if build_script.strip() else "none")
        log: list[bytes] = []
        ours = True
        try:
            sandbox = self.backend.create(spec)
            self.backend.copy_tree_in(sandbox, Path(revision.source), WORKDIR)
            if build_script.strip():
                script = "set -euo pipefail\ncd /work\n" + build_script + "\n"
                self.backend.write_file(sandbox, f"{PROBE_DIR}/build.sh", script.encode())
                result = self.backend.exec_once(sandbox, ["bash", f"{PROBE_DIR}/build.sh"], workdir=WORKDIR,
                                                timeout=self.build_timeout)
                log.append(b"$ bash build.sh\n" + result.stdout + result.stderr)
                if result.exit_code != 0:
                    ref = self.artifacts.put(b"".join(log))
                    return None, GateVerdict(passed=False, stage=Gate.BUILD_REPLAY,
                                             reason=f"{_failure(result, 'build_script')} in a clean container "
                                                    f"({name} revision); log {ref.sha256[:12]}",
                                             stdout_tail=_tail(result.stdout), stderr_tail=_tail(result.stderr))
                self.backend.drop_network(sandbox)
            log_ref = self.artifacts.put(b"".join(log) or b"(no build script)\n")
            self.backend.seal_environment(sandbox, tag, key, log_ref.sha256, writable=[PROBE_DIR])
            return tag, GateVerdict(passed=True, stage=Gate.BUILD_REPLAY, reason=f"sealed {tag}")
        except Exception as error:  # create, copy or control-plane failure
            ours = not isinstance(error, SandboxExists)
            return None, GateVerdict(passed=False, stage=Gate.INFRA,
                                     reason=f"build infrastructure: {type(error).__name__}: {error}"[:4000])
        finally:
            if ours:
                self.backend.remove(spec.name)

    # -- gates 3 and 4: one payload, one fresh container ----------------------------------------------------------------

    def run_probe(self, image: str, submission: Submission, revision: RevisionName, role: Role) -> ProbeRun:
        target = submission.hypothesis.target_file
        self._attempt += 1
        sandbox_labels = labels(self.run_id, "probe", role, revision=revision, n=str(self._attempt))
        name = sandbox_name(sandbox_labels)
        env = {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json", "HOME": "/tmp",
               "PYTHONPATH": f"{WORKDIR}:{PROBE_DIR}",
               "PYTHONDONTWRITEBYTECODE": "1", "COVERAGE_FILE": f"{RESULT_DIR}/coverage"}
        argv = ["python", "-m", "coverage", "run", f"--include={WORKDIR}/{target}", "-m", "pytest",
                "-p", "no:cacheprovider", "-c", "/dev/null", "--rootdir", WORKDIR, "--noconftest",
                "--import-mode=importlib", "-q", f"--junitxml={RESULT_DIR}/junit.xml",
                "-o", "junit_logging=all", "-o", "junit_log_passing_tests=true",
                f"{PROBE_DIR}/test_corsair_probe.py"]
        output = b""
        started = time.monotonic()
        duration: float | None = None
        ours = True
        try:
            self.backend.open_environment(image, WORKDIR, sandbox_labels)
            self.backend.write_file(name, f"{PROBE_DIR}/corsair_probe.py", submission.probe.encode())
            self.backend.write_file(name, f"{PROBE_DIR}/test_corsair_probe.py", TEST_FILE.encode())
            made = self.backend.exec_once(name, ["mkdir", "-p", RESULT_DIR], workdir="/", timeout=60)
            if made.exit_code != 0:
                raise RuntimeError(f"cannot create {RESULT_DIR}: {made.stderr.decode(errors='replace')}")
            result = self.backend.exec_once(name, argv, workdir=WORKDIR, env=env, timeout=self.probe_timeout)
            duration = time.monotonic() - started
            output = b"$ " + shlex.join(argv).encode() + b"\n--- stdout ---\n" + result.stdout + b"\n--- stderr ---\n" + result.stderr
            if result.timed_out or result.container_failed:
                return self._infra(revision, role, result, output, duration, self.backend.remove(name) if ours else None)
            self.backend.exec_once(name, ["python", "-m", "coverage", "json", "-o", f"{RESULT_DIR}/coverage.json"],
                                   workdir=WORKDIR, env=env, timeout=120)
            files = self.backend.copy_out(name, [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml",
                                                 f"{RESULT_DIR}/coverage.json"])
            ours_removed = self.backend.remove(name)
            ours = False
            return self._classify(revision, role, result, output, duration, files, submission.hypothesis, ours_removed)
        except Exception as error:
            ours = not isinstance(error, SandboxExists)
            output += f"\n[infra: {type(error).__name__}: {error}]\n".encode()
            confirmed = self.backend.remove(name) if ours else None
            ours = False
            return ProbeRun(revision=revision, role=role, outcome=Outcome.INFRA, exception_type=type(error).__name__,
                            message=str(error)[:2000], exit_code=None, junit_tests=0, duration_s=duration,
                            output=self.artifacts.put(output), cleanup_confirmed=confirmed)
        finally:
            if ours:
                self.backend.remove(name)

    def _infra(self, revision: RevisionName, role: Role, result: Exec, output: bytes, duration: float | None,
               confirmed: bool | None) -> ProbeRun:
        return ProbeRun(revision=revision, role=role, outcome=Outcome.INFRA, exit_code=result.exit_code,
                        message="timed out" if result.timed_out else "container failed", junit_tests=0,
                        duration_s=duration, output=self.artifacts.put(output), cleanup_confirmed=confirmed)

    def _classify(self, revision: RevisionName, role: Role, result: Exec, output: bytes, duration: float,
                  files: dict[str, bytes | None], hypothesis: Hypothesis, confirmed: bool | None) -> ProbeRun:
        junit_bytes = files.get(f"{RESULT_DIR}/junit.xml")
        tests, native = _read_junit(junit_bytes)
        record = files.get(f"{RESULT_DIR}/result.json")
        covered_target, covered_lines = _read_coverage(files.get(f"{RESULT_DIR}/coverage.json"), hypothesis)
        exception_type = message = None
        if record is None or tests == 0:
            outcome = Outcome.NOT_RUN
            message = native or "the test never ran (collection or import error)"
        else:
            parsed = json.loads(record)
            outcome = Outcome(parsed["outcome"])
            exception_type, message = parsed.get("exception_type"), parsed.get("message")
            # The kernel's record and the native report must agree: a holds record with a failing JUnit case (or
            # the reverse) means something interfered with the run, which is not a decisive observation.
            if (outcome is Outcome.HOLDS) != (native is None):
                outcome, message = Outcome.ERRORED, f"native report disagrees with the driver record: {native}"
        return ProbeRun(revision=revision, role=role, outcome=outcome, exception_type=exception_type, message=message,
                        exit_code=result.exit_code, junit_tests=tests, covered_target=covered_target,
                        covered_lines=covered_lines, duration_s=duration, output=self.artifacts.put(output),
                        junit=self.artifacts.put(junit_bytes) if junit_bytes else None, cleanup_confirmed=confirmed)

    # -- the whole evaluation -------------------------------------------------------------------------------------------

    async def evaluate(self, submission: Submission) -> Evaluation:
        started = time.monotonic()
        runs: list[ProbeRun] = []

        def done(gate: GateVerdict, verdict: Verdict | None = None) -> Evaluation:
            return Evaluation(submission=submission, submission_sha256=submission.sha256, gate=gate, verdict=verdict,
                              runs=tuple(runs), duration_s=time.monotonic() - started)

        binding = target_binding(self.case, submission.hypothesis)
        if not binding.passed:
            return done(binding)
        guard = ast_guard(submission.probe)
        if not guard.passed:
            return done(guard)
        image, built = self.build(self.case.revision, "vulnerable", submission.build_script)
        if image is None:
            return done(built)

        control = self.run_probe(image, submission, "vulnerable", "control")
        runs.append(control)
        if control.outcome is Outcome.INFRA:
            return done(GateVerdict(passed=False, stage=Gate.INFRA, reason=f"control run: {control.message}"))
        if control.outcome is not Outcome.HOLDS:
            return done(GateVerdict(passed=False, stage=Gate.CONTROL_RUN,
                                    reason=f"CONTROL_PAYLOAD must hold on the vulnerable revision but was "
                                           f"{control.outcome}: {control.exception_type or ''} {control.message or ''}".strip(),
                                    **self._tails(control)))
        if not control.covered_lines:
            return done(GateVerdict(passed=False, stage=Gate.CONTROL_COVERAGE,
                                    reason=f"CONTROL_PAYLOAD held but did not execute {submission.hypothesis.target_file} "
                                           f"lines {list(submission.hypothesis.target_lines)}"
                                           + ("" if control.covered_target else " (the file never ran)")))

        exploit = self.run_probe(image, submission, "vulnerable", "exploit")
        runs.append(exploit)
        if exploit.outcome is Outcome.INFRA:
            return done(GateVerdict(passed=False, stage=Gate.INFRA, reason=f"exploit run: {exploit.message}"))
        if exploit.outcome is Outcome.HOLDS:
            return done(GateVerdict(passed=False, stage=Gate.EXPLOIT_RUN,
                                    reason="EXPLOIT_PAYLOAD did not violate the invariant on the vulnerable revision; "
                                           "the reported condition was not demonstrated"))
        if exploit.outcome is not Outcome.VIOLATED:
            return done(GateVerdict(passed=False, stage=Gate.EXPLOIT_RUN,
                                    reason=f"EXPLOIT_PAYLOAD must fail the probe's own invariant assertion, but the run "
                                           f"was {exploit.outcome}: {exploit.exception_type or ''} {exploit.message or ''}".strip(),
                                    **self._tails(exploit)))
        if not exploit.covered_lines:
            return done(GateVerdict(passed=False, stage=Gate.EXPLOIT_COVERAGE,
                                    reason=f"EXPLOIT_PAYLOAD failed before executing {submission.hypothesis.target_file} "
                                           f"lines {list(submission.hypothesis.target_lines)}"))

        audit: AuditResult | None = None
        if self.auditor is not None:
            audit = await self.auditor(submission)
            if not audit.valid:
                return done(GateVerdict(passed=False, stage=Gate.BLIND_AUDIT,
                                        reason=f"outcome-blind audit rejected the probe: {audit.reason}"))

        fix, fix_reason = Fix.NOT_APPLICABLE, "the case has no fixed revision"
        fix_gate: GateVerdict | None = None
        if self.case.fixed_revision is not None:
            fix, fix_reason = self._verify_fix(submission, runs)
            fixed_exploit = runs[-1] if len(runs) == 4 and runs[-1].revision == "fixed" else None
            if (fixed_exploit is not None and fixed_exploit.role == "exploit"
                    and fixed_exploit.outcome is Outcome.ERRORED and fixed_exploit.exception_type != "AssertionError"):
                fix_gate = GateVerdict(passed=False, stage=Gate.FIX_RUN,
                                       reason=f"the vulnerable revision is verified, but on the fixed revision "
                                              f"EXPLOIT_PAYLOAD raised {fixed_exploit.exception_type}: "
                                              f"{(fixed_exploit.message or '')[:500]}. If that exception is how the "
                                              "fix rejects the payload, catch it inside run_target and let the "
                                              "invariant decide; the fix is not verified until the exploit run holds there")
        verdict = Verdict(label=Label.LIKELY_EXPLOITABLE, rule="K1",
                          reason="control held and the exploit payload violated the invariant on the vulnerable "
                                 "revision, both executing the target lines; the blind audit accepted the probe"
                                 if audit else "control held and the exploit payload violated the invariant on the "
                                               "vulnerable revision, both executing the target lines (no audit configured)",
                          fix=fix, fix_reason=fix_reason, submission_sha256=submission.sha256,
                          environment_image=image, runs=tuple(runs), audit=audit)
        return done(fix_gate or GateVerdict(passed=True, stage=Gate.VERIFIED, reason="differential probe verified"), verdict)

    def _verify_fix(self, submission: Submission, runs: list[ProbeRun]) -> tuple[Fix, str]:
        assert self.case.fixed_revision is not None
        image, built = self.build(self.case.fixed_revision, "fixed", submission.build_script)
        if image is None:
            return Fix.NOT_VERIFIED, f"fixed revision did not build: {built.reason}"
        control = self.run_probe(image, submission, "fixed", "control")
        exploit = self.run_probe(image, submission, "fixed", "exploit")
        runs += [control, exploit]
        if control.outcome is not Outcome.HOLDS:
            return Fix.NOT_VERIFIED, f"control did not hold on the fixed revision ({control.outcome}: {control.message})"
        if exploit.outcome is Outcome.HOLDS:
            if exploit.covered_target is False:
                return Fix.NOT_VERIFIED, "the invariant held on the fixed revision but the target file never executed"
            return Fix.VERIFIED, "control held and the exploit payload no longer violates the invariant on the fixed revision"
        if exploit.outcome is Outcome.VIOLATED:
            return Fix.NOT_VERIFIED, "the exploit payload still violates the invariant on the fixed revision"
        return Fix.NOT_VERIFIED, f"exploit run on the fixed revision was {exploit.outcome}: {exploit.message}"

    @staticmethod
    def _tails(run: ProbeRun) -> dict[str, str]:
        return {"stderr_tail": (run.message or "")[-TAIL:]}


def terminal_verdict(last: GateVerdict | None, attempts: int) -> Verdict:
    """The verdict when the producer stopped without a verified submission: decided from the last gate it hit."""
    if last is None:
        return Verdict(label=Label.ERROR, rule="K0", reason="no submission was evaluated", fix=Fix.NOT_APPLICABLE)
    if last.stage is Gate.INFRA:
        return Verdict(label=Label.ERROR, rule="K0", reason=last.reason, fix=Fix.NOT_APPLICABLE)
    if last.stage is Gate.BUILD_REPLAY:
        return Verdict(label=Label.UNABLE_TO_RUN, rule="K2", reason=last.reason, fix=Fix.NOT_APPLICABLE)
    reason = f"after {attempts} submission(s) the last one failed {last.stage}: {last.reason}"
    return Verdict(label=Label.INCONCLUSIVE, rule="K3", reason=reason[:2000], fix=Fix.NOT_APPLICABLE)


# --- native report readers ----------------------------------------------------------------------------------------


def _read_junit(data: bytes | None) -> tuple[int, str | None]:
    """(number of test cases, the first failure or error text or None)."""
    if not data:
        return 0, None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return 0, "unreadable JUnit report"
    cases = root.iter("testcase")
    count, first = 0, None
    for case in cases:
        count += 1
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None and first is None:
                first = f"{kind}: {(node.get('message') or '')[:500]}"
    if count == 0:
        for node in root.iter("error"):
            return 0, f"error: {(node.get('message') or node.text or '')[:500]}"
    return count, first


def _read_coverage(data: bytes | None, hypothesis: Hypothesis) -> tuple[bool | None, tuple[int, ...]]:
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
