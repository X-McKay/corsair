"""The verdict kernel: deterministic gates around one differential probe, run in twin sandboxes.

A submission is a hypothesis, a build script and one probe module that defines ``CONTROL_PAYLOAD``,
``EXPLOIT_PAYLOAD`` and ``run_target(payload)``. The kernel never trusts the producer's workspace: it replays the
build script in a clean container, seals the result as an image, and runs each payload alone in a fresh offline
container from that image, on the vulnerable revision and, when the case has one, the fixed revision.

The kernel binds the hypothesis to the reported target, guards the probe, and replays its build in a clean
container. A clean control observation allows both payloads to run. Decisive dispositions require control PASS,
complete target coverage for both runs, and an accepted outcome-blind audit. Exploit PASS yields K1
LIKELY_EXPLOITABLE; a clean exploit FAIL yields K4 LIKELY_NOT_EXPLOITABLE, scoped to the finding, payload,
exact revision and runtime. Invalid evidence
is K3 INCONCLUSIVE. Application exceptions never establish a negative disposition.

Each evaluated revision retains its own disposition. The top-level label mirrors the vulnerable/source revision;
a fixed revision verifies the fix only when it independently earns the negative disposition. A removed fixed
target remains INCONCLUSIVE/TARGET_REMOVED and does not verify the fix.

Drivers require a Boolean security invariant and report whether it matches the trusted role expectation.
Public run records retain the Boolean alongside PASS, FAIL, ERROR, NOT_RUN or INFRA.

The two payloads run as two native test ids through one kernel-owned driver, so "exactly two native probes through
the same seam" holds by construction. The framework adapter (``corsair.frameworks``) owns the driver, the command
and how the native report, coverage report and driver record are read; the kernel reads nothing else.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .artifacts import ArtifactRef, ArtifactStore
from .case import Case, Frozen, Revision, SafePath
from .matrix import Row
from .sandbox.port import Exec, Sandboxes, SandboxExists, SandboxSpec, labels, sandbox_name

BUILD_TIMEOUT_S = 1800.0
PROBE_TIMEOUT_S = 300.0
TAIL = 4000
ENV_REPOSITORY = "corsair-lite-env"
ENV_SCHEMA = "corsair-lite/env/4"
"""Part of every environment key; bump it when what a sealed environment contains or who owns it changes."""
WORKDIR = "/work"
PROBE_DIR = f"{WORKDIR}/.corsair"
RESULT_DIR = "/tmp/corsair"

Role = Literal["control", "exploit"]
RevisionName = Literal["vulnerable", "fixed"]


class Hypothesis(Frozen):
    target_file: SafePath = Field(description="Path of the vulnerable source file, relative to the repository root")
    target_symbol: str = Field(min_length=1, max_length=256, description="Function or method holding the flaw")
    target_lines: tuple[int, ...] = Field(min_length=1, max_length=64, description="Lines that both payloads must execute")
    root_cause: str = Field(min_length=1, max_length=2_000, description="The mechanism of the bug, one or two sentences")
    expected_violation: str = Field(min_length=1, max_length=1_000,
                                    description="What the invariant observes when EXPLOIT_PAYLOAD runs")

    @field_validator("target_lines")
    @classmethod
    def _positive(cls, lines: tuple[int, ...]) -> tuple[int, ...]:
        if any(line < 1 for line in lines):
            raise ValueError("target lines are 1-based")
        return tuple(sorted(set(lines)))


class Submission(Frozen):
    contract_version: Literal["corsair-lite/differential-probe/2"] = Field(
        description="Required Boolean differential-probe contract version; stale submissions must be rewritten")
    hypothesis: Hypothesis
    build_script: str = Field(default="", max_length=16_000,
                              description="bash run once in a clean container with network, from the repository "
                                          "root; empty when the project needs nothing installed")
    probe: str = Field(min_length=1, max_length=32_000,
                       description="One module in the selected runtime defining/exporting CONTROL_PAYLOAD, "
                                   "EXPLOIT_PAYLOAD and run_target(payload), expressing one security invariant "
                                   "that returns Boolean true when preserved and false when the reported condition occurs")

    @model_validator(mode="before")
    @classmethod
    def _contract_version(cls, value):
        if isinstance(value, dict) and value.get("contract_version") != "corsair-lite/differential-probe/2":
            raise ValueError("contract_version must be 'corsair-lite/differential-probe/2'; rewrite the probe "
                             "to return one payload-only Boolean invariant (true when preserved, false when the "
                             "reported condition occurs). Stale assertion-based submissions are not translated.")
        return value

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


class RoleResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"
    INFRA = "INFRA"


def role_result(role: Role, invariant_held: bool) -> RoleResult:
    """Compare a clean Boolean observation with the trusted role expectation."""
    if type(invariant_held) is not bool:
        raise TypeError("the security invariant must be a Boolean")
    return RoleResult.PASS if invariant_held == (role == "control") else RoleResult.FAIL


class ProbeRun(Frozen):
    revision: RevisionName
    role: Role
    result: RoleResult
    invariant_held: bool | None
    exception_type: str | None = None
    message: str | None = Field(default=None, max_length=2_000)
    exit_code: int | None
    junit_tests: int = Field(ge=0, description="Test cases the native JUnit report lists")
    covered_target: bool | None = Field(default=None, description="The target file executed at all; None unknown")
    covered_lines: tuple[int, ...] = Field(default=(), description="Hypothesis lines the run executed")
    duration_s: float | None = None
    output: ArtifactRef | None = None
    junit: ArtifactRef | None = None
    coverage: ArtifactRef | None = None
    cleanup_confirmed: bool | None = None


class AuditResult(Frozen):
    valid: bool
    reason: str = Field(max_length=2_000)


class Label(StrEnum):
    LIKELY_EXPLOITABLE = "LIKELY_EXPLOITABLE"
    LIKELY_NOT_EXPLOITABLE = "LIKELY_NOT_EXPLOITABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNABLE_TO_RUN = "UNABLE_TO_RUN"
    ERROR = "ERROR"


class Fix(StrEnum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    NOT_APPLICABLE = "not_applicable"


class RevisionDisposition(Frozen):
    revision: RevisionName
    label: Label
    rule: str
    reason_code: str
    reason: str


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
    revisions: tuple[RevisionDisposition, ...] = ()


class Evaluation(Frozen):
    """One submission's evidence and disposition, with the first failed gate when evidence is invalid.

    A verdict may be inconclusive when a gate fails. A ``fix_run`` failure preserves the source disposition while
    reporting an exception that prevents fix verification.
    """

    submission: Submission
    submission_sha256: str
    gate: GateVerdict
    verdict: Verdict | None = None
    runs: tuple[ProbeRun, ...] = ()
    duration_s: float


# --- gate 0: the hypothesis is about the reported target -------------------------------------------------------------


def _contained_file(source: str, path: str) -> Path | None:
    root = Path(source).resolve()
    candidate = root / path
    try:
        return candidate if candidate.resolve().is_relative_to(root) and candidate.is_file() else None
    except (OSError, RuntimeError):
        return None


def reported_target_present(case: Case) -> str | None:
    """None when the finding names no file or the file exists in the vulnerable tree; otherwise the reason the case
    cannot be investigated at all. Decided by trusted code before any model call."""
    path = case.finding.file_path
    if path is None:
        return None
    if _contained_file(case.revision.source, path) is None:
        return f"the reported file {path} does not exist inside the vulnerable revision"
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
    target = _contained_file(case.revision.source, hypothesis.target_file)
    if target is None:
        return GateVerdict(passed=False, stage=Gate.TARGET_BINDING,
                           reason=f"{hypothesis.target_file} does not exist in the vulnerable revision")
    try:
        text = target.read_text(errors="replace")
    except OSError:
        text = ""
    symbol = hypothesis.target_symbol.split("(")[0].split(".")[-1].strip()
    if symbol and symbol not in text:
        return GateVerdict(passed=False, stage=Gate.TARGET_BINDING,
                           reason=f"the symbol {hypothesis.target_symbol!r} does not appear in {hypothesis.target_file}; "
                                  "name the function or method that actually holds the flaw in that file")
    if max(hypothesis.target_lines) > text.count("\n") + 1:
        return GateVerdict(passed=False, stage=Gate.TARGET_BINDING,
                           reason=f"{hypothesis.target_file} has {text.count(chr(10)) + 1} lines; target_lines "
                                  f"{list(hypothesis.target_lines)} are out of range")
    return GateVerdict(passed=True, stage=Gate.TARGET_BINDING, reason="hypothesis bound to the reported target")


# --- gate 1: the structural guard is the framework adapter's; this name stays for the Python reference ---------


def ast_guard(probe: str) -> GateVerdict:
    from .frameworks.pytest_ import ast_guard as python_guard

    return python_guard(probe)


def _tail(data: bytes) -> str:
    return data[-TAIL:].decode(errors="replace")


def _failure(result: Exec, what: str) -> str:
    if result.timed_out:
        return f"{what} timed out"
    if result.output_limited:
        return f"{what} exceeded the output limit"
    if result.container_failed:
        return f"{what}: container failed"
    return f"{what} exited {result.exit_code}"


def environment_key(row: Row, tree_sha256: str, build_script: str, *, runtime_image_id: str | None = None) -> str:
    build_sha = hashlib.sha256(build_script.encode()).hexdigest()
    return hashlib.sha256(json.dumps([ENV_SCHEMA, row.id, row.framework, row.image, runtime_image_id,
                                      tree_sha256, build_sha]).encode()).hexdigest()


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
        from .frameworks import framework

        self.framework = framework(row.framework)
        self.runtime_image_id = backend.resolve_image(row.image)

    # -- gate 2: build replay -----------------------------------------------------------------------------------------

    def build(self, revision: Revision, name: RevisionName, build_script: str) -> tuple[str | None, GateVerdict]:
        """Replay the build script in a clean container and seal the result as an image; cached by exact key."""
        key = environment_key(self.row, revision.tree_sha256, build_script, runtime_image_id=self.runtime_image_id)
        tag = f"{ENV_REPOSITORY}:{key[:32]}"
        if self.backend.find_environment(tag, key) is not None:
            return tag, GateVerdict(passed=True, stage=Gate.BUILD_REPLAY, reason=f"environment cache hit {tag}")
        spec = SandboxSpec(image=self.runtime_image_id or self.row.image, workdir=WORKDIR,
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
                if result.timed_out or result.output_limited or result.container_failed:
                    ref = self.artifacts.put(b"".join(log))
                    return None, GateVerdict(passed=False, stage=Gate.INFRA,
                                             reason=f"{_failure(result, 'build_script')} in a clean container "
                                                    f"({name} revision); log {ref.sha256[:12]}",
                                             stdout_tail=_tail(result.stdout), stderr_tail=_tail(result.stderr))
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
        fw = self.framework
        target = submission.hypothesis.target_file
        self._attempt += 1
        sandbox_labels = labels(self.run_id, "probe", role, revision=revision, n=str(self._attempt))
        name = sandbox_name(sandbox_labels)
        env = dict(fw.environment(role))
        argv = fw.command(role, target)
        output = b""
        started = time.monotonic()
        duration: float | None = None
        ours = True
        try:
            self.backend.open_environment(image, WORKDIR, sandbox_labels)
            self.backend.write_file(name, f"{PROBE_DIR}/{fw.probe_file}", submission.probe.encode())
            for relative, data in fw.driver_files().items():
                self.backend.write_file(name, f"{PROBE_DIR}/{relative}", data)
            made = self.backend.exec_once(name, ["mkdir", "-p", RESULT_DIR], workdir="/", timeout=60)
            if made.exit_code != 0:
                raise RuntimeError(f"cannot create {RESULT_DIR}: {made.stderr.decode(errors='replace')}")
            result = self.backend.exec_once(name, argv, workdir=WORKDIR, env=env, timeout=self.probe_timeout)
            duration = time.monotonic() - started
            output = b"$ " + shlex.join(argv).encode() + b"\n--- stdout ---\n" + result.stdout + b"\n--- stderr ---\n" + result.stderr
            if result.timed_out or result.output_limited or result.container_failed:
                return self._infra(revision, role, result, output, duration, self.backend.remove(name) if ours else None)
            after = fw.after_command()
            if after:
                self.backend.exec_once(name, after, workdir=WORKDIR, env=env, timeout=120)
            files = self.backend.copy_out(name, fw.result_paths())
            confirmed = self.backend.remove(name)
            ours = False
            return self._classify(revision, role, result, output, duration, files, submission.hypothesis, confirmed)
        except Exception as error:
            ours = not isinstance(error, SandboxExists)
            output += f"\n[infra: {type(error).__name__}: {error}]\n".encode()
            confirmed = self.backend.remove(name) if ours else None
            ours = False
            return ProbeRun(revision=revision, role=role,
                            result=RoleResult.INFRA, invariant_held=None, exception_type=type(error).__name__,
                            message=str(error)[:2000], exit_code=None, junit_tests=0, duration_s=duration,
                            output=self.artifacts.put(output), cleanup_confirmed=confirmed)
        finally:
            if ours:
                self.backend.remove(name)

    def _infra(self, revision: RevisionName, role: Role, result: Exec, output: bytes, duration: float | None,
               confirmed: bool | None) -> ProbeRun:
        return ProbeRun(revision=revision, role=role,
                        result=RoleResult.INFRA, invariant_held=None, exit_code=result.exit_code,
                        message=("timed out" if result.timed_out else "output limit exceeded"
                                 if result.output_limited else "container failed"), junit_tests=0,
                        duration_s=duration, output=self.artifacts.put(output), cleanup_confirmed=confirmed)

    def _classify(self, revision: RevisionName, role: Role, result: Exec, output: bytes, duration: float,
                  files: dict[str, bytes | None], hypothesis: Hypothesis, confirmed: bool | None) -> ProbeRun:
        revision_source = self.case.revision if revision == "vulnerable" else self.case.fixed_revision
        assert revision_source is not None
        read = self.framework.read(files, hypothesis, role, Path(revision_source.source))
        expected_exit = 0 if read.result is RoleResult.PASS else 1
        observed, invariant_held, message = read.result, read.invariant_held, read.message
        if observed in (RoleResult.PASS, RoleResult.FAIL, RoleResult.ERROR) and result.exit_code != expected_exit:
            observed, invariant_held = RoleResult.ERROR, None
            message = ((message + "; ") if message else "") + "process exit code disagrees with the native evidence"
        junit_path = next((p for p in self.framework.result_paths() if p.endswith(".xml")), None)
        junit_bytes = files.get(junit_path) if junit_path else None
        coverage_path = next((path for path in self.framework.result_paths()
                              if path.endswith(("coverage.json", "jacoco.xml"))), None)
        coverage_bytes = files.get(coverage_path) if coverage_path else None
        return ProbeRun(revision=revision, role=role, result=observed, invariant_held=invariant_held,
                        exception_type=read.exception_type, message=message[:2000] if message else None,
                        exit_code=result.exit_code, junit_tests=read.junit_tests,
                        covered_target=read.covered_target, covered_lines=read.covered_lines, duration_s=duration,
                        output=self.artifacts.put(output),
                        junit=self.artifacts.put(junit_bytes) if junit_bytes else None,
                        coverage=self.artifacts.put(coverage_bytes) if coverage_bytes else None, cleanup_confirmed=confirmed)

    # -- the whole evaluation -------------------------------------------------------------------------------------------

    async def evaluate(self, submission: Submission) -> Evaluation:
        started = time.monotonic()
        runs: list[ProbeRun] = []
        dispositions: list[RevisionDisposition] = []
        image: str | None = None
        audit: AuditResult | None = None

        def done(gate: GateVerdict, verdict: Verdict | None = None) -> Evaluation:
            if verdict is None and runs:
                disposition = self._inconclusive("vulnerable", gate.stage.name, gate.reason)
                verdict = Verdict(label=disposition.label, rule=disposition.rule, reason=disposition.reason,
                                  fix=Fix.NOT_VERIFIED if self.case.fixed_revision else Fix.NOT_APPLICABLE,
                                  submission_sha256=submission.sha256, environment_image=image,
                                  runs=tuple(runs), audit=audit, revisions=(disposition,))
            return Evaluation(submission=submission, submission_sha256=submission.sha256, gate=gate, verdict=verdict,
                              runs=tuple(runs), duration_s=time.monotonic() - started)

        binding = target_binding(self.case, submission.hypothesis)
        if not binding.passed:
            return done(binding)
        guard = self.framework.guard(submission.probe)
        if not guard.passed:
            return done(guard)
        image, built = self.build(self.case.revision, "vulnerable", submission.build_script)
        if image is None:
            return done(built)

        control, exploit = self._run_revision(image, submission, "vulnerable", runs)
        failed = self._evidence_gate(submission.hypothesis, control, exploit)
        if failed is not None:
            return done(failed)
        if self.auditor is None:
            return done(GateVerdict(passed=False, stage=Gate.BLIND_AUDIT,
                                    reason="an accepted outcome-blind audit is required; no auditor configured"))
        audit = await self.auditor(submission)
        if not audit.valid:
            return done(GateVerdict(passed=False, stage=Gate.BLIND_AUDIT,
                                    reason=f"outcome-blind audit rejected the probe: {audit.reason}"))
        assert exploit is not None
        source = self._decide("vulnerable", exploit)
        dispositions.append(source)

        fix, fix_reason = Fix.NOT_APPLICABLE, "the case has no fixed revision"
        fix_gate: GateVerdict | None = None
        if self.case.fixed_revision is not None:
            fixed, fix, fix_reason = self._verify_fix(submission, runs)
            dispositions.append(fixed)
            fixed_exploit = runs[-1] if runs[-1].revision == "fixed" and runs[-1].role == "exploit" else None
            if fixed_exploit is not None and fixed_exploit.result is RoleResult.ERROR:
                fix_gate = GateVerdict(passed=False, stage=Gate.FIX_RUN,
                                       reason=f"the source disposition stands, but on the fixed revision "
                                              f"EXPLOIT_PAYLOAD raised {fixed_exploit.exception_type}: "
                                              f"{(fixed_exploit.message or '')[:500]}. If that exception is how the "
                                              "fix rejects the payload, catch it inside run_target and let the "
                                              "invariant decide; the fix is not verified until the exploit invariant is true there")
        verdict = Verdict(label=source.label, rule=source.rule, reason=source.reason,
                          fix=fix, fix_reason=fix_reason, submission_sha256=submission.sha256,
                          environment_image=image, runs=tuple(runs), audit=audit, revisions=tuple(dispositions))
        return done(fix_gate or GateVerdict(passed=True, stage=Gate.VERIFIED,
                                           reason="audited probe disposition verified"), verdict)

    def _run_revision(self, image: str, submission: Submission, revision: RevisionName,
                      runs: list[ProbeRun]) -> tuple[ProbeRun, ProbeRun | None]:
        control = self.run_probe(image, submission, revision, "control")
        runs.append(control)
        exploit = None
        if control.result in (RoleResult.PASS, RoleResult.FAIL):
            exploit = self.run_probe(image, submission, revision, "exploit")
            runs.append(exploit)
        return control, exploit

    @staticmethod
    def _evidence_gate(hypothesis: Hypothesis, control: ProbeRun, exploit: ProbeRun | None) -> GateVerdict | None:
        for run, run_gate, coverage_gate in [(control, Gate.CONTROL_RUN, Gate.CONTROL_COVERAGE),
                                             (exploit, Gate.EXPLOIT_RUN, Gate.EXPLOIT_COVERAGE)]:
            if run is None:
                continue
            if run.result is RoleResult.INFRA:
                return GateVerdict(passed=False, stage=Gate.INFRA, reason=f"{run.role} run: {run.message}")
            if run.result not in (RoleResult.PASS, RoleResult.FAIL) or (
                    run.role == "control" and run.result is RoleResult.FAIL):
                return GateVerdict(passed=False, stage=run_gate,
                                   reason=f"{run.role} run was {run.result}: {run.exception_type or ''} {run.message or ''}".strip(),
                                   **Kernel._tails(run))
            if run.covered_target is not True or not set(hypothesis.target_lines).issubset(run.covered_lines):
                return GateVerdict(passed=False, stage=coverage_gate,
                                   reason=f"{run.role} did not execute {hypothesis.target_file} "
                                          f"lines {list(hypothesis.target_lines)}")
        return None

    @staticmethod
    def _inconclusive(revision: RevisionName, code: str, reason: str) -> RevisionDisposition:
        return RevisionDisposition(revision=revision, label=Label.INCONCLUSIVE, rule="K3",
                                   reason_code=code, reason=reason[:2000])

    @staticmethod
    def _decide(revision: RevisionName, exploit: ProbeRun) -> RevisionDisposition:
        """Called only after both clean runs, exact coverage and the blind audit have passed."""
        positive = exploit.result is RoleResult.PASS
        return RevisionDisposition(revision=revision,
                                   label=Label.LIKELY_EXPLOITABLE if positive else Label.LIKELY_NOT_EXPLOITABLE,
                                   rule="K1" if positive else "K4",
                                   reason_code="EXPLOIT_EXPECTATION_MET" if positive else "INVARIANT_PRESERVED",
                                   reason=f"control passed and exploit {'passed' if positive else 'failed'} on the "
                                          f"{revision} revision, with clean invariant evidence, exact target coverage "
                                          "and an accepted outcome-blind audit")

    def _verify_fix(self, submission: Submission, runs: list[ProbeRun]) -> tuple[RevisionDisposition, Fix, str]:
        assert self.case.fixed_revision is not None
        if _contained_file(self.case.fixed_revision.source, submission.hypothesis.target_file) is None:
            reason = f"target {submission.hypothesis.target_file} was removed from the fixed revision"
            return self._inconclusive("fixed", "TARGET_REMOVED", reason), Fix.NOT_VERIFIED, reason
        image, built = self.build(self.case.fixed_revision, "fixed", submission.build_script)
        if image is None:
            reason = f"fixed revision did not build: {built.reason}"
            return self._inconclusive("fixed", "BUILD_FAILED", reason), Fix.NOT_VERIFIED, reason
        control, exploit = self._run_revision(image, submission, "fixed", runs)
        failed = self._evidence_gate(submission.hypothesis, control, exploit)
        if failed is not None:
            return self._inconclusive("fixed", failed.stage.name, failed.reason), Fix.NOT_VERIFIED, failed.reason
        assert exploit is not None
        disposition = self._decide("fixed", exploit)
        if disposition.label is Label.LIKELY_NOT_EXPLOITABLE:
            return disposition, Fix.VERIFIED, "control held and the exploit payload no longer violates the invariant on the fixed revision"
        return disposition, Fix.NOT_VERIFIED, "the exploit payload still violates the invariant on the fixed revision"

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
