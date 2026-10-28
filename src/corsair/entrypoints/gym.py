"""The evaluation-gym runner: one frozen tier through the production worker, scored once.

``run_gym`` composes the existing worker (``compose_worker``) in-process on a per-branch
task queue in the dedicated ``corsair-gym`` Temporal namespace, submits the existing
``EvaluationWorkflow`` through the typed API and scores the saved report with the gym
scorer. Nothing here schedules work or decides a label: Temporal, the workflow and the
kernel do that exactly as in production. The one addition is the run's own retry: an
episode the gym scorer names operational (a fault of the run, not behaviour) is submitted
once more, after the others, as one more batch of the same workflow, and its retry is
scored in its place. Trusted images are tagged by the content of their
build inputs, so two worktrees never overwrite each other's tags and an uncommitted driver
edit gets a new tag (and so a new configuration identity).

Runs persist in one store shared by every worktree of the repository,
``<main checkout>/.runs/gym/``: ``store/`` holds the content-addressed blobs and operation
records, ``runs/<run-id>/`` each run directory and ``reference/`` the reference scorecards,
so a run outlives the worktree that produced it. ``lock/`` holds the run lock: one live
``gym run`` or ``gym verify`` at a time per gym root, because every live run shares one model
endpoint and overlapping runs skew each other's timing and failures. Waiters queue under
``lock/queue/`` and take the lock in the order they joined.

A run pins what it scores: the manifest is read once at admission, its bytes are kept as
``dataset.json`` in the run directory with its digest in ``run.json``, and the end of the
run scores against that copy, never against whatever the checkout holds by then. Every
module the finish imports on first use is imported at admission too, so a checkout edited
while a run executes can change neither its score nor its completion.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Generator,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager, nullcontext
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from temporalio.client import Client, WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError, RPCStatusCode

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.adapters.temporal.client import connect, wait_for_result
from corsair.contracts import (
    BatchItem,
    BatchRequest,
    Budgets,
    Confirmation,
    ConfirmationSkip,
    Dataset,
    GateDecision,
    GateTrack,
    GateVerdict,
    InvestigationRequest,
    InvestigationResult,
    NoiseBand,
    OperationalReason,
    RunContext,
    Scorecard,
    SkipReason,
    TierGate,
    Trajectory,
    VerifyRecord,
    digest,
)
from corsair.contracts.evaluation import MAX_BATCH_REQUESTS
from corsair.entrypoints.api import start_evaluation
from corsair.entrypoints.worker import compose_worker, compose_worker_activities
from corsair.evaluation.datasets import LoadedDataset, dataset_root, parse_dataset
from corsair.evaluation.families import label_rows
from corsair.evaluation.gym.budgets import budgets_digest, load_budgets
from corsair.evaluation.gym.gate import (
    admit_min_cases,
    admit_track,
    chain_decision,
    confirmation_cases,
    confirmation_decision,
    gate,
    trajectories_reproduce,
)
from corsair.evaluation.gym.ledger import candidate_identity
from corsair.evaluation.gym.noise import assign_bands
from corsair.evaluation.gym.scoring import (
    ATTEMPT_KEY,
    REPORT_FILE,
    RETRIED_REASON_KEY,
    SCORECARD_FILE,
    SUPERSEDES_KEY,
    TRAJECTORIES_FILE,
    language_of,
    load_results,
    read_scorecard,
    read_trajectories,
    score_loaded_report,
    write_scorecard,
    write_trajectories,
)
from corsair.evaluation.scoring import save_report, score_batch
from corsair.observability.logging import event, safe_text
from corsair.settings import Settings
from corsair.steps.activities import Activities

GYM_NAMESPACE = "corsair-gym"
TIER_DIR = Path("evals/datasets")
DEFAULT_BUDGETS = Path("evals/experiments/budgets.json")
# Gym runs are live by default: the checkout's operator settings when they exist.
LIVE_SETTINGS = Path(".state/settings.json")
DRIVER_DIR = Path("src/corsair/adapters/sandboxing/drivers")
# The shared gym root below the main checkout, and its fixed layout.
SHARED_ROOT = Path(".runs/gym")
RUN_FILE = "run.json"
BUDGETS_FILE = "budgets.json"
# The exact manifest bytes a run was admitted with, beside run.json.
DATASET_FILE = "dataset.json"
VERDICT_FILE = "verdict.json"
# The first attempts a run retried, beside its scored trajectories.
SUPERSEDED_FILE = "superseded.jsonl"
# A retry batch's identity: ``<run id>.a2`` (attempt 2), then ``.a2.1``, ``.a2.2`` … when
# more episodes need a retry than one batch holds.
RETRY_SUFFIX = ".a2"
VERIFY_TIERS = ("tier0", "tier1")
# Repeats of each case an INCONCLUSIVE tier's confirmation re-runs (``--confirm-repeats``).
DEFAULT_CONFIRM_REPEATS = 5
# The tiers ``verify --min-cases`` narrows; tier0 has one case per language, so every
# language keeps deciding its smoke gate.
MIN_CASES_TIERS = ("tier1",)
_RUN_STAMP = re.compile(r"-(\d{8}t\d{6})-[0-9a-f]{6}$")
# Generated bytecode is never an image input (the Dockerfiles copy only reviewed files).
_GENERATED = frozenset({"__pycache__"})
_TAG_LENGTH = 7
_QUEUE_SLUG_LENGTH = 60
_RUN_SLUG_LENGTH = 20
_SERVER_READY_SECONDS = 60.0
_SERVER_STOP_SECONDS = 20.0
# The run lock under the gym root.
LOCK_DIR = "lock"
LOCK_FILE = "holder.json"
LOCK_QUEUE = "queue"
DEFAULT_LOCK_TIMEOUT = 2 * 60 * 60.0
LOCK_POLL_SECONDS = 2.0
LOCK_NOTICE_SECONDS = 60.0

# Modules the end of a run imports on first use: scoring revalidates saved receipts with the
# evidence verifier, which other callers import lazily because it loads the Docker SDK.
FINISH_IMPORTS = ("corsair.steps.verification",)

type ActivityComposer = Callable[[Settings], Activities]
type BatchObserver = Callable[[WorkflowHandle[Any, list[BatchItem]]], Awaitable[list[BatchItem]]]


class GymRefused(ValueError):
    """A run the gym will not start; nothing was submitted."""


class DatasetMismatch(GymRefused):
    """A manifest whose digest is not the one a run pinned; nothing was scored."""


# Tiers, selection and identities


def resolve_tier(tier: str, root: Path) -> Path:
    """``tier0`` -> ``evals/datasets/gym-tier0.json``; an existing manifest path is accepted."""
    candidate = Path(tier)
    if candidate.suffix == ".json" and candidate.is_file():
        return candidate
    manifest = root / TIER_DIR / f"gym-{tier}.json"
    if not manifest.is_file():
        raise ValueError(f"no gym tier {tier!r}: {manifest} does not exist")
    return manifest


def select_requests(
    requests: Sequence[InvestigationRequest], *, cases: Sequence[str], languages: Sequence[str]
) -> list[InvestigationRequest]:
    """Filter manifest entries in memory; language is the recipe-kind prefix."""
    known = {request.case.case_id for request in requests}
    unknown = sorted(set(cases) - known)
    if unknown:
        raise ValueError(f"case {', '.join(unknown)} is not in the tier")
    selected = [
        request
        for request in requests
        if (not cases or request.case.case_id in cases)
        and (not languages or language_of(request.case.recipe.kind) in languages)
    ]
    if not selected:
        raise ValueError("the --case and --lang filters select no case")
    return selected


def check_concurrency(settings: Settings, concurrency: int) -> None:
    """Refuse a batch wider than the worker's activity slots; queued work skews timing."""
    if concurrency > settings.max_concurrent_activities:
        raise ValueError(
            f"--concurrency {concurrency} exceeds max_concurrent_activities "
            f"{settings.max_concurrent_activities}; raise it in the settings file or lower "
            "--concurrency"
        )


def _slug(value: str, length: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:length].rstrip("-") or "x"


def gym_task_queue(branch: str, commit: str) -> str:
    """``gym-<branch-slug>-<sha7>``: one queue per branch and commit, never shared."""
    return f"gym-{_slug(branch, _QUEUE_SLUG_LENGTH)}-{commit[:7]}"


def new_run_id(dataset: Path) -> str:
    """``gym-<tier>-<utc time>-<6 hex>``, short enough for child workflow suffixes."""
    stem = _slug(dataset.stem.removeprefix("gym-"), _RUN_SLUG_LENGTH)
    stamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%S")
    return f"gym-{stem}-{stamp}-{uuid4().hex[:6]}"


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ValueError(f"git {' '.join(arguments)} failed in {root}; run from a git checkout")
    return completed.stdout.strip()


def git_revision(root: Path) -> tuple[str, str]:
    """The checkout's branch name (``HEAD`` when detached) and full commit."""
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD"), _git(root, "rev-parse", "HEAD")


def git_dirty(root: Path) -> bool:
    """Whether tracked or untracked (not ignored) files differ from the commit."""
    return bool(_git(root, "status", "--porcelain"))


def git_at_finish(root: Path) -> dict[str, object]:
    """``run.json``'s commit and dirty flag of the checkout when the run finished.

    A commit that differs from the one the run started at means the checkout changed while
    the run executed. A fact git cannot report stays None, never a guess.
    """
    try:
        commit: str | None = git_revision(root)[1]
    except (ValueError, OSError):
        commit = None
    try:
        dirty: bool | None = git_dirty(root)
    except (ValueError, OSError):
        dirty = None
    return {"git_commit_at_finish": commit, "source_dirty_at_finish": dirty}


def checkout_root() -> Path:
    """The git top level of the current directory: the tree whose images and tiers run."""
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel"))


def shared_gym_root(root: Path) -> Path:
    """``<main checkout>/.runs/gym``: the same directory from every worktree of the repository.

    The main checkout is the parent of git's common directory; a layout without a ``.git``
    common directory (a bare repository's worktree) falls back to this checkout.
    """
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    main = common.parent if common.name == ".git" else Path(root).resolve()
    return main / SHARED_ROOT


@dataclass(frozen=True)
class GymPaths:
    """Where gym runs live: ``root`` holds ``runs/`` and ``reference/``; ``store`` the blobs."""

    root: Path
    store: Path

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def reference(self) -> Path:
        return self.root / "reference"


_DEFAULT_ARTIFACT_ROOT = Settings.model_fields["artifact_root"].default


def gym_paths(root: Path | None, settings: Settings) -> GymPaths:
    """Settings naming an artifact root keep it as the store; otherwise the shared root.

    ``root`` is the checkout (default: the current one), read only for the shared root.
    """
    if settings.artifact_root != _DEFAULT_ARTIFACT_ROOT:
        store = Path(settings.artifact_root).absolute()
        return GymPaths(root=store / "gym", store=store)
    shared = shared_gym_root(checkout_root() if root is None else root)
    return GymPaths(root=shared, store=shared / "store")


def read_run_record(run_dir: Path) -> dict[str, Any]:
    """The run directory's ``run.json``, or an empty record for a run written without one."""
    path = run_dir / RUN_FILE
    return json.loads(path.read_text()) if path.is_file() else {}


def run_store(run_dir: Path, root: Path | None, settings: Settings) -> Path:
    """The store a run wrote to: its recorded store when present, else the configured one."""
    recorded = read_run_record(run_dir).get("store")
    if isinstance(recorded, str) and Path(recorded).is_dir():
        return Path(recorded)
    return gym_paths(root, settings).store


# The pinned dataset


@dataclass(frozen=True)
class PinnedDataset:
    """A run's manifest read once at admission: its bytes, the dataset root its entries
    resolve against, and the dataset, requests and oracles parsed from those bytes."""

    source: Path
    root: Path
    content: bytes
    loaded: LoadedDataset

    @property
    def dataset_digest(self) -> str:
        return digest(self.loaded[0])

    @property
    def entries(self) -> int:
        return len(self.loaded[0].entries)


def pin_dataset(path: Path) -> PinnedDataset:
    """Read the manifest once and load its frozen requests and oracles from those bytes."""
    content = path.read_bytes()
    root = dataset_root(path)
    return PinnedDataset(path, root, content, parse_dataset(content, root))


def manifest_digest(path: Path) -> str:
    """The dataset digest a report and scorecard record for this manifest."""
    return digest(Dataset.model_validate_json(path.read_bytes()))


@dataclass(frozen=True)
class ScoringDataset:
    """The manifest an offline command reads for a run, and whether the run pinned it.

    ``root`` resolves the entries of the run directory's copy; None means the manifest's
    own dataset root.
    """

    path: Path
    root: Path | None
    pinned: bool


def run_dataset(run_dir: Path, explicit: Path | None) -> ScoringDataset | None:
    """The manifest to score or capture ``run_dir`` against.

    A run keeps the manifest it was admitted with as ``dataset.json`` and its digest in
    ``run.json``; that copy is the default, resolved below the recorded dataset root.
    ``explicit`` (``--dataset``) is accepted only when its digest is the pinned one; any
    other digest raises ``DatasetMismatch`` naming both, so a run is never re-scored against
    another manifest. A run from before pinning has no copy: ``explicit`` is returned
    unpinned, and None when there is none.
    """
    copy = run_dir / DATASET_FILE
    if not copy.is_file():
        return None if explicit is None else ScoringDataset(explicit, None, pinned=False)
    record = read_run_record(run_dir)
    pinned = manifest_digest(copy)
    recorded = record.get("dataset_digest")
    if recorded != pinned:
        raise DatasetMismatch(
            f"dataset_mismatch: the pinned copy {copy} has digest {pinned}, but {RUN_FILE} "
            f"recorded {recorded or 'no digest'}; the run directory was altered after the run."
        )
    if explicit is not None:
        given = manifest_digest(explicit)
        if given != pinned:
            raise DatasetMismatch(
                f"dataset_mismatch: --dataset {explicit} has digest {given}, but run "
                f"{run_dir.name} ran the manifest with digest {pinned}; a run is scored only "
                f"against the manifest it ran. Omit --dataset to use its pinned copy {copy}."
            )
        return ScoringDataset(explicit, None, pinned=True)
    root = record.get("dataset_root")
    if not isinstance(root, str):
        raise ValueError(
            f"{run_dir / RUN_FILE} records no dataset_root for the pinned copy; pass --dataset "
            f"with digest {pinned}"
        )
    return ScoringDataset(copy, Path(root), pinned=True)


def unpinned_warning(run_dir: Path, manifest: Path) -> str:
    """The code-owned stderr line for a run from before pinning."""
    return (
        f"Warning: dataset_unpinned: `{run_dir}` has no {DATASET_FILE} (a run from before "
        f"dataset pinning); using `{manifest}`, whose digest cannot be checked against the "
        "manifest the run executed.\n"
    )


type RunContextSource = Literal["run.json", "scorecard.json", "flags", "unknown"]


def _recorded_context(record: Mapping[str, Any]) -> RunContext | None:
    """``run.json``'s ``run`` block; a run.json written before it recorded one has none."""
    block = record.get("run")
    return RunContext.model_validate(block) if isinstance(block, dict) else None


def recover_run_context(
    run_dir: Path, *, explicit: RunContext | None, fallback: RunContext
) -> tuple[RunContext, RunContextSource]:
    """The run context to rescore ``run_dir``'s report under, and where it came from.

    In order: ``run.json``'s ``run`` block; the run block of the scorecard beside the
    report when it names a commit (a run imported without ``run.json``); the operator's
    ``explicit`` flags; else ``fallback``, whose source is ``unknown``.
    """
    recorded = _recorded_context(read_run_record(run_dir))
    if recorded is not None:
        return recorded, "run.json"
    previous = run_dir / SCORECARD_FILE
    if previous.is_file():
        run = read_scorecard(previous).run
        if run.git_commit:
            return run, "scorecard.json"
    if explicit is not None:
        return explicit, "flags"
    return fallback, "unknown"


def write_recovered_run_record(run_dir: Path, run: RunContext, *, store: Path) -> bool:
    """Write ``run.json`` for a run imported without one, from the context its scorecard kept.

    Returns False, writing nothing, when ``run.json`` already exists.
    """
    record = {
        "schema_version": "corsair.gym-run/1",
        "run_id": run.run_id,
        "tier": _run_tier({}, run.run_id),
        "git": {"branch": run.git_branch, "commit": run.git_commit},
        "store": str(store),
        "run_dir": str(run_dir),
        "concurrency": run.concurrency,
        "run": run.model_dump(mode="json"),
        "recovered_from": SCORECARD_FILE,
        "recovered_at": _now(),
    }
    try:
        with (run_dir / RUN_FILE).open("x") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        return False
    return True


def default_settings_path(root: Path) -> Path | None:
    """The checkout's ``.state/settings.json`` when present; None selects built-in defaults."""
    path = root / LIVE_SETTINGS
    return path if path.is_file() else None


# Content-addressed images


def image_inputs(root: Path, language: str) -> list[Path]:
    """Working-tree files of ``deploy/<lang>/`` and the language's driver directory."""
    directories = [root / "deploy" / language, root / DRIVER_DIR / language]
    missing = [str(path.relative_to(root)) for path in directories if not path.is_dir()]
    if missing:
        raise ValueError(f"no image inputs for {language}: {', '.join(missing)} missing")
    files = [
        path
        for directory in directories
        for path in directory.rglob("*")
        if path.is_file()
        and not _GENERATED & set(path.relative_to(root).parts)
        and path.suffix != ".pyc"
    ]
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def image_tag(root: Path, language: str) -> str:
    """Seven hex of a sha256 over sorted relative paths and bytes of the image inputs."""
    hasher = hashlib.sha256()
    for path in image_inputs(root, language):
        content = path.read_bytes()
        name = path.relative_to(root).as_posix().encode()
        hasher.update(b"%d:%s\0%d:" % (len(name), name, len(content)))
        hasher.update(content)
    return hasher.hexdigest()[:_TAG_LENGTH]


def gym_images(root: Path, settings: Settings) -> dict[str, str]:
    """Each configured recipe kind's image as ``corsair-<lang>:<content tag>``."""
    tags: dict[str, str] = {}
    images: dict[str, str] = {}
    for kind in settings.images:
        language = language_of(kind)
        if language not in tags:
            tags[language] = image_tag(root, language)
        images[kind] = f"corsair-{language}:{tags[language]}"
    return images


def local_image_id(ref: str) -> str | None:
    """The local Docker image id for a tag, or None when it is not built."""
    completed = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def build_image(root: Path, language: str, ref: str) -> None:
    """The ``just images`` build: the language's Dockerfile with the checkout as context."""
    event("gym.image_building", image_id=ref, message=f"building {ref}")
    completed = subprocess.run(
        ["docker", "build", "-f", f"deploy/{language}/Dockerfile", "-t", ref, "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or completed.stdout).splitlines()[-15:])
        raise RuntimeError(f"docker build of {ref} failed:\n{safe_text(tail)}")


def ensure_images(root: Path, refs: Mapping[str, str]) -> dict[str, str]:
    """Build each missing ``{language: ref}`` image; return ``{ref: image id}``."""
    ids: dict[str, str] = {}
    for language, ref in sorted(refs.items()):
        image_id = local_image_id(ref)
        if image_id is None:
            build_image(root, language, ref)
            image_id = local_image_id(ref)
        if image_id is None:
            raise RuntimeError(f"{ref} is not available after its build")
        ids[ref] = image_id
    return ids


def gym_settings(
    base: Settings,
    *,
    temporal_address: str,
    task_queue: str,
    images: Mapping[str, str],
    store: Path | None = None,
) -> Settings:
    """The run's in-memory settings: gym namespace, its queue, store and content-tagged images."""
    python_image = next(
        (ref for kind, ref in images.items() if language_of(kind) == "python"), base.image
    )
    return Settings.model_validate(
        {
            **base.model_dump(mode="json"),
            "artifact_root": str(store) if store is not None else base.artifact_root,
            "temporal_address": temporal_address,
            "temporal_namespace": GYM_NAMESPACE,
            "task_queue": task_queue,
            "image": python_image,
            "images": dict(images),
        }
    )


# Temporal endpoint


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def namespace_exists(address: str, namespace: str) -> bool:
    """Whether the Temporal service at ``address`` has registered ``namespace``."""
    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

    async with asyncio.timeout(10):
        client = await Client.connect(
            address, namespace=namespace, data_converter=pydantic_data_converter
        )
    try:
        await client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=namespace), timeout=timedelta(seconds=5)
        )
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    return True


async def require_gym_namespace(address: str) -> None:
    """Refuse an existing server without ``corsair-gym``; never fall back to ``default``."""
    if not await namespace_exists(address, GYM_NAMESPACE):
        raise GymRefused(
            f"Temporal at {address} has no namespace {GYM_NAMESPACE}; gym runs never use "
            f"another namespace. Create it (temporal operator namespace create --namespace "
            f"{GYM_NAMESPACE} --address {address}) or omit --temporal-address."
        )


def _log_tail(path: Path, lines: int = 15) -> str:
    if not path.exists():
        return ""
    return safe_text("\n".join(path.read_text(errors="replace").splitlines()[-lines:]))


async def _await_server(process: subprocess.Popen[bytes], address: str, log: Path) -> None:
    deadline = time.monotonic() + _SERVER_READY_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"temporal server start-dev exited with status {process.returncode}:\n"
                + _log_tail(log)
            )
        try:
            if await namespace_exists(address, GYM_NAMESPACE):
                return
        except (RuntimeError, OSError, TimeoutError, RPCError):
            pass  # Not accepting connections or serving the namespace yet.
        await asyncio.sleep(0.25)
    raise RuntimeError(
        f"temporal server start-dev did not answer within {_SERVER_READY_SECONDS:.0f}s:\n"
        + _log_tail(log)
    )


async def _stop_server(process: subprocess.Popen[bytes]) -> None:
    """SIGTERM the server's process group, then SIGKILL; return once it has exited."""
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        await asyncio.to_thread(process.wait, _SERVER_STOP_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        await asyncio.to_thread(process.wait)


@asynccontextmanager
async def ephemeral_temporal(log: Path) -> AsyncGenerator[str]:
    """A headless in-memory ``temporal server start-dev`` with ``corsair-gym`` pre-created.

    Yields its address once the namespace answers; stops the server on exit, including
    when the run fails.
    """
    temporal = shutil.which("temporal")
    if temporal is None:
        raise RuntimeError("the temporal CLI is not on PATH; run inside `nix develop`")
    port = free_port()
    address = f"127.0.0.1:{port}"
    command = [
        temporal,
        "server",
        "start-dev",
        "--headless",
        "--ip",
        "127.0.0.1",
        "--port",
        str(port),
        "--namespace",
        GYM_NAMESPACE,
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        await _await_server(process, address, log)
        event("gym.temporal_ready", namespace=GYM_NAMESPACE, message=address)
        yield address
    finally:
        await _stop_server(process)
        event("gym.temporal_stopped", namespace=GYM_NAMESPACE, message=address)


@asynccontextmanager
async def temporal_endpoint(address: str | None, log: Path) -> AsyncGenerator[str]:
    """The operator's server (already checked for ``corsair-gym``) or an ephemeral one."""
    if address is not None:
        yield address
        return
    async with ephemeral_temporal(log) as started:
        yield started


# The shared-root run lock


class GymLockTimeout(GymRefused):
    """The run lock stayed held, or earlier waiters stayed queued, for all of ``--lock-timeout``."""


def _wall() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.isoformat()


@dataclass(frozen=True)
class LockHolder:
    """Who holds the gym root's run lock: written once, atomically, by the acquirer."""

    run_id: str
    pid: int
    host: str
    branch: str
    commit: str
    tier: str
    # When the run (process) started; the lock may have been taken much later.
    started_at: str
    # Unique per acquisition, so a release never removes another holder's lock.
    token: str
    # When this holder took the lock; None in a holder file from before it was recorded.
    acquired_at: str | None = None

    def record(self) -> dict[str, Any]:
        """The holder for run.json and views; the token stays in the lock file."""
        return {key: value for key, value in asdict(self).items() if key != "token"}

    def held_seconds(self, now: datetime | None = None) -> float | None:
        """Seconds since this holder took the lock; None when that time is unknown."""
        acquired = _moment(self.acquired_at)
        if acquired is None:
            return None
        return max(0.0, ((now or _wall()) - acquired).total_seconds())


def _moment(text: str | None) -> datetime | None:
    """A recorded timezone-aware ISO time, or None when absent or unreadable."""
    if text is None:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


# A holder record that cannot be read names no live process; it is reclaimed.
_UNREADABLE = LockHolder("unreadable", 0, "", "unknown", "unknown", "unknown", "", "")


def new_lock_holder(run_id: str, *, tier: str, branch: str, commit: str) -> LockHolder:
    """This process as the holder of the lock for ``run_id``; ``acquire_lock`` stamps it."""
    return LockHolder(
        run_id=run_id,
        pid=os.getpid(),
        host=socket.gethostname(),
        branch=branch,
        commit=commit,
        tier=tier,
        started_at=_now(),
        token=uuid4().hex,
    )


@dataclass(frozen=True)
class LockTicket:
    """A waiter's place in the first-come queue: ``<gym root>/lock/queue/<token>.json``."""

    run_id: str
    pid: int
    host: str
    branch: str
    commit: str
    tier: str
    joined_at: str
    # The waiter's holder token: one ticket per waiter, removed only by that waiter.
    token: str

    def record(self) -> dict[str, Any]:
        """The ticket for views; the token stays in the ticket file."""
        return {key: value for key, value in asdict(self).items() if key != "token"}

    def order(self) -> tuple[datetime, str]:
        """First come first served: join time, then token for ties."""
        joined = _moment(self.joined_at)
        if joined is None:  # Never published: _parse_ticket refuses such a ticket.
            raise ValueError(f"ticket {self.token} has no readable join time")
        return joined, self.token


def _ticket_for(holder: LockHolder, joined: datetime) -> LockTicket:
    return LockTicket(
        run_id=holder.run_id,
        pid=holder.pid,
        host=holder.host,
        branch=holder.branch,
        commit=holder.commit,
        tier=holder.tier,
        joined_at=_stamp(joined),
        token=holder.token,
    )


def lock_file(gym_root: Path) -> Path:
    """``<gym root>/lock/holder.json``: present exactly while the lock is held."""
    return gym_root / LOCK_DIR / LOCK_FILE


def queue_dir(gym_root: Path) -> Path:
    """``<gym root>/lock/queue/``: one ticket per waiting run, in join order."""
    return gym_root / LOCK_DIR / LOCK_QUEUE


def _string_fields(value: object, names: Iterable[str]) -> dict[str, Any] | None:
    """The named fields of a JSON record when ``pid`` is an int and the rest strings."""
    if not isinstance(value, dict):
        return None
    try:
        fields = {name: value[name] for name in names}
    except KeyError:
        return None
    if not isinstance(fields["pid"], int) or not all(
        isinstance(item, str) for name, item in fields.items() if name != "pid"
    ):
        return None
    return fields


def _parse_holder(text: str) -> LockHolder:
    try:
        value = json.loads(text)
    except ValueError:
        return _UNREADABLE
    required = [name for name in LockHolder.__dataclass_fields__ if name != "acquired_at"]
    fields = _string_fields(value, required)
    acquired = value.get("acquired_at") if isinstance(value, dict) else None
    if fields is None or not (acquired is None or isinstance(acquired, str)):
        return _UNREADABLE
    return LockHolder(**fields, acquired_at=acquired)


def _parse_ticket(text: str) -> LockTicket | None:
    try:
        fields = _string_fields(json.loads(text), LockTicket.__dataclass_fields__)
    except ValueError:
        return None
    if fields is None or _moment(fields["joined_at"]) is None:
        return None
    return LockTicket(**fields)


def read_lock(gym_root: Path) -> LockHolder | None:
    """The current holder, or None when the lock is free. The file is published whole."""
    try:
        return _parse_holder(lock_file(gym_root).read_text())
    except FileNotFoundError:
        return None


def _read_queue(gym_root: Path) -> list[tuple[Path, LockTicket | None]]:
    """Every published ticket (None when unreadable); temporary write names are skipped."""
    directory = queue_dir(gym_root)
    if not directory.is_dir():
        return []
    tickets = []
    for path in sorted(directory.glob("*.json")):
        try:
            tickets.append((path, _parse_ticket(path.read_text())))
        except FileNotFoundError:
            continue
    return tickets


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid exists on this host."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # It exists but belongs to another user.
    return True


def _holder_alive(holder: LockHolder | LockTicket, alive: Callable[[int], bool]) -> bool | None:
    """True or False for a process on this host; None (never stale) for another host's."""
    if holder.pid <= 0:
        return False
    if holder.host != socket.gethostname():
        return None
    return alive(holder.pid)


@contextmanager
def _lock_guard(gym_root: Path) -> Generator[Path]:
    """Serialise check, reclaim and publish between processes; never held across an await."""
    directory = gym_root / LOCK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".guard").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        try:
            yield lock_file(gym_root)
        finally:
            fcntl.flock(guard, fcntl.LOCK_UN)


def _publish(path: Path, value: Mapping[str, Any], token: str) -> None:
    """Write ``value`` whole to a temporary name and link it into place (never replacing)."""
    temporary = path.with_name(f".write-{token}")
    temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n")
    try:
        os.link(temporary, path)  # Fails rather than replaces when the name exists.
    finally:
        temporary.unlink()


def _reclaim_tickets(
    gym_root: Path, own: str, alive: Callable[[int], bool]
) -> tuple[list[LockTicket], LockTicket | None]:
    """Under the guard: drop dead or unreadable tickets; ``(live others, own ticket)``."""
    live: list[LockTicket] = []
    mine = None
    for path, ticket in _read_queue(gym_root):
        if ticket is not None and ticket.token == own:
            mine = ticket
            continue
        if ticket is not None and _holder_alive(ticket, alive) is not False:
            live.append(ticket)
            continue
        path.unlink(missing_ok=True)
        if ticket is None:
            name, why = "unreadable", "the ticket could not be read"
        else:
            name = ticket.run_id
            why = f"process {ticket.pid} on {ticket.host or 'an unknown host'} is gone"
        event(
            "gym.queue_reclaimed",
            level=logging.WARNING,
            run_id=name,
            message=f"removed the gym lock queue ticket of {name}: {why}",
        )
    return live, mine


@dataclass(frozen=True)
class _Attempt:
    """One attempt under the guard: taken (``holder``) or why not, and what was reclaimed."""

    holder: LockHolder | None
    blocking: LockHolder | None
    ahead: tuple[LockTicket, ...]
    waiting: int
    ticket: LockTicket | None
    reclaimed: LockHolder | None


def _try_lock(
    gym_root: Path,
    holder: LockHolder,
    alive: Callable[[int], bool],
    wall: Callable[[], datetime],
    joined: LockTicket | None,
) -> _Attempt:
    """Take the lock when it is free and no live waiter joined earlier, else join the queue.

    Under the guard: a stale holder and dead waiters' tickets are reclaimed; the lock is
    published with ``acquired_at`` and this waiter's ticket removed in the same step. A
    caller that is blocked publishes its ticket (``joined`` keeps its first join time).
    """
    with _lock_guard(gym_root) as path:
        current = read_lock(gym_root)
        reclaimed = None
        if current is not None and _holder_alive(current, alive) is False:
            path.unlink()
            reclaimed, current = current, None
            event(
                "gym.lock_reclaimed",
                level=logging.WARNING,
                run_id=reclaimed.run_id,
                message=f"reclaimed the gym lock from {reclaimed.run_id}: process "
                f"{reclaimed.pid} on {reclaimed.host or 'an unknown host'} is gone",
            )
        others, published = _reclaim_tickets(gym_root, holder.token, alive)
        now = wall()
        mine = joined or published or _ticket_for(holder, now)
        ahead = tuple(
            sorted((item for item in others if item.order() < mine.order()), key=LockTicket.order)
        )
        ticket_path = queue_dir(gym_root) / f"{holder.token}.json"
        if current is None and not ahead:
            taken = replace(holder, acquired_at=_stamp(now))
            _publish(path, asdict(taken), holder.token)
            ticket_path.unlink(missing_ok=True)
            return _Attempt(taken, None, (), 0, None, reclaimed)
        if published is None:
            ticket_path.parent.mkdir(exist_ok=True)
            _publish(ticket_path, asdict(mine), holder.token)
        return _Attempt(None, current, ahead, len(others) + 1, mine, reclaimed)


def _leave_queue(gym_root: Path, token: str) -> None:
    """Remove this waiter's own ticket, if it is still queued; never another waiter's."""
    with _lock_guard(gym_root):
        (queue_dir(gym_root) / f"{token}.json").unlink(missing_ok=True)


def duration_text(seconds: float) -> str:
    """``2h 00m 00s``, ``4m 05s`` or ``12s``."""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _holder_text(holder: LockHolder | LockTicket) -> str:
    return (
        f"{holder.run_id} ({holder.tier}, {holder.branch}@{holder.commit[:7]}, pid {holder.pid} "
        f"on {holder.host or 'an unknown host'})"
    )


def _held_text(seconds: float | None) -> str:
    return "held time unknown" if seconds is None else f"held {duration_text(seconds)}"


def _waiters_text(count: int) -> str:
    return f"{count} earlier waiter{'s' if count != 1 else ''}"


@dataclass(frozen=True)
class LockWait:
    """How a run came to hold the lock: whom it waited for, how long, what it reclaimed.

    ``queue_position`` is the 1-based place it joined the queue at (None when it took a
    free lock at its first attempt) and ``waiters_ahead`` how many live waiters were ahead.
    """

    holder: LockHolder
    seconds: float
    waited_for: tuple[LockHolder, ...] = ()
    reclaimed: tuple[LockHolder, ...] = ()
    queue_position: int | None = None
    waiters_ahead: int = 0

    def record(self) -> dict[str, Any]:
        """``run.json``'s ``lock`` entry."""
        return {
            "used": True,
            "holder_run_id": self.holder.run_id,
            "waited": bool(self.waited_for) or self.queue_position is not None,
            "wait_seconds": round(self.seconds, 1),
            "waited_for": [item.record() for item in self.waited_for],
            "reclaimed": [item.record() for item in self.reclaimed],
            "queue_position": self.queue_position,
            "waiters_ahead": self.waiters_ahead,
        }


def _waiting_notice(attempt: _Attempt, waited: float, timeout: float, now: datetime) -> None:
    position = f"queue position {len(attempt.ahead) + 1} of {attempt.waiting}"
    if attempt.blocking is not None:
        named = attempt.blocking.run_id
        whom = (
            f"held by {named} ({attempt.blocking.tier}, "
            f"{_held_text(attempt.blocking.held_seconds(now))})"
        )
    else:
        named = attempt.ahead[0].run_id
        whom = f"free, behind {_waiters_text(len(attempt.ahead))} (next: {named})"
    event(
        "gym.lock_waiting",
        run_id=named,
        seconds=round(waited),
        message=f"waiting for the gym lock {whom}; {position}; waited "
        f"{duration_text(waited)} of {duration_text(timeout)}",
    )


def _timeout_text(gym_root: Path, attempt: _Attempt, waited: float) -> str:
    where = f"the gym lock under {gym_root / LOCK_DIR}"
    if attempt.blocking is not None:
        state = f"{where} is still held by {_holder_text(attempt.blocking)}"
        remedy = (
            "if that process no longer runs, release it with `corsair gym lock release --force`"
        )
    else:
        state = (
            f"{where} is free, but {_waiters_text(len(attempt.ahead))} still queued ahead of "
            f"this run (next: {_holder_text(attempt.ahead[0])})"
        )
        remedy = (
            "if that waiter no longer runs on another host, remove its ticket under "
            f"{queue_dir(gym_root)}"
        )
    return (
        f"{state} after waiting {duration_text(waited)}; nothing was started. Wait for "
        f"that run, raise --lock-timeout, or, {remedy}."
    )


async def acquire_lock(
    gym_root: Path,
    holder: LockHolder,
    *,
    timeout: float,
    alive: Callable[[int], bool] = pid_alive,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    wall: Callable[[], datetime] = _wall,
) -> LockWait:
    """Take the gym root's run lock first come first served, waiting while it is busy.

    A caller that finds the lock free and no live waiter ahead takes it at once and leaves
    no ticket. Otherwise it joins the queue under ``lock/queue/`` and takes the lock only
    once it is free and no live ticket joined earlier. A holder or ticket whose process is
    gone on this host is reclaimed with a logged notice. While it waits, one line names the
    holder (or the next waiter) and this caller's queue position when the wait starts and
    every minute after; after ``timeout`` seconds the wait ends with ``GymLockTimeout``.
    The caller's own ticket is removed when it takes the lock, times out or fails.
    """
    begun = clock()
    waited_for: list[LockHolder] = []
    reclaimed: list[LockHolder] = []
    notice_at = begun
    joined: LockTicket | None = None
    position: tuple[int, int] | None = None
    try:
        while True:
            attempt = _try_lock(gym_root, holder, alive, wall, joined)
            if attempt.reclaimed is not None:
                reclaimed.append(attempt.reclaimed)
            if attempt.holder is not None:
                return LockWait(
                    attempt.holder,
                    clock() - begun,
                    tuple(waited_for),
                    tuple(reclaimed),
                    queue_position=None if position is None else position[0],
                    waiters_ahead=0 if position is None else position[1],
                )
            joined = attempt.ticket
            if position is None:
                position = (len(attempt.ahead) + 1, len(attempt.ahead))
            blocking = attempt.blocking
            if blocking is not None and all(item.token != blocking.token for item in waited_for):
                waited_for.append(blocking)
            waited = clock() - begun
            if waited >= timeout:
                raise GymLockTimeout(_timeout_text(gym_root, attempt, waited))
            if clock() >= notice_at:
                _waiting_notice(attempt, waited, timeout, wall())
                notice_at += LOCK_NOTICE_SECONDS
            await sleep(min(LOCK_POLL_SECONDS, timeout - waited))
    finally:
        _leave_queue(gym_root, holder.token)


def release_lock(gym_root: Path, holder: LockHolder) -> bool:
    """Remove the lock when ``holder`` still holds it; never another holder's."""
    with _lock_guard(gym_root) as path:
        current = read_lock(gym_root)
        if current is not None and current.token == holder.token:
            path.unlink()
            return True
    event(
        "gym.lock_lost",
        level=logging.WARNING,
        run_id=holder.run_id,
        message="the gym lock was released or taken by another process while this run held it",
    )
    return False


def force_release(gym_root: Path) -> LockHolder | None:
    """Remove the lock whoever holds it; return that holder (None when it was free).

    The queue is left alone: its waiters still take the lock in the order they joined.
    """
    with _lock_guard(gym_root) as path:
        current = read_lock(gym_root)
        if current is not None:
            path.unlink()
        return current


@asynccontextmanager
async def gym_lock(
    gym_root: Path,
    holder: LockHolder,
    *,
    timeout: float,
    alive: Callable[[int], bool] = pid_alive,
) -> AsyncGenerator[LockWait]:
    """Hold the run lock for the block; released on success, failure and cancellation."""
    wait = await acquire_lock(gym_root, holder, timeout=timeout, alive=alive)
    try:
        yield wait
    finally:
        release_lock(gym_root, holder)


def lock_status(
    gym_root: Path,
    *,
    alive: Callable[[int], bool] = pid_alive,
    wall: Callable[[], datetime] = _wall,
) -> dict[str, Any] | None:
    """The holder with ``alive`` (None on another host) and ``held_seconds``, or None.

    ``held_seconds`` counts from acquisition and is None when the holder file records no
    acquisition time (one written before it did).
    """
    holder = read_lock(gym_root)
    if holder is None:
        return None
    held = holder.held_seconds(wall())
    return {
        **holder.record(),
        "alive": _holder_alive(holder, alive),
        "held_seconds": None if held is None else round(held, 1),
    }


def queue_status(
    gym_root: Path,
    *,
    alive: Callable[[int], bool] = pid_alive,
    wall: Callable[[], datetime] = _wall,
) -> list[dict[str, Any]]:
    """Every readable queue ticket in join order with ``alive`` and ``waited_seconds``."""
    tickets = sorted(
        (ticket for _, ticket in _read_queue(gym_root) if ticket is not None),
        key=LockTicket.order,
    )
    now = wall()
    return [
        {
            **ticket.record(),
            "alive": _holder_alive(ticket, alive),
            "waited_seconds": round(max(0.0, (now - ticket.order()[0]).total_seconds()), 1),
        }
        for ticket in tickets
    ]


_LIVENESS = {True: "running", False: "process gone", None: "liveness unknown on another host"}


def lock_line(status: Mapping[str, Any]) -> str:
    """One code-owned line for a held lock, from ``lock_status``."""
    held = status["held_seconds"]
    since = (
        "; held time unknown (the holder file records no acquisition time)."
        if held is None
        else f" for {duration_text(held)} since it took the lock."
    )
    return (
        f"Gym lock: held by `{status['run_id']}` ({status['tier']}, "
        f"{status['branch']}@{str(status['commit'])[:7]}, pid {status['pid']} on "
        f"{status['host'] or 'an unknown host'}, {_LIVENESS[status['alive']]}){since}"
    )


def queue_lines(queue: Sequence[Mapping[str, Any]]) -> list[str]:
    """One code-owned line per waiter, from ``queue_status``, in the order they get the lock."""
    return [
        f"{number}. `{row['run_id']}` ({row['tier']}, pid {row['pid']} on "
        f"{row['host'] or 'an unknown host'}, {_LIVENESS[row['alive']]}), waiting "
        f"{duration_text(row['waited_seconds'])}."
        for number, row in enumerate(queue, start=1)
    ]


def _lock_scope(
    options: GymOptions, gym_root: Path, holder: LockHolder, held: LockWait | None
) -> AbstractAsyncContextManager[LockWait | None]:
    """The caller's lock when it already holds one, none with ``--no-lock``, else a new one."""
    if held is not None:
        return nullcontext(held)
    if not options.lock:
        return nullcontext(None)
    return gym_lock(gym_root, holder, timeout=options.lock_timeout)


# The run


@dataclass(frozen=True)
class GymOptions:
    dataset: Path
    settings: Settings
    repeats: int = 1
    concurrency: int = 2
    temporal_address: str | None = None
    cases: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    budgets: Path | None = None
    out: Path | None = None
    run_id: str | None = None
    # The command line that started the run, recorded in run.json (sanitized).
    invocation: tuple[str, ...] = ()
    # The shared-root run lock; off only for scripted tests (``--no-lock``).
    lock: bool = True
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT
    # Retry each operationally stopped episode once after the run's other episodes;
    # off with ``--no-retry``.
    retry: bool = True


@dataclass(frozen=True)
class GymRun:
    run_dir: Path
    scorecard: Scorecard
    trajectories: list[Trajectory]
    temporal_address: str
    ephemeral: bool
    wall_seconds: float


async def execute_batch(
    settings: Settings,
    batch: BatchRequest,
    compose_activities: ActivityComposer,
    observe: BatchObserver,
) -> list[BatchItem]:
    """Run the batch on an in-process production worker bound to the run's queue."""
    client = await connect(settings)
    async with compose_worker(client, settings, compose_activities(settings)):
        handle = await start_evaluation(client, batch, settings)
        event(
            "gym.submitted",
            run_id=batch.batch_id,
            namespace=settings.temporal_namespace,
            task_queue=settings.task_queue,
            total=len(batch.requests) * batch.repeats,
        )
        return await observe(handle)


def score_items(
    pinned: PinnedDataset, items: Sequence[BatchItem], store: ArtifactStore
) -> list[dict[str, Any]]:
    """Each batch receipt's report row as ``corsair eval`` scores it, in receipt order.

    Scores against the dataset pinned at admission, never the manifest on disk now.
    """
    dataset, _, oracles = pinned.loaded
    return label_rows(score_batch(items, store, oracles), dataset)


def score_rows(
    pinned: PinnedDataset,
    rows: Sequence[Mapping[str, Any]],
    store: ArtifactStore,
    *,
    run: RunContext,
    budgets: Budgets | None,
    sliced: bool,
) -> tuple[list[Trajectory], Scorecard]:
    """The gym scorer over report rows, one trajectory per row in row order."""
    report = {"rows": list(rows), "dataset_digest": pinned.dataset_digest}
    run_ids = [str(row.get("run_id")) for row in rows]
    return score_loaded_report(
        report, pinned.loaded, load_results(store, run_ids), run=run, budgets=budgets, sliced=sliced
    )


@dataclass(frozen=True)
class RetriedAttempt:
    """An operational first attempt and the retry receipt that replaces it when scored.

    ``position`` is the episode's place in the run's batch (``case index x repeats +
    repeat``), the order of its receipts, report rows and trajectories.
    """

    position: int
    first: Trajectory
    retry: BatchItem

    @property
    def reason(self) -> OperationalReason:
        if self.first.operational_reason is None:
            raise ValueError("only an operational first attempt is retried")
        return self.first.operational_reason


def retry_batch_id(run_id: str, chunk: int = 0) -> str:
    """``<run id>.a2`` for the first retry batch, ``<run id>.a2.<n>`` for later ones."""
    return f"{run_id}{RETRY_SUFFIX}" + (f".{chunk}" if chunk else "")


def retry_batches(batch: BatchRequest, positions: Sequence[int]) -> list[BatchRequest]:
    """The same requests for the episodes at ``positions``, one repeat each, in order.

    Each retry has a fresh child run id (so a fresh operation id) under the run's retry
    batch; the request, its identity and its budgets are the first attempt's own, and the
    batch keeps the run's concurrency, so no work waits for a slot it was not given.
    """
    requests = [batch.requests[position // batch.repeats] for position in positions]
    return [
        BatchRequest(
            batch_id=retry_batch_id(batch.batch_id, chunk),
            requests=requests[start : start + MAX_BATCH_REQUESTS],
            repeats=1,
            concurrency=batch.concurrency,
        )
        for chunk, start in enumerate(range(0, len(requests), MAX_BATCH_REQUESTS))
    ]


async def retry_operational(
    settings: Settings,
    batch: BatchRequest,
    first: Sequence[Trajectory],
    compose_activities: ActivityComposer,
    observe: BatchObserver,
) -> list[RetriedAttempt]:
    """Run once more every first attempt the gym scorer named operational.

    The classification is ``operational_stop``'s, read from the first attempts' scored
    trajectories; nothing here reads model text or decides a label. A retry is never
    retried again: whatever it returns is scored.
    """
    positions = [position for position, item in enumerate(first) if item.operational]
    if not positions:
        return []
    event(
        "gym.retrying",
        run_id=batch.batch_id,
        total=len(positions),
        reasons=",".join(
            sorted({str(first[position].operational_reason) for position in positions})
        ),
    )
    receipts: list[BatchItem] = []
    for retry in retry_batches(batch, positions):
        receipts.extend(await execute_batch(settings, retry, compose_activities, observe))
    retried = [
        RetriedAttempt(position, first[position], receipt)
        for position, receipt in zip(positions, receipts, strict=True)
    ]
    if any(item.retry.case_id != item.first.case_id for item in retried):
        raise ValueError("a retry receipt names another case than the attempt it replaces")
    return retried


def retried_rows(
    pinned: PinnedDataset,
    rows: Sequence[Mapping[str, Any]],
    retried: Sequence[RetriedAttempt],
    store: ArtifactStore,
) -> list[dict[str, Any]]:
    """The first attempts' rows with each retried episode replaced by its retry's row.

    A retry row keeps its place (so its case and repeat) and records ``attempt`` 2, the
    first attempt's operational reason and its run id.
    """
    merged = [dict(row) for row in rows]
    retry_rows = score_items(pinned, [item.retry for item in retried], store)
    for item, row in zip(retried, retry_rows, strict=True):
        merged[item.position] = {
            **row,
            ATTEMPT_KEY: 2,
            RETRIED_REASON_KEY: item.reason.value,
            SUPERSEDES_KEY: item.first.run_id,
        }
    return merged


def superseded_trajectories(retried: Sequence[RetriedAttempt]) -> list[Trajectory]:
    """Each retried first attempt as scored, marked ``superseded_by`` its retry's run id."""
    return [
        Trajectory.model_validate(
            {**item.first.model_dump(mode="json"), "superseded_by": item.retry.run_id}
        )
        for item in retried
    ]


def write_run_records(
    run_dir: Path,
    pinned: PinnedDataset,
    rows: Sequence[Mapping[str, Any]],
    store: ArtifactStore,
    *,
    run: RunContext,
    budgets: Budgets | None,
    sliced: bool,
    retried: Sequence[RetriedAttempt] = (),
) -> tuple[list[Trajectory], Scorecard]:
    """Write ``report.json`` as ``corsair eval`` would, then the trajectories and scorecard.

    ``rows`` are the first attempts' report rows; each retried episode's row is replaced by
    its retry's, and the superseded first attempts are written to ``superseded.jsonl``.
    """
    report = save_report(
        run_dir / REPORT_FILE,
        retried_rows(pinned, rows, retried, store),
        dataset_digest=pinned.dataset_digest,
    )
    trajectories, scorecard = score_rows(
        pinned, report["rows"], store, run=run, budgets=budgets, sliced=sliced
    )
    write_trajectories(run_dir / TRAJECTORIES_FILE, trajectories)
    if retried:
        write_trajectories(run_dir / SUPERSEDED_FILE, superseded_trajectories(retried))
    write_scorecard(run_dir / SCORECARD_FILE, scorecard)
    return trajectories, scorecard


def _default_budgets(root: Path) -> Path | None:
    path = root / DEFAULT_BUDGETS
    return path if path.is_file() else None


def tier_name(dataset: Path) -> str:
    """``gym-tier0.json`` -> ``tier0``; any other manifest by its stem."""
    return dataset.stem.removeprefix("gym-")


def safe_invocation(argv: Sequence[str]) -> tuple[str, ...]:
    """The program's base name and its arguments with credentials and endpoints redacted."""
    if not argv:
        return ()
    return (Path(argv[0]).name, *(safe_text(argument) for argument in argv[1:]))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run_record(
    options: GymOptions,
    *,
    run_id: str,
    run_dir: Path,
    paths: GymPaths,
    git: Mapping[str, object],
    budgets: Mapping[str, str] | None,
    sliced: bool,
    dataset: PinnedDataset,
    cases: Sequence[str],
    lock: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """``run.json``: safe metadata on how and where a run executed; never settings values.

    ``dataset`` is the manifest pinned at admission (its digest, entry count and the root
    its entries resolve against) and ``cases`` the case ids actually run; ``case_filter``
    and ``languages`` keep the ``--case`` and ``--lang`` selection. ``lock`` records whether
    the run held the gym root's lock and whom it waited for.
    """
    return {
        "schema_version": "corsair.gym-run/1",
        "run_id": run_id,
        "tier": tier_name(options.dataset),
        "dataset": str(options.dataset),
        "dataset_digest": dataset.dataset_digest,
        "dataset_entries": dataset.entries,
        "dataset_root": str(dataset.root),
        "invocation": list(options.invocation),
        "git": dict(git),
        "store": str(paths.store),
        "gym_root": str(paths.root),
        "run_dir": str(run_dir),
        "repeats": options.repeats,
        "concurrency": options.concurrency,
        "cases": list(cases),
        "case_filter": list(options.cases),
        "languages": list(options.languages),
        "sliced": sliced,
        "budgets": None if budgets is None else dict(budgets),
        "temporal": {"existing": options.temporal_address is not None},
        "lock": None if lock is None else dict(lock),
        "retry": options.retry,
        "started_at": _now(),
    }


def preload_finish() -> None:
    """Import at admission every module the end of a run imports on first use.

    A checkout edited while the run executes (a merge into the worktree) must not break
    the finish with an import of the changed source.
    """
    for name in FINISH_IMPORTS:
        importlib.import_module(name)


def finish_run(
    run_dir: Path,
    record: Mapping[str, Any],
    pinned: PinnedDataset,
    rows: Sequence[Mapping[str, Any]],
    store: ArtifactStore,
    *,
    root: Path,
    run: RunContext,
    budgets: Budgets | None,
    sliced: bool,
    started: float,
    retried: Sequence[RetriedAttempt] = (),
) -> tuple[list[Trajectory], Scorecard, float]:
    """Score the finished batch against the pinned dataset and complete ``run.json``.

    ``rows`` are the first attempts' report rows and ``retried`` the retries that replace
    the operational ones. Reads no manifest and imports nothing that admission did not;
    the checkout's commit and dirty flag at this point are recorded beside the ones the
    run started from.
    """
    trajectories, scorecard = write_run_records(
        run_dir, pinned, rows, store, run=run, budgets=budgets, sliced=sliced, retried=retried
    )
    wall = time.monotonic() - started
    _write_json(
        run_dir / RUN_FILE,
        {
            **record,
            "completed_at": _now(),
            "wall_seconds": round(wall, 1),
            "episodes": len(rows),
            "retried_episodes": len(retried),
            **git_at_finish(root),
            # The scorecard's run context, so a rescore of this run recovers it.
            "run": run.model_dump(mode="json"),
        },
    )
    return trajectories, scorecard, wall


async def run_gym(
    options: GymOptions,
    *,
    root: Path,
    compose_activities: ActivityComposer = compose_worker_activities,
    observe: BatchObserver = wait_for_result,
    held: LockWait | None = None,
    pinned: PinnedDataset | None = None,
) -> GymRun:
    """Run one tier, write report, trajectories and scorecard, and return the run.

    The gym root's run lock is taken after the run is admitted and before any image build
    or Temporal server, and released when the run ends; ``held`` is the lock a caller
    (``verify``) already holds for this run. Admission reads the manifest once (``pinned``
    when the caller already read it) and imports what the finish needs; the run directory
    keeps the manifest bytes as ``dataset.json``.

    With ``options.retry`` every episode the gym scorer names operational is run once more
    after the run's other episodes, on the same worker composition and concurrency, and its
    retry is the episode that is scored (``RetriedAttempt``).
    """
    pinned = pinned or pin_dataset(options.dataset)
    selected = select_requests(pinned.loaded[1], cases=options.cases, languages=options.languages)
    sliced = bool(options.cases or options.languages)
    check_concurrency(options.settings, options.concurrency)
    if options.temporal_address is not None:
        await require_gym_namespace(options.temporal_address)
    budgets_path = options.budgets or _default_budgets(root)
    budgets = load_budgets(budgets_path) if budgets_path is not None else None
    branch, commit = git_revision(root)
    git = {"branch": branch, "commit": commit, "dirty": git_dirty(root)}
    paths = gym_paths(root, options.settings)
    run_id = options.run_id or new_run_id(options.dataset)
    holder = new_lock_holder(run_id, tier=tier_name(options.dataset), branch=branch, commit=commit)
    preload_finish()
    async with _lock_scope(options, paths.root, holder, held) as lock:
        # Wall time starts once the lock is held; the wait is recorded on its own.
        started = time.monotonic()
        images = gym_images(root, options.settings)
        used = {language_of(request.case.recipe.kind) for request in selected}
        refs = {language_of(kind): ref for kind, ref in images.items() if language_of(kind) in used}
        image_ids = ensure_images(root, refs)
        run_dir = options.out or paths.runs / run_id
        record = run_record(
            options,
            run_id=run_id,
            run_dir=run_dir,
            paths=paths,
            git=git,
            budgets=None
            if budgets is None
            else {"source": str(budgets_path), "digest": budgets_digest(budgets)},
            sliced=sliced,
            dataset=pinned,
            cases=[request.case.case_id for request in selected],
            lock={"used": False} if lock is None else lock.record(),
        )
        _write_json(run_dir / RUN_FILE, record)
        (run_dir / DATASET_FILE).write_bytes(pinned.content)
        if budgets_path is not None:
            (run_dir / BUDGETS_FILE).write_bytes(budgets_path.read_bytes())
        batch = BatchRequest(
            batch_id=run_id,
            requests=selected,
            repeats=options.repeats,
            concurrency=options.concurrency,
        )
        event("gym.started", run_id=run_id, total=len(selected) * options.repeats)
        async with temporal_endpoint(options.temporal_address, run_dir / "temporal.log") as address:
            settings = gym_settings(
                options.settings,
                temporal_address=address,
                task_queue=gym_task_queue(branch, commit),
                images=images,
                store=paths.store,
            )
            run = RunContext(
                run_id=run_id,
                git_branch=branch,
                git_commit=commit,
                temporal_namespace=settings.temporal_namespace,
                task_queue=settings.task_queue,
                concurrency=options.concurrency,
                image_ids=image_ids,
            )
            store = ArtifactStore(settings.artifact_root)
            items = await execute_batch(settings, batch, compose_activities, observe)
            rows = score_items(pinned, items, store)
            retried: list[RetriedAttempt] = []
            if options.retry:
                first, _ = score_rows(pinned, rows, store, run=run, budgets=budgets, sliced=sliced)
                retried = await retry_operational(
                    settings, batch, first, compose_activities, observe
                )
        trajectories, scorecard, wall = finish_run(
            run_dir,
            record,
            pinned,
            rows,
            store,
            root=root,
            run=run,
            budgets=budgets,
            sliced=sliced,
            started=started,
            retried=retried,
        )
    event("gym.completed", run_id=run_id, seconds=round(wall, 1), total=len(trajectories))
    return GymRun(
        run_dir=run_dir,
        scorecard=scorecard,
        trajectories=trajectories,
        temporal_address=address,
        ephemeral=options.temporal_address is None,
        wall_seconds=wall,
    )


# The candidate protocol: tier0, gate, then tier1 and gate unless tier0 was rejected


type GateObserver = Callable[[str, TierGate, Scorecard, GymRun], None]


@dataclass(frozen=True)
class Verification:
    """One ``verify``: its chain decision, canonical record and runs, and the record's path."""

    decision: GateDecision
    record: VerifyRecord
    runs: dict[str, GymRun]
    verdict_path: Path
    # Per confirmed tier, the run of its re-run cases.
    confirmation_runs: dict[str, GymRun] = field(default_factory=dict)


def new_verify_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%S")
    return f"verify-{stamp}-{uuid4().hex[:6]}"


def verify_record(
    gates: Mapping[str, TierGate],
    runs: Mapping[str, GymRun],
    skipped: Mapping[str, SkipReason],
    *,
    decision: GateDecision,
    reference: Path,
    invocation: Sequence[str],
    track: GateTrack = "objective",
    noise: Sequence[str] = (),
    confirmation: Mapping[str, Confirmation] | None = None,
) -> VerifyRecord:
    """``verdict.json``: the candidate's identity, the chain decision and each tier's gate.

    The candidate is the one every run's scorecard names; a skipped tier makes the record
    incomplete, so its decision is not an acceptance.
    """
    branch, commit = candidate_identity(
        [(run.scorecard.run.git_branch, run.scorecard.run.git_commit) for run in runs.values()]
    )
    return VerifyRecord(
        branch=branch,
        commit=commit,
        track=track,
        tier0=gates.get("tier0"),
        tier1=gates.get("tier1"),
        decision=decision,
        complete=not skipped,
        skipped=dict(skipped),
        reference=str(reference),
        invocation=list(invocation) or None,
        recorded_at=datetime.now(UTC),
        noise=list(noise),
        confirmation=dict(confirmation or {}),
    )


async def verify_candidate(
    options: GymOptions,
    reference: Path,
    *,
    root: Path,
    tiers: Mapping[str, Path],
    skip: Sequence[str] = (),
    compose_activities: ActivityComposer = compose_worker_activities,
    observe: BatchObserver = wait_for_result,
    on_gate: GateObserver | None = None,
    track: GateTrack = "objective",
    target_language: str | None = None,
    noise: Mapping[str, NoiseBand] | None = None,
    min_cases: int | None = None,
    confirm_repeats: int | None = DEFAULT_CONFIRM_REPEATS,
) -> Verification:
    """Run and gate tier0, then tier1 unless tier0 was rejected.

    Each tier is gated against ``<reference>/<tier>.json`` on ``track`` (tier0 as a smoke
    gate); ``tiers`` maps ``tier0`` and ``tier1``, in that order, to their manifests. A
    ``target_language`` is checked against every reference before any tier runs, and so is
    each ``noise`` band (keyed by its file): it applies to the tier whose reference scored
    its dataset. ``min_cases`` narrows the deciding languages of the ``MIN_CASES_TIERS``
    gates (checked against their references first) and adds their paired per-case
    outcomes, from the run's trajectories and the reference run's under the gym root.

    When the chain is INCONCLUSIVE (no gate rejected or incomparable), each INCONCLUSIVE
    tier is confirmed unless ``confirm_repeats`` is ``None``: its deciding flips within
    noise (and its regressed deciding languages' flips) are re-run ``confirm_repeats``
    times each and gated as a slice screen against the same reference and band
    (``evaluation.gym.gate.confirmation_decision``), and that tier then decides the chain
    by its confirmation. A candidate run without trajectories, a band without pooled
    counts, a reference run without trajectories or no such flip skips the confirmation,
    recorded with its reason. The gym root's run lock is held once across every tier and
    confirmation. The canonical ``VerifyRecord`` is written to ``verdict.json`` under the
    gym root.
    """
    if tuple(tiers) != VERIFY_TIERS:
        raise ValueError(f"verify runs exactly {', '.join(VERIFY_TIERS)}, in that order")
    wanted = [name for name in tiers if name not in skip]
    references = {name: reference / f"{name}.json" for name in wanted}
    missing = [str(path) for path in references.values() if not path.is_file()]
    if missing:
        raise ValueError(f"no reference scorecard {', '.join(missing)}")
    baselines = {name: read_scorecard(path) for name, path in references.items()}
    # Every tier's manifest is read now, so tier1 runs the manifest verify was started with.
    manifests = {name: pin_dataset(tiers[name]) for name in wanted}
    for baseline in baselines.values():
        # Refuse a target language a reference lacks now, not after an hour of runs.
        admit_track(baseline, track, target_language)
    if min_cases is not None:
        for name in MIN_CASES_TIERS:
            if name in baselines:
                admit_min_cases(baselines[name], min_cases, target_language)
    bands = assign_bands(
        noise or {}, {name: card.dataset_digest for name, card in baselines.items()}
    )
    gates: dict[str, TierGate] = {}
    runs: dict[str, GymRun] = {}
    skipped: dict[str, SkipReason] = {name: "skipped_by_request" for name in tiers if name in skip}
    verify_id = new_verify_id()
    gym_root = gym_paths(root, options.settings).root
    branch, commit = git_revision(root)
    holder = new_lock_holder(verify_id, tier="+".join(wanted), branch=branch, commit=commit)
    # One lock across every tier, so no other run lands between tier0 and tier1.
    async with _lock_scope(options, gym_root, holder, None) as held:
        for name in wanted:
            if "tier0" in gates and gates["tier0"].gate.decision is GateDecision.REJECTED:
                skipped[name] = "rejected_at_tier0"
                continue
            run = await run_gym(
                replace(options, dataset=tiers[name], out=None, run_id=None),
                root=root,
                compose_activities=compose_activities,
                observe=observe,
                held=held,
                pinned=manifests[name],
            )
            # Only the first tier waited; later tiers run under the lock already held.
            held = _already_held(held)
            runs[name] = run
            narrowed = min_cases is not None and name in MIN_CASES_TIERS
            reference_trajectories = None
            if narrowed:
                reference_trajectories, _ = scorecard_trajectories(
                    references[name], baselines[name], gym_root / "runs"
                )
                if reference_trajectories is None:
                    # The gate then records ``paired`` as unknown and its view says so.
                    event(
                        "gym.paired_unknown",
                        run_id=baselines[name].run.run_id,
                        artifact=str(references[name]),
                    )
            gates[name] = TierGate(
                reference=str(references[name]),
                scorecard=str(run.run_dir / SCORECARD_FILE),
                run_dir=str(run.run_dir),
                # tier0 is the smoke gate: the track's improvement criterion is reported,
                # never rejecting.
                gate=gate(
                    baselines[name],
                    run.scorecard,
                    smoke=(name == "tier0"),
                    track=track,
                    target_language=target_language,
                    noise=bands[name][1] if name in bands else None,
                    min_cases=min_cases if narrowed and min_cases is not None else 1,
                    baseline_trajectories=reference_trajectories,
                    candidate_trajectories=run.trajectories if narrowed else None,
                ),
            )
            if on_gate is not None:
                on_gate(name, gates[name], baselines[name], run)
        confirmations: dict[str, Confirmation] = {}
        confirmation_runs: dict[str, GymRun] = {}
        # A tier is confirmed only when its INCONCLUSIVE gate decides the chain: no tier
        # was rejected or incomparable.
        chained = chain_decision([item.gate.decision for item in gates.values()])
        if confirm_repeats is not None and chained is GateDecision.INCONCLUSIVE:
            for name, gated in gates.items():
                if gated.gate.decision is not GateDecision.INCONCLUSIVE:
                    continue
                selection = confirmation_selection(
                    gated.gate, runs[name], references[name], baselines[name], gym_root / "runs"
                )
                if isinstance(selection, str):
                    event("gym.confirmation_skipped", tier=name, reason=selection)
                    confirmations[name] = Confirmation(skipped=selection)
                    continue
                cases, reference_trajectories = selection
                rerun = await run_gym(
                    replace(
                        options,
                        dataset=tiers[name],
                        cases=tuple(cases),
                        languages=(),
                        repeats=confirm_repeats,
                        out=None,
                        run_id=None,
                    ),
                    root=root,
                    compose_activities=compose_activities,
                    observe=observe,
                    held=held,
                    pinned=manifests[name],
                )
                held = _already_held(held)
                confirmation_runs[name] = rerun
                confirmations[name] = confirm_tier(
                    gated.gate,
                    baselines[name],
                    reference_trajectories,
                    rerun,
                    cases,
                    confirm_repeats,
                )
    # REJECTED when any tier rejected, else INCOMPARABLE when any was, else INCONCLUSIVE
    # when any was, else ACCEPTED; a confirmed tier decides by its confirmation.
    decision = chain_decision(
        [
            confirmations[name].decision if name in confirmations else item.gate.decision
            for name, item in gates.items()
        ]
    )
    record = verify_record(
        gates,
        {**runs, **{f"{name}-confirmation": run for name, run in confirmation_runs.items()}},
        skipped,
        decision=decision,
        reference=reference,
        invocation=options.invocation,
        track=track,
        noise=list(noise or ()),
        confirmation=confirmations,
    )
    verdict_path = gym_root / "verify" / verify_id / VERDICT_FILE
    _write_json(verdict_path, record.model_dump(mode="json"))
    return Verification(decision, record, runs, verdict_path, confirmation_runs)


def _already_held(held: LockWait | None) -> LockWait | None:
    """The lock record of a later run under the hold: only the first run waited for it."""
    if held is None:
        return None
    return replace(
        held, seconds=0.0, waited_for=(), reclaimed=(), queue_position=None, waiters_ahead=0
    )


def confirmation_selection(
    verdict: GateVerdict, run: GymRun, reference: Path, baseline: Scorecard, runs: Path
) -> tuple[list[str], list[Trajectory]] | ConfirmationSkip:
    """The cases an INCONCLUSIVE tier's confirmation re-runs and the reference trajectories
    its screen reads, or why it is not run: the candidate's run has no trajectories
    reproducing its scorecard, the gate's band has no pooled counts, the reference run's
    trajectories are not beside ``reference`` or under ``runs``, or no case qualifies."""
    if not run.trajectories or not trajectories_reproduce(run.scorecard, run.trajectories):
        return "trajectories_missing"
    if verdict.noise is None or not verdict.noise.pooled:
        return "band_not_pooled"
    reference_trajectories, _ = scorecard_trajectories(reference, baseline, runs)
    if reference_trajectories is None:
        return "reference_trajectories_missing"
    cases = confirmation_cases(verdict, reference_trajectories, run.trajectories)
    if not cases:
        return "no_cases"
    return cases, reference_trajectories


def confirm_tier(
    verdict: GateVerdict,
    baseline: Scorecard,
    reference_trajectories: Sequence[Trajectory],
    rerun: GymRun,
    cases: Sequence[str],
    repeats: int,
) -> Confirmation:
    """The confirmation of an INCONCLUSIVE ``verdict`` by the re-run of ``cases``: that run
    gated as a slice screen against the reference and the gate's band, and the tier's
    decision from it."""
    screen = gate(
        baseline,
        rerun.scorecard,
        slice=True,
        noise=verdict.noise,
        baseline_trajectories=reference_trajectories,
        candidate_trajectories=rerun.trajectories,
    )
    decision, basis = confirmation_decision(verdict, screen)
    event(
        "gym.confirmed",
        run_id=rerun.scorecard.run.run_id,
        cases=len(cases),
        decision=decision.value,
        basis=basis,
    )
    return Confirmation(
        cases=list(cases),
        repeats=repeats,
        run_dir=str(rerun.run_dir),
        scorecard=str(rerun.run_dir / SCORECARD_FILE),
        screen=screen,
        decision=decision,
        basis=basis,
    )


# Stored runs


def _started(run_dir: Path, record: Mapping[str, Any], run_id: str) -> str:
    """When the run started: run.json, else the run id's stamp, else the scorecard's mtime."""
    if isinstance(record.get("started_at"), str):
        return record["started_at"]
    stamp = _RUN_STAMP.search(run_id)
    moment = (
        datetime.strptime(stamp.group(1), "%Y%m%dt%H%M%S").replace(tzinfo=UTC)
        if stamp
        else datetime.fromtimestamp((run_dir / SCORECARD_FILE).stat().st_mtime, UTC)
    )
    return moment.isoformat(timespec="seconds")


def _run_tier(record: Mapping[str, Any], run_id: str) -> str | None:
    if isinstance(record.get("tier"), str):
        return record["tier"]
    stamp = _RUN_STAMP.search(run_id)
    if stamp is None or not run_id.startswith("gym-"):
        return None
    return run_id[len("gym-") : stamp.start()]


def run_scorecard(path: Path) -> Path:
    """A run directory's scorecard, or the scorecard file given."""
    return path / SCORECARD_FILE if path.is_dir() else path


def scorecard_trajectories(
    path: Path, card: Scorecard, runs: Path | None
) -> tuple[list[Trajectory] | None, list[Path]]:
    """The trajectories behind the scorecard file ``path``, and every place looked.

    Beside the file first, then the run directory ``<runs>/<run id>`` its ``run`` names (a
    reference copy under ``reference/``); only trajectories that reproduce the scorecard's
    per-language cases and majority verified accuracy are used, else ``None``.
    """
    places = [path.parent / TRAJECTORIES_FILE]
    if runs is not None:
        places.append(runs / card.run.run_id / TRAJECTORIES_FILE)
    for place in places:
        if place.is_file():
            found = read_trajectories(place)
            if trajectories_reproduce(card, found):
                return found, places
    return None, places


def noise_tier(paths: Sequence[Path], cards: Sequence[Scorecard]) -> str:
    """The one tier every run names (its ``run.json``, else its run id); refused otherwise."""
    tiers = {
        _run_tier(read_run_record(path) if path.is_dir() else {}, card.run.run_id)
        for path, card in zip(paths, cards, strict=True)
    }
    tier = tiers.pop() if len(tiers) == 1 else None
    if tier is None:
        raise ValueError("the runs do not name one tier; pass --out")
    return tier


def run_summary(run_dir: Path) -> dict[str, Any]:
    """One stored run's headline figures from its scorecard and run.json."""
    card = read_scorecard(run_dir / SCORECARD_FILE)
    record = read_run_record(run_dir)
    # A scorecard written without the run's context defers to the one run.json recorded.
    run = card.run if card.run.git_commit else (_recorded_context(record) or card.run)
    known = [
        (summary.verified_accuracy, language)
        for language, summary in card.languages.items()
        if summary.verified_accuracy is not None
    ]
    worst = min(known) if known else None
    finish = record.get("git_commit_at_finish")
    return {
        "run_id": run.run_id,
        "started_at": _started(run_dir, record, run.run_id),
        "git_commit": run.git_commit,
        "git_dirty": record.get("git", {}).get("dirty"),
        "git_commit_at_finish": finish,
        "source_dirty_at_finish": record.get("source_dirty_at_finish"),
        # None when either commit is unknown (a run recorded before the finish fields).
        "commit_changed": None if not (finish and run.git_commit) else finish != run.git_commit,
        "tier": _run_tier(record, run.run_id),
        "repeats": card.repeats,
        "sliced": card.sliced,
        "objective_j": card.objective_j,
        "macro_verified_accuracy": card.macro_verified_accuracy,
        "worst_language": None if worst is None else worst[1],
        "worst_language_verified_accuracy": None if worst is None else worst[0],
        "macro_effective_tokens": card.macro_effective_tokens,
        "macro_p50_seconds": card.macro_p50_seconds,
        "capped_call_episodes": card.capped_call_episodes,
        "run_dir": str(run_dir),
    }


def list_runs(
    gym_root: Path, *, tier: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Stored runs under ``runs/`` (and directly under the root, an older layout), newest first."""
    run_dirs = {
        path.parent
        for pattern in (f"runs/*/{SCORECARD_FILE}", f"*/{SCORECARD_FILE}")
        for path in gym_root.glob(pattern)
    }
    rows = [run_summary(run_dir) for run_dir in run_dirs]
    if tier is not None:
        rows = [row for row in rows if row["tier"] == tier]
    rows.sort(key=lambda row: (row["started_at"], row["run_id"]), reverse=True)
    return rows if limit is None else rows[:limit]


# Offline views over a finished run


def dataset_for_report(report_path: Path, root: Path) -> Path:
    """The checked-in case manifest whose digest the report was scored against."""
    from corsair.evaluation.comparison import read_report

    wanted = read_report(report_path).get("dataset_digest")
    for path in sorted((root / TIER_DIR).glob("*.json")):
        try:
            if digest(Dataset.model_validate_json(path.read_bytes())) == wanted:
                return path
        except ValueError:
            continue  # An agent, intake or legacy listing, not a case manifest.
    raise ValueError(
        f"no manifest under {TIER_DIR} has the report's dataset digest; pass --dataset"
    )


def _round_calls(result: InvestigationResult, session: int, index: int) -> list[dict[str, Any]]:
    """Per-call tokens and seconds for one round, from the stored producer and audit usage."""
    calls: list[dict[str, Any]] = []
    for item in result.rounds:
        if (item.session, item.index) != (session, index):
            continue
        usages = [("producer", item.producer.usage)]
        if item.audit is not None:
            usages.append(("auditor", item.audit.usage))
        for role, usage in usages:
            calls.extend(
                {"role": role, "call": "model", **call.model_dump(mode="json")}
                for call in usage.model_calls
            )
            calls.extend(
                {"role": role, "call": "tool", **call.model_dump(mode="json")}
                for call in usage.tool_calls_detail
            )
    return calls


def _replay_repeat(
    item: Trajectory, result: InvestigationResult | None, store: ArtifactStore
) -> dict[str, Any]:
    from corsair.entrypoints.runs import explain_run

    rounds = []
    for summary in item.rounds:
        view = summary.model_dump(mode="json", exclude={"control_payload", "exploit_payload"})
        view["calls"] = (
            [] if result is None else _round_calls(result, summary.session, summary.index)
        )
        rounds.append(view)
    return {
        "run_id": item.run_id,
        "repeat": item.repeat,
        "status": item.status,
        "verdict": item.verdict,
        "execution_status": item.execution_status,
        "passed": item.passed,
        "verified": item.verified,
        "failure_stop": item.failure_stop,
        "reward": item.reward,
        "effective_tokens": item.effective_tokens,
        "agent_seconds": item.agent_seconds,
        "seconds": item.seconds,
        "usage_known": item.usage_known,
        "attempt": item.attempt,
        "retried_reason": item.retried_reason,
        "supersedes": item.supersedes,
        "superseded_by": item.superseded_by,
        "result": "present" if result is not None else "unavailable",
        "rounds": rounds,
        "statements": [] if result is None else explain_run(store, result)["statements"],
    }


def replay_case(
    run_dir: Path, case_id: str, store: ArtifactStore, *, superseded: bool = False
) -> dict[str, Any]:
    """Each repeat's round timeline, per-call usage and failure stop; never payload text.

    The scored attempt of each repeat comes first; a retried repeat names its attempt, the
    first attempt's operational reason and run id. With ``superseded`` the run's superseded
    first attempts (``superseded.jsonl``) follow, each marked with its retry's run id.
    """
    repeats = [
        item for item in read_trajectories(run_dir / TRAJECTORIES_FILE) if item.case_id == case_id
    ]
    if not repeats:
        raise ValueError(f"{case_id} has no trajectory in {run_dir}")
    if superseded and (run_dir / SUPERSEDED_FILE).is_file():
        repeats += [
            item for item in read_trajectories(run_dir / SUPERSEDED_FILE) if item.case_id == case_id
        ]
    results = load_results(store, [item.run_id for item in repeats])
    return {
        "run_dir": str(run_dir),
        "case_id": case_id,
        "repeats": [_replay_repeat(item, results.get(item.run_id), store) for item in repeats],
    }


def _cell(value: object, digits: int = 1) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _round_rows(rounds: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [
        [
            _cell(item["session"]),
            _cell(item["index"]),
            _cell(item["stop"]),
            "none" if item["payload_identity"] is None else f"`{item['payload_identity'][:12]}`",
            _cell(item["producer_abstained"]),
            f"{_cell(item['audit_decision'])} {_cell(item['audit_rule'])}",
            _cell(item["control_outcome"]),
            _cell(item["adversarial_outcome"]),
            _cell(item["sandbox_host_seconds"]),
        ]
        for item in rounds
    ]


def _call_rows(rounds: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [
        [
            f"{item['session']}.{item['index']}",
            call["role"],
            call["call"],
            _cell(call["index"]),
            call.get("name", "") if call["call"] == "tool" else "",
            _cell(call.get("input_tokens")) if call["call"] == "model" else "",
            _cell(call.get("cached_input_tokens")) if call["call"] == "model" else "",
            _cell(call.get("output_tokens")) if call["call"] == "model" else "",
            _cell(call.get("thought_tokens")) if call["call"] == "model" else "",
            _cell(call.get("result_bytes")) if call["call"] == "tool" else "",
            _cell(call["seconds"], 2),
        ]
        for item in rounds
        for call in item["calls"]
    ]


def _attempt_text(repeat: Mapping[str, Any]) -> str:
    """The attempt marker of a retried repeat's scored or superseded attempt; else nothing."""
    if repeat.get("superseded_by"):
        return f" · attempt 1, superseded by `{repeat['superseded_by']}`"
    if repeat.get("attempt") == 2:
        return (
            f" · attempt 2, retried after {repeat['retried_reason']} "
            f"(first attempt `{repeat['supersedes']}`)"
        )
    return ""


def render_replay(view: Mapping[str, Any]) -> str:
    """Code-owned Markdown: enums, counts, digests, gate names and fixed statements only."""
    lines = [f"## Replay `{view['case_id']}`", "", f"Run directory `{view['run_dir']}`.", ""]
    for repeat in view["repeats"]:
        lines.extend(
            [
                f"### Repeat {repeat['repeat']} · run `{repeat['run_id']}`{_attempt_text(repeat)}",
                "",
                f"- Verdict {_cell(repeat['verdict'])}; execution "
                f"{_cell(repeat['execution_status'])}; status {repeat['status']}; verified "
                f"{_cell(repeat['verified'])}; failure stop {_cell(repeat['failure_stop'])}",
                f"- Reward {_cell(repeat['reward'], 3)}; effective tokens "
                f"{_cell(repeat['effective_tokens'], 0)}; seconds {_cell(repeat['seconds'])} "
                f"(agent {_cell(repeat['agent_seconds'])}); usage known "
                f"{_cell(repeat['usage_known'])}; stored result {repeat['result']}",
                "",
            ]
        )
        header = ["Session", "Round", "Stop", "Payload", "Abstained", "Audit"]
        header += ["Control", "Adversarial", "Sandbox host s"]
        lines.extend(_table(header, _round_rows(repeat["rounds"])))
        calls = _call_rows(repeat["rounds"])
        if calls:
            header = ["Round", "Role", "Call", "#", "Tool", "Input", "Cached", "Output"]
            header += ["Thought", "Result bytes", "Seconds"]
            lines.extend(["", *_table(header, calls)])
        if repeat["statements"]:
            lines.append("")
            lines.extend(f"- {statement['text']}" for statement in repeat["statements"])
        lines.append("")
    return "\n".join(lines)


def build_gym_images(root: Path, settings: Settings) -> dict[str, str]:
    """Build every configured language's content-tagged image; return ``{ref: image id}``."""
    images = gym_images(root, settings)
    return ensure_images(root, {language_of(kind): ref for kind, ref in images.items()})
