"""Trusted build replay (stage 4, ``stages.Replay``).

The Builder agent only proposes a Recipe. Trusted code replays it here in a fresh sandbox that no agent touched,
requires the baseline test to pass with no network, and seals the result as an Environment keyed by (runtime row and
image, recipe, revision tree): the exact-environment cache of amendment A3. Docker seals it as an image; a backend
that cannot snapshot replays the sealed recipe into each probe's fresh sandbox. Every command runs exactly once; a
timeout or sandbox failure is recorded, never retried. The sandbox is always removed. All of it goes through the
``Sandboxes`` port (``workspace.sandboxes()`` unless one is passed).
"""
from __future__ import annotations

import hashlib
import json
import shlex
import uuid
from pathlib import Path

from .artifacts import ArtifactStore
from .contracts import BuildResult, Case, Environment, Recipe, Runtime
from .workspace import sandboxes as configured
from .workspace.port import Exec, Sandboxes, SandboxExists, SandboxSpec, labels

SETUP_TIMEOUT_S = 1800.0
BASELINE_TIMEOUT_S = 600.0
REPLAY_BUDGET_S = 3600.0
"""The most one replay of a sealed recipe (copy, every setup step, baseline) may take when a backend replays it again
to open an environment; equal to the replay activity's own bound, which the sealed replay already completed within."""
ENV_REPOSITORY = "corsair-v2-env"


def recipe_sha256(recipe: Recipe) -> str:
    return hashlib.sha256(json.dumps(recipe.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def environment_key(runtime: Runtime, recipe_digest: str, tree_sha256: str) -> str:
    """The exact-environment identity. The image is included beside the row so a re-pinned row never reuses an
    environment built on its previous image."""
    material = [runtime.row_id, runtime.image, recipe_digest, tree_sha256]
    return hashlib.sha256(json.dumps(material).encode()).hexdigest()


def _record(log: list[bytes], argv: tuple[str, ...] | list[str], result: Exec) -> None:
    status = ("timed out" if result.timed_out else "container failed" if result.container_failed
              else f"exit {result.exit_code}")
    log.append(f"$ {shlex.join(argv)}\n".encode() + result.stdout + result.stderr + f"\n[{status}]\n".encode())


def _failure(result: Exec, what: str) -> str:
    if result.timed_out:
        return f"{what} timed out"
    if result.container_failed:
        return f"{what}: container failed"
    return f"{what} exited {result.exit_code}"


def replay(case: Case, runtime: Runtime, recipe: Recipe, *, revision: str = "vulnerable", run_id: str | None = None,
           artifacts: Path | str | None = None, workdir: str | None = None, setup_timeout: float = SETUP_TIMEOUT_S,
           baseline_timeout: float = BASELINE_TIMEOUT_S, backend: Sandboxes | None = None
           ) -> tuple[BuildResult, Environment | None]:
    if revision not in ("vulnerable", "fixed"):
        raise ValueError("revision must be 'vulnerable' or 'fixed'")
    tree = case.revision if revision == "vulnerable" else case.fixed_revision
    if tree is None:
        return BuildResult(recipe=recipe, replayed=False, reason="the case has no fixed revision"), None
    clobbered = [added.path for added in recipe.files if (Path(tree.source) / added.path).exists()]
    if clobbered:  # a recipe may add files, never replace the revision's own
        return BuildResult(recipe=recipe, replayed=False,
                           reason=f"recipe would overwrite files of the revision: {', '.join(clobbered)}"), None
    store = ArtifactStore(artifacts)
    digest = recipe_sha256(recipe)
    key = environment_key(runtime, digest, tree.tree_sha256)
    tag = f"{ENV_REPOSITORY}:{key[:32]}"
    backend = backend or configured()
    workdir = workdir or backend.workdir  # The backend's own workdir unless the caller names one.
    environment = Environment(image=tag, workdir=workdir, runtime_row=runtime.row_id, recipe_sha256=digest,
                              tree_sha256=tree.tree_sha256)
    cached = backend.find_environment(tag, key)
    if cached is not None:
        log = store.ref(cached) if cached else None
        return BuildResult(recipe=recipe, replayed=True, baseline_exit_code=0, log=log,
                           reason=f"exact-environment cache hit: {tag}"), environment

    spec = SandboxSpec(image=runtime.image, workdir=workdir,
                       labels=labels(run_id or uuid.uuid4().hex[:12], "build", revision=revision, env=key[:16]),
                       network="build" if recipe.network_during_setup else "none")
    log: list[bytes] = []
    baseline_exit: int | None = None
    reason = ""
    log_ref = None
    ours = True
    try:
        name = backend.create(spec)
        backend.copy_tree_in(name, Path(tree.source), workdir)
        for added in recipe.files:
            backend.write_file(name, f"{workdir}/{added.path}", added.content.encode())
        for index, step in enumerate(recipe.setup, 1):
            result = backend.exec_once(name, step, workdir=workdir, timeout=setup_timeout)
            _record(log, step, result)
            if result.exit_code != 0:
                reason = _failure(result, f"setup step {index}")
                break
        if not reason and recipe.network_during_setup:
            try:
                backend.drop_network(name)
            except Exception as error:
                reason = f"cannot remove the network before the baseline: {error}"
        if not reason:
            result = backend.exec_once(name, recipe.baseline_test, workdir=workdir, timeout=baseline_timeout)
            _record(log, recipe.baseline_test, result)
            baseline_exit = result.exit_code
            if result.exit_code != 0:
                reason = _failure(result, "baseline test")
        log_ref = store.put(b"".join(log))
        if not reason:
            try:
                backend.seal_environment(name, tag, key, log_ref.sha256, recipe=recipe, tree_source=Path(tree.source),
                                         base_image=runtime.image, setup_timeout=setup_timeout,
                                         baseline_timeout=baseline_timeout)
            except Exception as error:
                reason = str(error)
    except Exception as error:  # A create, copy or control-plane failure is recorded as the build's reason.
        ours = not isinstance(error, SandboxExists)
        reason = f"infra: {type(error).__name__}: {error}"
        log_ref = store.put(b"".join(log)) if log else None
    finally:
        # Never remove a sandbox another attempt owns; the reconciler sweeps it with its run.
        confirmed = backend.remove(spec.name) if ours else None
    ok = not reason
    built = BuildResult(recipe=recipe, replayed=ok, baseline_exit_code=baseline_exit, log=log_ref,
                        reason=reason[:2000], cleanup_confirmed=confirmed)
    return built, (environment if ok else None)
