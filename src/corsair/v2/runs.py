"""Compare recorded runs without confusing absent records with unknown telemetry.

Legacy records remain readable. A real record needs run.json or summary.json;
missing optional fields stay None. An unfinished receipt does not prove active work.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .record import _agents

COLUMNS = ("run", "case", "mode", "label", "rule", "reason", "wall_s", "tokens", "requests", "tool_calls",
           "retries", "models", "prompt_versions", "state")
SHORT = {"grounding": "gnd", "investigator": "inv", "builder": "bld", "control_prober": "ctl",
         "exploit_prober": "xpl", "reviewer": "rev"}


def _read(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"invalid JSON record: {path}") from exc


def details(run_dir: Path) -> dict[str, Any]:
    """Load a real run, with per-agent aggregates but no transcripts or raw tool content."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ValueError(f"run directory does not exist: {run_dir}")
    if not any((run_dir / name).is_file() for name in ("run.json", "summary.json")):
        raise ValueError(f"no run.json or summary.json in: {run_dir}")
    summary, run = _read(run_dir / "summary.json"), _read(run_dir / "run.json")
    if not isinstance(summary, dict) or not isinstance(run, dict):
        raise ValueError(f"run.json and summary.json must be JSON objects: {run_dir}")
    agents = summary.get("agents")
    if agents is None:
        usage = _read(run_dir / "usage.json")
        agents = _agents(usage) if isinstance(usage, list) else {}
    totals = summary.get("totals") or {}
    if not isinstance(agents, dict) or not isinstance(totals, dict):
        raise ValueError(f"agents and totals must be JSON objects: {run_dir}")
    if not all(isinstance(agent, dict) for agent in agents.values()):
        raise ValueError(f"agent aggregates must be JSON objects: {run_dir}")
    state = "completed" if summary.get("label") else run.get("state")
    if state not in ("completed", "cancelled", "interrupted"):
        state = "incomplete"
    return {"run": run, "summary": summary, "agents": agents, "totals": totals, "state": state}


def row(run_dir: Path) -> dict[str, Any]:
    """Comparable values plus existing agent/totals detail; presentation never turns None into zero."""
    data = details(run_dir)
    summary, run, agents, totals = (data[name] for name in ("summary", "run", "agents", "totals"))
    return {
        "run": summary.get("run_id") or run.get("run_id") or Path(run_dir).name,
        "case": summary.get("case_id") or run.get("case_id"),
        "mode": summary.get("mode") or run.get("mode"),
        "label": summary.get("label"),
        "rule": summary.get("rule_id"),
        "reason": summary.get("terminal_reason"),
        "wall_s": totals.get("wall_s"),
        "tokens": totals.get("tokens"),
        "requests": totals.get("requests"),
        "tool_calls": totals.get("tool_calls"),
        "retries": totals.get("retries"),
        "models": ",".join(summary.get("models") or sorted({m for a in agents.values() for m in a.get("models", [])}))
        or None,
        "prompt_versions": " ".join(f"{SHORT.get(name, name)}={'|'.join(a['prompt_versions'])}"
                                    for name, a in agents.items() if a.get("prompt_versions")) or None,
        "state": data["state"], "agents": agents, "totals": totals,
    }


def table(run_dirs: Iterable[Path]) -> str:
    """A header and one aligned line per run; retained deterministic non-TTY text format."""
    rows = [[_cell(r[c]) for c in COLUMNS] for r in map(row, run_dirs)]
    lines = [list(COLUMNS), *rows]
    widths = [max(len(line[i]) for line in lines) for i in range(len(COLUMNS) - 1)]
    return "\n".join("  ".join([*(cell.ljust(w) for cell, w in zip(line, widths)), line[-1]]).rstrip()
                     for line in lines)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return "".join(char if ord(char) >= 32 and not 127 <= ord(char) <= 159 else f"\\x{ord(char):02x}"
                   for char in str(value))


__all__ = ["COLUMNS", "details", "row", "table"]
