"""Trusted probe execution (stage 7, ``stages.Execute``) and the D3 diagnostics run.

Each probe runs alone, exactly once, in a fresh offline container from the replayed Environment image, with only its
own file written. Trusted code observes three things itself (D8): the exit code, sorted by the matrix row's exit-code
map; the ``start`` and ``end`` marker files the test writes under ``$CORSAIR_MARKER_DIR``; and whether the per-run
``$CORSAIR_TOKEN`` (exploit role only) appears in the output. ``outcome.classify`` turns those facts into an Outcome.
Nothing here knows a language: the run argv comes from the row's template, filled generically.
"""
from __future__ import annotations

import posixpath
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .artifacts import ArtifactStore
from .contracts import Environment, ExitClass, FrozenPatch, Outcome, ProbeDraft, ProbeFacts, ProbeRun, Runtime
from .workspace.docker import ContainerExists, DockerConfig, create, exec_once, labels, remove, write_file

PROBE_TIMEOUT_S = 300.0
DIAGNOSTICS_LIMIT = 8 * 1024
MARKER_ENV = "CORSAIR_MARKER_DIR"
TOKEN_ENV = "CORSAIR_TOKEN"
_PLACEHOLDER = re.compile(r"\{(file|name|class|module)\}")


def fill_template(template: tuple[str, ...] | list[str], draft: ProbeDraft) -> list[str]:
    """Fill {file} (path under the root), {name} (test name), {class} (file stem) and {module} (dotted path without
    the extension). Other braces are left alone, so a template may carry literal ones."""
    path = PurePosixPath(draft.test_file)
    values = {"file": draft.test_file, "name": draft.test_name, "class": path.stem,
              "module": ".".join(path.with_suffix("").parts)}
    return [_PLACEHOLDER.sub(lambda match: values[match.group(1)], arg) for arg in template]


def exit_class(runtime: Runtime, exit_code: int | None) -> ExitClass | None:
    if exit_code is None:
        return None
    return runtime.exit_codes.get(exit_code, ExitClass.UNKNOWN)


def new_token(role: str) -> str | None:
    """A fresh token per run, for the security assertion only; the control probe gets none."""
    return secrets.token_hex(16) if role == "exploit" else None


def classify(facts: ProbeFacts) -> Outcome:
    from .outcome import classify as rule_table  # Owned by the Decide stage; imported where used.

    return rule_table(facts)


@dataclass(frozen=True)
class Observation:
    facts: ProbeFacts
    output: bytes
    duration_s: float | None
    token: str | None
    cleanup_confirmed: bool | None


def _infra() -> ProbeFacts:
    return ProbeFacts(exit_code=None, exit_class=None, start_marker=False, end_marker=False, token_in_output=False)


def observe(environment: Environment, runtime: Runtime, draft: ProbeDraft, *, revision: str, run_id: str | None,
            timeout: float, patch_sha256: str | None = None) -> Observation:
    """Run one draft once and record what was observed. Never retried; any failure is a container failure fact."""
    token = new_token(draft.role)
    marker_dir = f"/tmp/corsair-markers-{secrets.token_hex(8)}"
    extra = {"revision": revision} | ({"patch": patch_sha256[:16]} if patch_sha256 else {})
    config = DockerConfig(image=environment.image, workdir=environment.workdir, network="none",
                          labels=labels(run_id or uuid.uuid4().hex[:12], "execute", draft.role, **extra))
    env = {MARKER_ENV: marker_dir} | ({TOKEN_ENV: token} if token else {})
    facts, output, duration, ours = _infra(), b"", None, True
    try:
        name = create(config, adopt=False)
        write_file(name, posixpath.join(environment.workdir, draft.test_file), draft.source.encode())
        made = exec_once(name, ["mkdir", "-p", marker_dir], workdir="/", timeout=60)
        if made.exit_code != 0:
            raise RuntimeError(f"cannot create the marker directory: {made.stderr.decode(errors='replace')}")
        started = time.monotonic()
        result = exec_once(name, fill_template(runtime.run_template, draft), workdir=environment.workdir, env=env,
                           timeout=timeout)
        duration = time.monotonic() - started
        output = b"--- stdout ---\n" + result.stdout + b"\n--- stderr ---\n" + result.stderr
        markers = exec_once(name, ["sh", "-c", 'for f in start end; do test -e "$1/$f" && echo "$f"; done; true',
                                   "sh", marker_dir], workdir="/", timeout=60)
        if markers.exit_code != 0:
            output += b"\n[markers unreadable: container failed]\n"
        else:
            found = markers.stdout.decode().split()
            facts = ProbeFacts(exit_code=result.exit_code, exit_class=exit_class(runtime, result.exit_code),
                               timed_out=result.timed_out, start_marker="start" in found, end_marker="end" in found,
                               token_in_output=token is not None
                               and token.encode() in result.stdout + result.stderr)
    except Exception as error:  # Create, write or control-plane failure: an infra fact, never retried.
        ours = not isinstance(error, ContainerExists)
        output += f"\n[infra: {type(error).__name__}: {error}]\n".encode()
    finally:
        confirmed = remove(config.name) if ours else None
    return Observation(facts, output, duration, token, confirmed)


def run_probe(environment: Environment, runtime: Runtime, patch: FrozenPatch, role: str, *,
              revision: str = "vulnerable", run_id: str | None = None, artifacts: Path | str | None = None,
              timeout: float = PROBE_TIMEOUT_S) -> ProbeRun:
    if role not in ("control", "exploit") or revision not in ("vulnerable", "fixed"):
        raise ValueError("role must be control or exploit and revision vulnerable or fixed")
    draft = patch.control if role == "control" else patch.exploit
    seen = observe(environment, runtime, draft, revision=revision, run_id=run_id, timeout=timeout,
                   patch_sha256=patch.sha256)
    return ProbeRun(role=draft.role, revision=revision, patch_sha256=patch.sha256, facts=seen.facts,
                    outcome=classify(seen.facts), output=ArtifactStore(artifacts).put(seen.output),
                    duration_s=seen.duration_s, cleanup_confirmed=seen.cleanup_confirmed)


def _truncate(text: str, limit: int = DIAGNOSTICS_LIMIT) -> str:
    data = text.encode()
    if len(data) <= limit:
        return text
    marker = b"\n[... truncated ...]\n"
    half = (limit - len(marker)) // 2
    return (data[:half] + marker + data[-half:]).decode(errors="ignore")


def diagnose(environment: Environment, runtime: Runtime, draft: ProbeDraft, *, run_id: str | None = None,
             timeout: float = PROBE_TIMEOUT_S) -> tuple[Outcome, str]:
    """D3: run a draft the same way, on the vulnerable revision. Only a ``not_run`` or ``errored`` outcome returns
    the author's own output (at most 8 KB, token redacted); any other outcome returns an empty string, so an author
    can fix mechanics but never learns whether its assertion held."""
    seen = observe(environment, runtime, draft, revision="vulnerable", run_id=run_id, timeout=timeout)
    outcome = classify(seen.facts)
    if outcome not in (Outcome.NOT_RUN, Outcome.ERRORED):
        return outcome, ""
    text = seen.output.decode(errors="replace")
    if seen.token:
        text = text.replace(seen.token, "<token>")
    return outcome, _truncate(text)
