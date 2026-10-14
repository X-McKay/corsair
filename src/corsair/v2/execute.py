"""Trusted probe execution (stage 7, ``stages.Execute``) and the D3 mechanical check run.

Each probe runs alone, exactly once, in a fresh offline container from the replayed Environment image, with only its
own file written. Trusted code observes four things itself (D8): the exit code, sorted by the matrix row's exit-code
map; the ``start`` and ``end`` marker files the test writes under ``$CORSAIR_MARKER_DIR``; the ``check`` marker it
writes there immediately before its main assertion (``safe`` or ``unsafe``); and whether the per-run
``$CORSAIR_TOKEN`` (given to both roles) appears in the output. ``outcome.classify`` turns those facts into an
Outcome. Nothing here knows a language: the run argv comes from the row's template, filled generically.
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
from .contracts import (CheckResult, Environment, ExitClass, FrozenPatch, Outcome, ProbeDraft, ProbeFacts, ProbeRun,
                        Runtime)
from .outcome import classify, read_check
from .workspace.docker import ContainerExists, DockerConfig, create, exec_once, labels, remove, write_file

PROBE_TIMEOUT_S = 300.0
SYNTAX_LIMIT = 4 * 1024
CHECK_BYTES = 64
MARKER_ENV = "CORSAIR_MARKER_DIR"
TOKEN_ENV = "CORSAIR_TOKEN"
_PLACEHOLDER = re.compile(r"\{(file|name|class|module)\}")
_MARKERS_SCRIPT = ('for f in start end; do test -e "$1/$f" && echo "$f"; done; echo ---; '
                   f'test -f "$1/check" && head -c {CHECK_BYTES} "$1/check"; true')


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


def new_token() -> str:
    """A fresh token per run; both probes use it as their main assertion's failure message."""
    return secrets.token_hex(16)


@dataclass(frozen=True)
class Observation:
    facts: ProbeFacts
    output: bytes
    duration_s: float | None
    token: str
    cleanup_confirmed: bool | None
    syntax: tuple[int | None, bytes] | None = None  # (exit code, output) of the row's syntax check, when run


def _infra() -> ProbeFacts:
    return ProbeFacts(exit_code=None, exit_class=None, start_marker=False, end_marker=False, token_in_output=False)


def observe(environment: Environment, runtime: Runtime, draft: ProbeDraft, *, revision: str, run_id: str | None,
            timeout: float, patch_sha256: str | None = None, syntax_check: bool = False) -> Observation:
    """Run one draft once and record what was observed. Never retried; any failure is a container failure fact.

    With ``syntax_check`` (the D3 check run only) the row's syntax check runs first in the same container, without
    the token; it runs no application code, so its output may go back to the author."""
    token = new_token()
    marker_dir = f"/tmp/corsair-markers-{secrets.token_hex(8)}"
    extra = {"revision": revision} | ({"patch": patch_sha256[:16]} if patch_sha256 else {})
    config = DockerConfig(image=environment.image, workdir=environment.workdir, network="none",
                          labels=labels(run_id or uuid.uuid4().hex[:12], "execute", draft.role, **extra))
    env = {MARKER_ENV: marker_dir, TOKEN_ENV: token}
    facts, output, duration, ours, syntax = _infra(), b"", None, True, None
    try:
        name = create(config, adopt=False)
        write_file(name, posixpath.join(environment.workdir, draft.test_file), draft.source.encode())
        made = exec_once(name, ["mkdir", "-p", marker_dir], workdir="/", timeout=60)
        if made.exit_code != 0:
            raise RuntimeError(f"cannot create the marker directory: {made.stderr.decode(errors='replace')}")
        if syntax_check and runtime.syntax_check:
            checked = exec_once(name, fill_template(runtime.syntax_check, draft), workdir=environment.workdir,
                                timeout=timeout)
            syntax = (None if checked.timed_out else checked.exit_code, checked.stdout + checked.stderr)
        started = time.monotonic()
        result = exec_once(name, fill_template(runtime.run_template, draft), workdir=environment.workdir, env=env,
                           timeout=timeout)
        duration = time.monotonic() - started
        output = b"--- stdout ---\n" + result.stdout + b"\n--- stderr ---\n" + result.stderr
        markers = exec_once(name, ["sh", "-c", _MARKERS_SCRIPT, "sh", marker_dir], workdir="/", timeout=60)
        if markers.exit_code != 0:
            output += b"\n[markers unreadable: container failed]\n"
        else:
            names, _, check = markers.stdout.partition(b"---\n")
            found = names.decode(errors="replace").split()
            facts = ProbeFacts(exit_code=result.exit_code, exit_class=exit_class(runtime, result.exit_code),
                               timed_out=result.timed_out, start_marker="start" in found, end_marker="end" in found,
                               token_in_output=token.encode() in result.stdout + result.stderr,
                               check_marker=read_check(check) if check else None)
    except Exception as error:  # Create, write or control-plane failure: an infra fact, never retried.
        ours = not isinstance(error, ContainerExists)
        output += f"\n[infra: {type(error).__name__}: {error}]\n".encode()
    finally:
        confirmed = remove(config.name) if ours else None
    return Observation(facts, output, duration, token, confirmed, syntax)


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


def _truncate(text: str, limit: int = SYNTAX_LIMIT) -> str:
    data = text.encode()
    if len(data) <= limit:
        return text
    marker = b"\n[... truncated ...]\n"
    half = (limit - len(marker)) // 2
    return (data[:half] + marker + data[-half:]).decode(errors="ignore")


def check_result(facts: ProbeFacts) -> tuple[CheckResult, str | None]:
    """D3: the mechanical class of the check run and one fixed hint chosen from the exit class and the markers.

    Only a test body that never started (``not_run``) or failed before its check marker (``errored``) gets a class
    other than ``ok``. A harness error before ``start`` is the author's mechanics here (a collection or load error),
    so it is ``not_run`` with its own hint; everything else, infrastructure included, is ``ok`` and discarded.
    """
    if facts.timed_out or facts.exit_code is None:
        return "ok", None
    exit_class = facts.exit_class or ExitClass.UNKNOWN
    if exit_class is ExitClass.NO_TESTS:
        return "not_run", "not discovered"
    if not facts.start_marker:
        return "not_run", "harness error" if exit_class is ExitClass.HARNESS_ERROR else "body did not start"
    if classify(facts) is Outcome.ERRORED:
        return "errored", "raised before the check marker"
    return "ok", None


def diagnose(environment: Environment, runtime: Runtime, draft: ProbeDraft, *, run_id: str | None = None,
             timeout: float = PROBE_TIMEOUT_S) -> tuple[CheckResult, str | None]:
    """D3 mechanical check (``stages.Diagnose``): run one frozen draft once on the vulnerable revision, before review.

    Returns ``ok`` with no feedback, or ``not_run`` / ``errored`` with the class, a fixed hint (``check_result``)
    and, when the row declares one, the full output of its syntax check (capped at 4 KiB). The test run's own output
    never reaches the author: even a line naming its own file can carry what application code printed. So an author
    can fix mechanics but never learns whether its assertion held.
    """
    seen = observe(environment, runtime, draft, revision="vulnerable", run_id=run_id, timeout=timeout,
                   syntax_check=True)
    result, hint = check_result(seen.facts)
    if result == "ok":
        return result, None
    feedback = f"check: {result}\nhint: {hint}"
    if seen.syntax is not None:
        code, text = seen.syntax
        status = "timed out" if code is None else f"exit {code}"
        feedback += f"\n--- syntax check ({status}) ---\n{_truncate(text.decode(errors='replace'))}"
    return result, feedback
