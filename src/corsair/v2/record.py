"""Run recorder: one directory per run holding every stage's input and output, usage and the verdict.

Every file carries the versioned run-record schema ``corsair-v2-run/1`` (``SCHEMA``), documented field by field in
``RUN_RECORD.md``. Layout of ``<root>/<run_id>/``:

- ``run.json``: what produced the run (schema, ids, mode, host, UTC start and finish, code commit and dirty flag,
  provider-config and matrix digests, the selected runtime row and its image id, the revision trees and the
  environment images used); ``case.json``: the Case as investigated.
- ``stages/<step>.json``: one file per stage call with its input, output, wall time and any error.
- ``agents/<step>.messages.json``: the native PydanticAI message history of an agent call, when captured.
- ``usage.json``: one ``AgentUsage`` per agent call (with its step), in order; ``timings.json``: per-stage wall time.
- ``grounding.json``: the advisory grounding brief, when Ground ran. Nothing downstream reads it.
- ``verdict.json`` and ``summary.json`` (outcome, per-author review results, per-agent aggregates and totals;
  unknown values are null).

State lives in the files, not in the object, so a Temporal activity on any worker sharing the filesystem can reopen
the run directory and append to it. Steps run one at a time per run, so read-modify-write appends do not race.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import AgentUsage, Case, Environment, Revision, Runtime, Verdict

SCHEMA = "corsair-v2-run/1"
DEFAULT_ROOT = Path(".runs/v2/runs")
CODE_ROOT = Path(__file__).resolve().parent
_STEP = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def to_json(value: Any) -> Any:
    """Plain JSON for contracts, paths, enums and containers; anything else becomes its repr, never dropped."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _total(values: Iterable[int | None]) -> int | None:
    """Sum of known values; one unknown makes the total unknown (None), never a silent zero."""
    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total


class RunRecorder:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        (self.run_dir / "stages").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "agents").mkdir(exist_ok=True)

    @classmethod
    def create(cls, root: Path | None = None, run_id: str | None = None) -> RunRecorder:
        root = Path(root) if root is not None else Path.cwd() / DEFAULT_ROOT
        run_id = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        run_dir = root / run_id
        if run_dir.exists():
            raise FileExistsError(f"run directory already exists: {run_dir}")
        return cls(run_dir)

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    def _write(self, name: str, value: Any) -> None:
        path = self.run_dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(to_json(value), indent=2, sort_keys=False) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _read(self, name: str, default: Any) -> Any:
        path = self.run_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def _append(self, name: str, item: Any) -> None:
        self._write(name, [*self._read(name, []), to_json(item)])

    def _update(self, name: str, **fields: Any) -> None:
        self._write(name, {**self._read(name, {}), **fields})

    def begin(self, case: Case, *, mode: str, provider_config: Path | None = None, matrix: Path | None = None
              ) -> None:
        """Write run.json. Idempotent: a retried begin keeps the first record and its start time."""
        if self._read("run.json", None) is None:
            commit, dirty = _git_state()
            self._write("run.json", {
                "schema": SCHEMA, "run_id": self.run_id, "case_id": case.case_id, "mode": mode,
                "hostname": socket.gethostname(), "started_at": _now(), "finished_at": None,
                "git_commit": commit, "git_dirty": dirty,
                "provider_config_sha256": _file_sha256(provider_config),
                "matrix_sha256": _file_sha256(matrix),
                "runtime_row": None, "runtime_image": None, "runtime_image_id": None,
                "revision": _revision(case.revision), "fixed_revision": _revision(case.fixed_revision),
                "environments": {},
            })
        self._write("case.json", case)

    def runtime(self, runtime: Runtime, image_id: str | None) -> None:
        """The selected matrix row, its image reference and the local image id it resolved to (None: unknown)."""
        self._update("run.json", runtime_row=runtime.row_id, runtime_image=runtime.image, runtime_image_id=image_id)

    def environment(self, revision: str, environment: Environment, image_id: str | None) -> None:
        """A replayed environment probes may run on, keyed by revision; the last replay of a revision wins."""
        environments = self._read("run.json", {}).get("environments") or {}
        environments[revision] = {"image": environment.image, "image_id": image_id,
                                  "tree_sha256": environment.tree_sha256, "recipe_sha256": environment.recipe_sha256,
                                  "runtime_row": environment.runtime_row}
        self._update("run.json", environments=environments)

    def stage(self, step: str, *, inputs: Mapping[str, Any], output: Any, wall_s: float | None,
              error: str | None = None) -> None:
        if not _STEP.match(step):
            raise ValueError(f"invalid step name: {step!r}")
        self._write(f"stages/{step}.json",
                    {"step": step, "input": inputs, "output": output, "wall_s": wall_s, "error": error})
        self._append("timings.json", {"step": step, "wall_s": wall_s, "error": error is not None})

    def agent(self, step: str, usage: AgentUsage, messages_json: bytes | None) -> None:
        self._append("usage.json", {"step": step, **usage.model_dump(mode="json")})
        if messages_json is not None:
            (self.run_dir / "agents" / f"{step}.messages.json").write_bytes(messages_json)

    def grounding(self, brief: Any) -> None:
        self._write("grounding.json", brief)

    def usage(self) -> list[AgentUsage]:
        return [AgentUsage.model_validate({k: v for k, v in row.items() if k != "step"})
                for row in self._read("usage.json", [])]

    def finish(self, verdict: Verdict) -> dict[str, Any]:
        self._write("verdict.json", verdict)
        finished = _now()
        self._update("run.json", finished_at=finished)
        run = self._read("run.json", {})
        rows = self._read("usage.json", [])
        usage = self.usage()
        inputs, outputs = _total(u.input_tokens for u in usage), _total(u.output_tokens for u in usage)
        summary = {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "case_id": verdict.case_id,
            "mode": run.get("mode"),
            "label": verdict.label.value,
            "rule_id": verdict.rule_id,
            "terminal_reason": verdict.terminal_reason.value,
            "finding": verdict.finding,
            "fix": verdict.fix,
            "outcome": _outcome(verdict),
            "review": _review(verdict),
            "models": sorted({u.model for u in usage if u.model is not None}),
            "agents": _agents(rows),
            "totals": {
                "agent_calls": len(usage),
                "requests": _total(u.requests for u in usage),
                "input_tokens": inputs,
                "output_tokens": outputs,
                "tokens": None if inputs is None or outputs is None else inputs + outputs,
                "tool_calls": _total(u.tool_calls for u in usage),
                "retries": _total(u.retries for u in usage),
                "agent_wall_s": _total_float(u.wall_s for u in usage),
                "wall_s": _elapsed(run.get("started_at"), finished),
            },
        }
        self._write("summary.json", summary)
        return summary


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _elapsed(started: Any, finished: str) -> float | None:
    if not isinstance(started, str):
        return None
    try:
        begin = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end - begin).total_seconds(), 3)


def _file_sha256(path: Path | None) -> str | None:
    if path is None or not Path(path).is_file():
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _revision(revision: Revision | None) -> dict[str, Any] | None:
    return None if revision is None else {"tree_sha256": revision.tree_sha256, "commit": revision.commit}


def _git_state(root: Path = CODE_ROOT) -> tuple[str | None, bool | None]:
    """The commit of the checkout this code runs from and whether it has changes (untracked files included)."""
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=30, check=False)
        if head.returncode != 0:
            return None, None
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True,
                                timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    return head.stdout.strip() or None, (bool(status.stdout.strip()) if status.returncode == 0 else None)


def _outcome(verdict: Verdict) -> dict[str, Any]:
    """The decision and the per-probe evidence it read, by revision then role."""
    probes: dict[str, dict[str, Any]] = {}
    for run in verdict.runs:
        probes.setdefault(run.revision, {})[run.role] = {
            "outcome": run.outcome.value, "facts": run.facts.model_dump(mode="json"),
            "duration_s": run.duration_s, "patch_sha256": run.patch_sha256, "image_digest": run.image_digest,
            "tree_sha256": run.tree_sha256, "cleanup_confirmed": run.cleanup_confirmed}
    return {"label": verdict.label.value, "rule_id": verdict.rule_id,
            "terminal_reason": verdict.terminal_reason.value, "finding": verdict.finding, "fix": verdict.fix,
            "fix_reason": verdict.fix_reason.value if verdict.fix_reason is not None else None, "probes": probes}


def _agents(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-agent aggregates over usage.json rows, in first-call order; unknown values make a sum unknown."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["agent"], []).append(row)
    out = {}
    for agent, calls in grouped.items():
        statuses: dict[str, int] = {}
        for call in calls:
            statuses[call.get("status", "ok")] = statuses.get(call.get("status", "ok"), 0) + 1
        out[agent] = {
            "calls": len(calls),
            "steps": [call.get("step") for call in calls],
            "models": sorted({call["model"] for call in calls if call.get("model")}),
            "prompt_versions": sorted({call["prompt_version"] for call in calls if call.get("prompt_version")}),
            "requests": _total(call.get("requests") for call in calls),
            "input_tokens": _total(call.get("input_tokens") for call in calls),
            "output_tokens": _total(call.get("output_tokens") for call in calls),
            "tool_calls": _total(call.get("tool_calls") for call in calls),
            "retries": _total(call.get("retries") for call in calls),
            "wall_s": _total_float(call.get("wall_s") for call in calls),
            "statuses": statuses,
        }
    return out


def _review(verdict: Verdict) -> dict[str, Any]:
    """Per-author review results for evals: first-time pass, revisions used and recovery (invalid at the first
    review, valid on the final one). Unknown stays None."""
    final = next((v for v in verdict.validity if v.revision == "vulnerable"), None)
    authors = {}
    for role in ("control", "exploit"):
        first = verdict.first_review_valid.get(role)
        last = None if final is None else getattr(final, role).valid
        authors[role] = {"first_review_valid": first, "revisions_used": verdict.revisions.get(role, 0),
                         "final_valid": last,
                         "recovered": None if first is None else (first is False and last is True)}
    return {"rounds": verdict.review_rounds, "authors": authors}


def _total_float(values: Iterable[float | None]) -> float | None:
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += value
    return round(total, 3)
