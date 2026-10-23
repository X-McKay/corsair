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
   executes the target lines. If it holds instead, with the target lines executed, the submission is a clean negative
   observation once the blind auditor accepts it; the gate still fails so the producer tries another payload.
5. ``blind_audit``: a stateless auditor that sees the hypothesis and probe only, never an outcome.

Polarity: ``violated`` means the probe's safety invariant failed, i.e. the reported condition occurred. The fixed
revision is run after the gates and never rejects a submission; it decides fix verification.

The two payloads run as two native test ids through one kernel-owned driver, so "exactly two native probes through
the same seam" holds by construction. The framework adapter (``corsair.adapters.frameworks``) owns the driver, the command
and how the native report, coverage report and driver record are read; the kernel reads nothing else.
"""

from __future__ import annotations

import hashlib
import json
import math
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from corsair.domain.case import Case, Revision, tree_sha256
from corsair.domain.verification import (
    TAIL,
    AuditResult,
    Evaluation,
    Fix,
    Gate,
    GateVerdict,
    Hypothesis,
    Label,
    Outcome,
    ProbeRun,
    RevisionName,
    Role,
    Submission,
    Verdict,
)
from corsair.ports.artifacts import Artifacts
from corsair.ports.framework import Framework
from corsair.ports.sandbox import Exec, Sandboxes, SandboxExists, SandboxSpec, labels, sandbox_name
from corsair.runtime.matrix import Row

BUILD_TIMEOUT_S = 1800.0
PROBE_TIMEOUT_S = 300.0
ENV_REPOSITORY = "corsair-lite-env"
ENV_SCHEMA = "corsair-lite/env/6"
"""Part of every environment key; bump it when what a sealed environment contains or who owns it changes."""
WORKDIR = "/work"
PROBE_DIR = f"{WORKDIR}/.corsair"
RESULT_DIR = "/tmp/corsair"
NOT_DEMONSTRATED = (
    "EXPLOIT_PAYLOAD did not violate the invariant on the vulnerable revision; the reported condition "
    "was not demonstrated"
)

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
        return GateVerdict(
            passed=False,
            stage=Gate.TARGET_BINDING,
            reason=f"the finding reports {reported}; the hypothesis targets {hypothesis.target_file}. "
            "Investigate the reported file; if the reported condition cannot occur there, stop "
            "and say so instead of substituting another target",
        )
    target = Path(case.revision.source) / hypothesis.target_file
    if (
        not target.is_file()
        or target.is_symlink()
        or not target.resolve().is_relative_to(Path(case.revision.source).resolve())
    ):
        return GateVerdict(
            passed=False,
            stage=Gate.TARGET_BINDING,
            reason=f"{hypothesis.target_file} does not exist in the vulnerable revision",
        )
    try:
        text = target.read_text(errors="replace")
    except OSError:
        text = ""
    symbol = hypothesis.target_symbol.split("(")[0].split(".")[-1].strip()
    if symbol and symbol not in text:
        return GateVerdict(
            passed=False,
            stage=Gate.TARGET_BINDING,
            reason=f"the symbol {hypothesis.target_symbol!r} does not appear in {hypothesis.target_file}; "
            "name the function or method that actually holds the flaw in that file",
        )
    if max(hypothesis.target_lines) > text.count("\n") + 1:
        return GateVerdict(
            passed=False,
            stage=Gate.TARGET_BINDING,
            reason=f"{hypothesis.target_file} has {text.count(chr(10)) + 1} lines; target_lines "
            f"{list(hypothesis.target_lines)} are out of range",
        )
    return GateVerdict(
        passed=True, stage=Gate.TARGET_BINDING, reason="hypothesis bound to the reported target"
    )


def _tail(data: bytes) -> str:
    return data[-TAIL:].decode(errors="replace")


def _failure(result: Exec, what: str) -> str:
    if result.timed_out:
        return f"{what} timed out"
    if result.container_failed:
        return f"{what}: container failed"
    return f"{what} exited {result.exit_code}"


def environment_key(
    row: Row,
    tree_sha256: str,
    build_script: str,
    base_image: str | None = None,
    protected_target: str | None = None,
    sandbox_policy: str | None = None,
) -> str:
    build_sha = hashlib.sha256(build_script.encode()).hexdigest()
    return hashlib.sha256(
        json.dumps(
            [
                ENV_SCHEMA,
                row.model_dump(mode="json"),
                base_image,
                tree_sha256,
                build_sha,
                protected_target,
                sandbox_policy,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


class Kernel:
    def __init__(
        self,
        backend: Sandboxes,
        row: Row,
        case: Case,
        *,
        artifacts: Artifacts,
        framework: Framework,
        auditor: Callable[[Submission], Awaitable[AuditResult]] | None = None,
        run_id: str | None = None,
        build_timeout: float = BUILD_TIMEOUT_S,
        probe_timeout: float = PROBE_TIMEOUT_S,
    ):
        self.backend = backend
        self.row = row
        self.case = case
        self.artifacts = artifacts
        self.auditor = auditor
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.build_timeout = build_timeout
        self.probe_timeout = probe_timeout
        if not all(math.isfinite(t) and t > 0 for t in (build_timeout, probe_timeout)):
            raise ValueError("build and probe timeouts must be positive")
        self._attempt = 0
        if framework.name != row.framework:
            raise ValueError("injected framework does not match the selected runtime row")
        self.framework = framework

    # -- gate 2: build replay -----------------------------------------------------------------------------------------

    def build(
        self, revision: Revision, name: RevisionName, build_script: str, protected_target: str | None = None
    ) -> tuple[str | None, GateVerdict]:
        """Replay the build script in a clean container and seal the result as an image; cached by exact key."""
        if tree_sha256(Path(revision.source)) != revision.tree_sha256:
            return None, GateVerdict(
                passed=False,
                stage=Gate.INFRA,
                reason="source changed after revision identity was recorded; reload the case",
            )
        if (Path(revision.source) / ".corsair").exists() or (Path(revision.source) / ".corsair").is_symlink():
            return None, GateVerdict(
                passed=False,
                stage=Gate.BUILD_REPLAY,
                reason="source collides with the kernel-reserved .corsair support path",
            )
        try:
            base_image = self.backend.resolve_image(self.row.image)
            policy = self.backend.cache_identity
            if not isinstance(policy, str) or not policy.strip():
                raise ValueError("sandbox cache policy must have an explicit identity")
        except Exception as error:
            return None, GateVerdict(
                passed=False,
                stage=Gate.INFRA,
                reason=f"sandbox configuration: {type(error).__name__}: {error}"[:4000],
            )
        if base_image is None:
            return None, GateVerdict(
                passed=False,
                stage=Gate.INFRA,
                reason=f"runtime image {self.row.image} is unavailable; build its configured image first",
            )
        key = environment_key(
            self.row, revision.tree_sha256, build_script, base_image, protected_target, policy
        )
        tag = f"{ENV_REPOSITORY}:{key[:32]}"
        if self.backend.find_environment(tag, key) is not None:
            return tag, GateVerdict(
                passed=True, stage=Gate.BUILD_REPLAY, reason=f"environment cache hit {tag}"
            )
        spec = SandboxSpec(
            image=self.row.image,
            workdir=WORKDIR,
            labels=labels(self.run_id, "build", revision=name, env=key[:16]),
            network="build" if build_script.strip() else "none",
        )
        log: list[bytes] = []
        ours = True
        try:
            sandbox = self.backend.create(spec)
            self.backend.copy_tree_in(sandbox, Path(revision.source), WORKDIR)
            if build_script.strip():
                script = "set -euo pipefail\ncd /work\n" + build_script + "\n"
                self.backend.write_file(sandbox, f"{PROBE_DIR}/build.sh", script.encode())
                result = self.backend.exec_once(
                    sandbox, ["bash", f"{PROBE_DIR}/build.sh"], workdir=WORKDIR, timeout=self.build_timeout
                )
                log.append(b"$ bash build.sh\n" + result.stdout + result.stderr)
                if result.exit_code != 0:
                    ref = self.artifacts.put(b"".join(log))
                    return None, GateVerdict(
                        passed=False,
                        stage=Gate.BUILD_REPLAY,
                        reason=f"{_failure(result, 'build_script')} in a clean container "
                        f"({name} revision); log {ref.sha256[:12]}",
                        stdout_tail=_tail(result.stdout),
                        stderr_tail=_tail(result.stderr),
                    )
                self.backend.drop_network(sandbox)
            if not self.backend.source_unchanged(sandbox, Path(revision.source)):
                return None, GateVerdict(
                    passed=False,
                    stage=Gate.BUILD_REPLAY,
                    reason="build_script changed, removed or replaced original source entries",
                )
            log_ref = self.artifacts.put(b"".join(log) or b"(no build script)\n")
            self.backend.seal_environment(sandbox, tag, key, log_ref.sha256, writable=[PROBE_DIR])
            return tag, GateVerdict(passed=True, stage=Gate.BUILD_REPLAY, reason=f"sealed {tag}")
        except Exception as error:  # create, copy or control-plane failure
            ours = not isinstance(error, SandboxExists)
            return None, GateVerdict(
                passed=False,
                stage=Gate.INFRA,
                reason=f"build infrastructure: {type(error).__name__}: {error}"[:4000],
            )
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
            output = (
                b"$ "
                + shlex.join(argv).encode()
                + b"\n--- stdout ---\n"
                + result.stdout
                + b"\n--- stderr ---\n"
                + result.stderr
            )
            if result.timed_out or result.container_failed:
                return self._infra(
                    revision, role, result, output, duration, self.backend.remove(name) if ours else None
                )
            after = fw.after_command()
            collected = None
            if after:
                collected = self.backend.exec_once(name, after, workdir=WORKDIR, env=env, timeout=120)
                output += b"\n$ " + shlex.join(after).encode() + b"\n" + collected.stdout + collected.stderr
                if collected.timed_out or collected.container_failed:
                    return self._infra(
                        revision,
                        role,
                        collected,
                        output,
                        time.monotonic() - started,
                        self.backend.remove(name) if ours else None,
                    )
            files = self.backend.copy_out(name, fw.result_paths())
            confirmed = self.backend.remove(name)
            ours = False
            run = self._classify(
                revision, role, result, output, duration, files, submission.hypothesis, confirmed
            )
            if (
                collected is not None
                and collected.exit_code != 0
                and run.outcome not in (Outcome.NOT_RUN, Outcome.ERRORED)
            ):
                return run.model_copy(
                    update={
                        "outcome": Outcome.INFRA,
                        "covered_target": None,
                        "covered_lines": (),
                        "message": f"coverage collector exited {collected.exit_code}",
                    }
                )
            return run
        except Exception as error:
            ours = not isinstance(error, SandboxExists)
            output += f"\n[infra: {type(error).__name__}: {error}]\n".encode()
            confirmed = self.backend.remove(name) if ours else None
            ours = False
            return ProbeRun(
                revision=revision,
                role=role,
                outcome=Outcome.INFRA,
                exception_type=type(error).__name__,
                message=str(error)[:2000],
                exit_code=None,
                junit_tests=0,
                duration_s=duration,
                output=self.artifacts.put(output),
                cleanup_confirmed=confirmed,
            )
        finally:
            if ours:
                self.backend.remove(name)

    def _infra(
        self,
        revision: RevisionName,
        role: Role,
        result: Exec,
        output: bytes,
        duration: float | None,
        confirmed: bool | None,
    ) -> ProbeRun:
        return ProbeRun(
            revision=revision,
            role=role,
            outcome=Outcome.INFRA,
            exit_code=result.exit_code,
            message=(
                "timed out"
                if result.timed_out
                else "container failed"
                if result.container_failed
                else f"coverage collector exited {result.exit_code}"
            ),
            junit_tests=0,
            duration_s=duration,
            output=self.artifacts.put(output),
            cleanup_confirmed=confirmed,
        )

    def _classify(
        self,
        revision: RevisionName,
        role: Role,
        result: Exec,
        output: bytes,
        duration: float,
        files: dict[str, bytes | None],
        hypothesis: Hypothesis,
        confirmed: bool | None,
    ) -> ProbeRun:
        read = self.framework.read(files, hypothesis)
        if (read.outcome is Outcome.HOLDS and result.exit_code != 0) or (
            read.outcome is Outcome.VIOLATED and result.exit_code != 1
        ):
            from dataclasses import replace

            read = replace(
                read, outcome=Outcome.ERRORED, message="process exit status disagrees with the probe evidence"
            )
        junit_path = next((p for p in self.framework.result_paths() if p.endswith(".xml")), None)
        junit_bytes = files.get(junit_path) if junit_path else None
        return ProbeRun(
            revision=revision,
            role=role,
            outcome=read.outcome,
            exception_type=read.exception_type,
            message=read.message,
            exit_code=result.exit_code,
            junit_tests=read.junit_tests,
            covered_target=read.covered_target,
            covered_lines=read.covered_lines,
            duration_s=duration,
            output=self.artifacts.put(output),
            junit=self.artifacts.put(junit_bytes) if junit_bytes else None,
            reports={path: self.artifacts.put(data) for path, data in files.items() if data is not None},
            cleanup_confirmed=confirmed,
        )

    # -- the whole evaluation -------------------------------------------------------------------------------------------

    async def evaluate(self, submission: Submission) -> Evaluation:
        started = time.monotonic()
        runs: list[ProbeRun] = []

        def done(
            gate: GateVerdict,
            verdict: Verdict | None = None,
            *,
            audit: AuditResult | None = None,
            clean_negative: bool = False,
        ) -> Evaluation:
            return Evaluation(
                submission=submission,
                submission_sha256=submission.sha256,
                gate=gate,
                verdict=verdict,
                runs=tuple(runs),
                duration_s=time.monotonic() - started,
                audit=audit,
                clean_negative=clean_negative,
            )

        binding = target_binding(self.case, submission.hypothesis)
        if not binding.passed:
            return done(binding)
        guard = self.framework.guard(submission.probe)
        if not guard.passed:
            return done(guard)
        image, built = self.build(
            self.case.revision, "vulnerable", submission.build_script, submission.hypothesis.target_file
        )
        if image is None:
            return done(built)

        control = self.run_probe(image, submission, "vulnerable", "control")
        runs.append(control)
        if control.outcome is Outcome.INFRA:
            return done(GateVerdict(passed=False, stage=Gate.INFRA, reason=f"control run: {control.message}"))
        if control.outcome is not Outcome.HOLDS:
            return done(
                GateVerdict(
                    passed=False,
                    stage=Gate.CONTROL_RUN,
                    reason=f"CONTROL_PAYLOAD must hold on the vulnerable revision but was "
                    f"{control.outcome}: {control.exception_type or ''} {control.message or ''}".strip(),
                    **self._tails(control),
                )
            )
        if not set(submission.hypothesis.target_lines).issubset(control.covered_lines):
            return done(
                GateVerdict(
                    passed=False,
                    stage=Gate.CONTROL_COVERAGE,
                    reason=f"CONTROL_PAYLOAD held but did not execute {submission.hypothesis.target_file} "
                    f"lines {list(submission.hypothesis.target_lines)}"
                    + ("" if control.covered_target else " (the file never ran)"),
                )
            )

        exploit = self.run_probe(image, submission, "vulnerable", "exploit")
        runs.append(exploit)
        if exploit.outcome is Outcome.INFRA:
            return done(GateVerdict(passed=False, stage=Gate.INFRA, reason=f"exploit run: {exploit.message}"))
        if exploit.outcome is Outcome.HOLDS:
            if not set(submission.hypothesis.target_lines).issubset(exploit.covered_lines):
                return done(
                    GateVerdict(
                        passed=False,
                        stage=Gate.EXPLOIT_RUN,
                        reason=f"{NOT_DEMONSTRATED}; the target lines did not execute, so this is not "
                        "a clean negative",
                    )
                )
            # Control held and both runs executed the target lines: a clean negative observation if the auditor accepts.
            held_audit = await self._audit(submission)
            if held_audit is not None and not held_audit.valid:
                return done(
                    GateVerdict(
                        passed=False,
                        stage=Gate.BLIND_AUDIT,
                        reason=f"outcome-blind audit rejected the probe: {held_audit.reason}",
                    ),
                    audit=held_audit,
                )
            return done(
                GateVerdict(
                    passed=False,
                    stage=Gate.EXPLOIT_RUN,
                    reason=f"{NOT_DEMONSTRATED}; recorded as a clean negative observation",
                ),
                audit=held_audit,
                clean_negative=True,
            )
        if exploit.outcome is not Outcome.VIOLATED:
            return done(
                GateVerdict(
                    passed=False,
                    stage=Gate.EXPLOIT_RUN,
                    reason=f"EXPLOIT_PAYLOAD must fail the probe's own invariant assertion, but the run "
                    f"was {exploit.outcome}: {exploit.exception_type or ''} {exploit.message or ''}".strip(),
                    **self._tails(exploit),
                )
            )
        if not set(submission.hypothesis.target_lines).issubset(exploit.covered_lines):
            return done(
                GateVerdict(
                    passed=False,
                    stage=Gate.EXPLOIT_COVERAGE,
                    reason=f"EXPLOIT_PAYLOAD failed before executing {submission.hypothesis.target_file} "
                    f"lines {list(submission.hypothesis.target_lines)}",
                )
            )

        audit: AuditResult | None = None
        if self.auditor is not None:
            audit = await self._audit(submission)
            if not audit.valid:
                return done(
                    GateVerdict(
                        passed=False,
                        stage=Gate.BLIND_AUDIT,
                        reason=f"outcome-blind audit rejected the probe: {audit.reason}",
                    ),
                    audit=audit,
                )

        fix, fix_reason = Fix.NOT_APPLICABLE, "the case has no fixed revision"
        fix_gate: GateVerdict | None = None
        if self.case.fixed_revision is not None:
            fix, fix_reason = self._verify_fix(submission, runs)
            fixed_exploit = runs[-1] if len(runs) == 4 and runs[-1].revision == "fixed" else None
            if (
                fixed_exploit is not None
                and fixed_exploit.role == "exploit"
                and fixed_exploit.outcome is Outcome.ERRORED
                and fixed_exploit.exception_type != "AssertionError"
            ):
                fix_gate = GateVerdict(
                    passed=False,
                    stage=Gate.FIX_RUN,
                    reason=f"the vulnerable revision is verified, but on the fixed revision "
                    f"EXPLOIT_PAYLOAD raised {fixed_exploit.exception_type}: "
                    f"{(fixed_exploit.message or '')[:500]}. If that exception is how the "
                    "fix rejects the payload, catch it inside run_target and let the "
                    "invariant decide; the fix is not verified until the exploit run holds there",
                )
        verdict = Verdict(
            label=Label.LIKELY_EXPLOITABLE,
            rule="K1",
            reason="control held and the exploit payload violated the invariant on the vulnerable "
            "revision, both executing the target lines; the blind audit accepted the probe"
            if audit
            else "control held and the exploit payload violated the invariant on the "
            "vulnerable revision, both executing the target lines (no audit configured)",
            fix=fix,
            fix_reason=fix_reason,
            submission_sha256=submission.sha256,
            environment_image=image,
            runs=tuple(runs),
            audit=audit,
        )
        return done(
            fix_gate or GateVerdict(passed=True, stage=Gate.VERIFIED, reason="differential probe verified"),
            verdict,
            audit=audit,
        )

    async def _audit(self, submission: Submission) -> AuditResult | None:
        if self.auditor is None:
            return None
        try:
            return await self.auditor(submission)
        except Exception as error:
            return AuditResult(
                valid=False, reason=f"audit unavailable: {type(error).__name__}: {error}"[:2000]
            )

    def _verify_fix(self, submission: Submission, runs: list[ProbeRun]) -> tuple[Fix, str]:
        assert self.case.fixed_revision is not None
        image, built = self.build(
            self.case.fixed_revision, "fixed", submission.build_script, submission.hypothesis.target_file
        )
        if image is None:
            return Fix.NOT_VERIFIED, f"fixed revision did not build: {built.reason}"
        control = self.run_probe(image, submission, "fixed", "control")
        exploit = self.run_probe(image, submission, "fixed", "exploit")
        runs += [control, exploit]
        if control.outcome is not Outcome.HOLDS:
            return (
                Fix.NOT_VERIFIED,
                f"control did not hold on the fixed revision ({control.outcome}: {control.message})",
            )
        if control.covered_target is not True:
            return Fix.NOT_VERIFIED, "control held on the fixed revision but target coverage is missing"
        if exploit.outcome is Outcome.HOLDS:
            if exploit.covered_target is not True:
                return (
                    Fix.NOT_VERIFIED,
                    "the invariant held on the fixed revision but the target file never executed",
                )
            return (
                Fix.VERIFIED,
                "control held and the exploit payload no longer violates the invariant on the fixed revision",
            )
        if exploit.outcome is Outcome.VIOLATED:
            return Fix.NOT_VERIFIED, "the exploit payload still violates the invariant on the fixed revision"
        return Fix.NOT_VERIFIED, f"exploit run on the fixed revision was {exploit.outcome}: {exploit.message}"

    @staticmethod
    def _tails(run: ProbeRun) -> dict[str, str]:
        return {"stderr_tail": (run.message or "")[-TAIL:]}
