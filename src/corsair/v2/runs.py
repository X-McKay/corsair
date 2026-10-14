"""Compare recorded runs: one line per run from its ``summary.json`` and ``run.json`` (``RUN_RECORD.md``).

    corsair-v2 runs compare <run_dir> [<run_dir> ...]

Columns: run id, case, mode, label, rule, terminal reason, wall seconds, tokens, requests, tool calls, retries,
models, and each agent's prompt version(s). Unknown values print as ``-``. A run recorded before the schema existed
(no ``schema`` field) still prints; its per-agent prompt versions come from ``usage.json`` when present.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .record import _agents

COLUMNS = ("run", "case", "mode", "label", "rule", "reason", "wall_s", "tokens", "requests", "tool_calls",
           "retries", "models", "prompt_versions")
SHORT = {"grounding": "gnd", "investigator": "inv", "builder": "bld", "control_prober": "ctl",
         "exploit_prober": "xpl", "reviewer": "rev"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def row(run_dir: Path) -> dict[str, Any]:
    """One run's comparable values; a missing file or field is None."""
    run_dir = Path(run_dir)
    summary, run = _read(run_dir / "summary.json"), _read(run_dir / "run.json")
    agents = summary.get("agents")
    if agents is None:
        usage = _read(run_dir / "usage.json")
        agents = _agents(usage) if isinstance(usage, list) else {}
    totals = summary.get("totals") or {}
    return {
        "run": summary.get("run_id") or run.get("run_id") or run_dir.name,
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
    }


def table(run_dirs: Iterable[Path]) -> str:
    """A header and one aligned line per run; the last column is left unpadded."""
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
    return str(value)


__all__ = ["COLUMNS", "row", "table"]
