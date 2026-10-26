"""Grouped reward export for later training: rewards, advantages, proposals and digests.

Each record carries the per-round payload proposals and audit decisions plus the request and
identity digests from which ``corsair agent preview`` rebuilds the exact model inputs. Packets,
hypotheses, audit reasons and model reasoning are never written.
"""

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from corsair.contracts import RoundSummary, Trajectory
from corsair.evaluation.gym.scoring import TRAJECTORIES_FILE, read_trajectories

EXPORT_SCHEMA = "corsair.gym-export/1"
MIN_GROUP = 2


def _round(item: RoundSummary) -> dict[str, Any]:
    return {
        "session": item.session,
        "index": item.index,
        "payload_identity": item.payload_identity,
        "control_payload": item.control_payload,
        "exploit_payload": item.exploit_payload,
        "producer_abstained": item.producer_abstained,
        "audit_decision": None if item.audit_decision is None else item.audit_decision.value,
        "audit_rule": None if item.audit_rule is None else item.audit_rule.value,
    }


def _record(item: Trajectory, advantage: float, size: int) -> dict[str, Any]:
    return {
        "schema_version": EXPORT_SCHEMA,
        "case_id": item.case_id,
        "kind": item.kind,
        "language": item.language,
        "run_id": item.run_id,
        "repeat": item.repeat,
        "group_size": size,
        "reward": item.reward,
        "advantage": advantage,
        "rounds": [_round(round_item) for round_item in item.rounds],
        "request_digest": item.identity.get("request"),
        "identity": dict(sorted(item.identity.items())),
        "models": dict(sorted(item.models.items())),
        "git_commit": item.git_commit,
    }


def group_records(trajectories: Iterable[Trajectory]) -> list[dict[str, Any]]:
    """Group by case; skip groups smaller than two or with zero reward variance."""
    groups: dict[str, list[Trajectory]] = defaultdict(list)
    for item in trajectories:
        groups[item.case_id].append(item)
    records = []
    for case_id in sorted(groups):
        members = groups[case_id]
        rewards = [item.reward for item in members]
        if len(members) < MIN_GROUP:
            continue
        spread = pstdev(rewards)
        if spread == 0:
            continue
        centre = mean(rewards)
        records.extend(
            _record(item, (item.reward - centre) / spread, len(members)) for item in members
        )
    return records


def export_groups(run_dirs: Sequence[Path], out: Path) -> int:
    """Write grouped JSONL from each run directory's trajectories; return the record count."""
    trajectories = [
        item for run_dir in run_dirs for item in read_trajectories(run_dir / TRAJECTORIES_FILE)
    ]
    records = group_records(trajectories)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    return len(records)
