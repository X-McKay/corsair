"""Trusted build replay (stage 4, ``stages.Replay``).

The Builder agent only proposes a Recipe. Trusted code replays it here in a fresh container that no agent touched,
requires the baseline test to pass with no network, and commits the result as an Environment image keyed by
(runtime row and image, recipe, revision tree): the exact-environment cache of amendment A3. Every command runs
exactly once; a timeout or container failure is recorded, never retried. The container is always removed.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import uuid
from pathlib import Path

from .artifacts import ArtifactStore
from .contracts import BuildResult, Case, Environment, Recipe, Runtime
from .workspace.docker import (LABEL, ContainerExists, DockerConfig, Exec, copy_tree_in, create, docker, exec_once,
                               labels, make_workdir, owner, remove)

SETUP_TIMEOUT_S = 1800.0
BASELINE_TIMEOUT_S = 600.0
ENV_REPOSITORY = "corsair-v2-env"
LOG_LABEL = f"{LABEL}.env.log"
KEY_LABEL = f"{LABEL}.env.key"


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
           artifacts: Path | str | None = None, workdir: str = "/work", setup_timeout: float = SETUP_TIMEOUT_S,
           baseline_timeout: float = BASELINE_TIMEOUT_S) -> tuple[BuildResult, Environment | None]:
    if revision not in ("vulnerable", "fixed"):
        raise ValueError("revision must be 'vulnerable' or 'fixed'")
    tree = case.revision if revision == "vulnerable" else case.fixed_revision
    if tree is None:
        return BuildResult(recipe=recipe, replayed=False, reason="the case has no fixed revision"), None
    store = ArtifactStore(artifacts)
    digest = recipe_sha256(recipe)
    key = environment_key(runtime, digest, tree.tree_sha256)
    tag = f"{ENV_REPOSITORY}:{key[:32]}"
    environment = Environment(image=tag, workdir=workdir, runtime_row=runtime.row_id, recipe_sha256=digest,
                              tree_sha256=tree.tree_sha256)

    cached = docker("image", "inspect", "--format", "{{json .Config.Labels}}", tag)
    if cached.returncode == 0:
        found = json.loads(cached.stdout) or {}
        if found.get(KEY_LABEL) == key:
            log = store.ref(found.get(LOG_LABEL, "")) if found.get(LOG_LABEL) else None
            return BuildResult(recipe=recipe, replayed=True, baseline_exit_code=0, log=log,
                               reason=f"exact-environment cache hit: {tag}"), environment

    config = DockerConfig(image=runtime.image, workdir=workdir,
                          labels=labels(run_id or uuid.uuid4().hex[:12], "build", revision=revision, env=key[:16]),
                          network="bridge" if recipe.network_during_setup else "none")
    log: list[bytes] = []
    baseline_exit: int | None = None
    reason = ""
    log_ref = None
    ours = True
    try:
        name = create(config, adopt=False)
        uid, gid = owner(name)
        make_workdir(name, workdir, uid, gid)
        copy_tree_in(name, Path(tree.source), workdir, uid, gid)
        for index, step in enumerate(recipe.setup, 1):
            result = exec_once(name, step, workdir=workdir, timeout=setup_timeout)
            _record(log, step, result)
            if result.exit_code != 0:
                reason = _failure(result, f"setup step {index}")
                break
        if not reason and recipe.network_during_setup:
            detached = docker("network", "disconnect", "--force", "bridge", name)
            if detached.returncode != 0:
                reason = f"cannot remove the network before the baseline: {detached.stderr.decode(errors='replace')}"
        if not reason:
            result = exec_once(name, recipe.baseline_test, workdir=workdir, timeout=baseline_timeout)
            _record(log, recipe.baseline_test, result)
            baseline_exit = result.exit_code
            if result.exit_code != 0:
                reason = _failure(result, "baseline test")
        log_ref = store.put(b"".join(log))
        if not reason:
            committed = docker("commit", "--change", f"LABEL {KEY_LABEL}={key} {LOG_LABEL}={log_ref.sha256}", name,
                               tag, timeout=1800)
            if committed.returncode != 0:
                reason = f"docker commit failed: {committed.stderr.decode(errors='replace')[-1000:]}"
    except Exception as error:  # A create, copy or control-plane failure is recorded as the build's reason.
        ours = not isinstance(error, ContainerExists)
        reason = f"infra: {type(error).__name__}: {error}"
        log_ref = store.put(b"".join(log)) if log else None
    finally:
        # Never remove a container another attempt owns; the reconciler sweeps it with its run.
        confirmed = remove(config.name) if ours else None
    ok = not reason
    built = BuildResult(recipe=recipe, replayed=ok, baseline_exit_code=baseline_exit, log=log_ref,
                        reason=reason[:2000], cleanup_confirmed=confirmed)
    return built, (environment if ok else None)
