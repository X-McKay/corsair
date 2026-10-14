"""Run recorder: one directory per run holding every stage's input and output, usage and the verdict.

Layout of ``<root>/<run_id>/``:

- ``run.json``: run id, mode and start time; ``case.json``: the Case as investigated.
- ``stages/<step>.json``: one file per stage call with its input, output, wall time and any error.
- ``agents/<step>.messages.json``: the native PydanticAI message history of an agent call, when captured.
- ``usage.json``: one ``AgentUsage`` per agent call, in order; ``timings.json``: per-stage wall time, in order.
- ``grounding.json``: the advisory grounding brief, when Ground ran. Nothing downstream reads it.
- ``verdict.json`` and ``summary.json`` (label, rule id, terminal reason and totals; unknown totals are null).

State lives in the files, not in the object, so a Temporal activity on any worker sharing the filesystem can reopen
the run directory and append to it. Steps run one at a time per run, so read-modify-write appends do not race.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import AgentUsage, Case, Verdict

DEFAULT_ROOT = Path(".runs/v2/runs")
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

    def begin(self, case: Case, *, mode: str) -> None:
        """Idempotent: a retried begin keeps the first start time."""
        run = self._read("run.json", None) or {"run_id": self.run_id, "mode": mode, "started_at": time.time()}
        self._write("run.json", run)
        self._write("case.json", case)

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
        usage = self.usage()
        started = self._read("run.json", {}).get("started_at")
        inputs, outputs = _total(u.input_tokens for u in usage), _total(u.output_tokens for u in usage)
        summary = {
            "run_id": self.run_id,
            "case_id": verdict.case_id,
            "label": verdict.label.value,
            "rule_id": verdict.rule_id,
            "terminal_reason": verdict.terminal_reason.value,
            "finding": verdict.finding,
            "fix": verdict.fix,
            "totals": {
                "agent_calls": len(usage),
                "requests": _total(u.requests for u in usage),
                "input_tokens": inputs,
                "output_tokens": outputs,
                "tokens": None if inputs is None or outputs is None else inputs + outputs,
                "tool_calls": _total(u.tool_calls for u in usage),
                "agent_wall_s": _total_float(u.wall_s for u in usage),
                "wall_s": None if started is None else round(time.time() - started, 3),
            },
        }
        self._write("summary.json", summary)
        return summary


def _total_float(values: Iterable[float | None]) -> float | None:
    total = 0.0
    for value in values:
        if value is None:
            return None
        total += value
    return round(total, 3)
