"""Gym export: grouped advantages, skipped groups, and no packets or reasoning."""

import json

import pytest

from corsair.contracts import AuditDecision, AuditRule, RoundSummary, Trajectory
from corsair.evaluation.gym.export import export_groups, group_records
from corsair.evaluation.gym.scoring import TRAJECTORIES_FILE, write_trajectories


def _trajectory(case: str, repeat: int, reward: float) -> Trajectory:
    return Trajectory(
        run_id=f"run-{case}-{repeat}",
        case_id=case,
        repeat=repeat,
        kind="python.k/1",
        language="python",
        status="pass",
        passed=True,
        verified=True,
        false_label=False,
        rounds=[
            RoundSummary(
                session=1,
                index=1,
                payload_identity="a" * 64,
                control_payload="ok.txt",
                exploit_payload="../secret",
                audit_decision=AuditDecision.ACCEPT,
                audit_rule=AuditRule.ALL,
            )
        ],
        usage_known=False,
        reward_verdict=reward,
        reward=reward,
        identity={"config": "c" * 64, "request": "r" * 64},
    )


def test_groups_get_normalised_advantages_and_trivial_groups_are_skipped():
    trajectories = [
        _trajectory("varied", 0, 1.0),
        _trajectory("varied", 1, 0.0),
        _trajectory("varied", 2, -1.0),
        _trajectory("constant", 0, 1.0),
        _trajectory("constant", 1, 1.0),
        _trajectory("single", 0, 0.5),
    ]
    records = group_records(trajectories)
    assert {record["case_id"] for record in records} == {"varied"}
    assert [record["advantage"] for record in records] == pytest.approx(
        [1.224744871, 0.0, -1.224744871]
    )
    assert sum(record["advantage"] for record in records) == pytest.approx(0.0)
    first = records[0]
    assert first["request_digest"] == "r" * 64
    assert first["rounds"][0]["exploit_payload"] == "../secret"
    assert first["rounds"][0]["audit_decision"] == "ACCEPT"
    assert first["group_size"] == 3


def test_export_groups_reads_trajectories_across_runs(tmp_path):
    first, second = tmp_path / "run-1", tmp_path / "run-2"
    write_trajectories(first / TRAJECTORIES_FILE, [_trajectory("case", 0, 1.0)])
    write_trajectories(second / TRAJECTORIES_FILE, [_trajectory("case", 0, 0.0)])
    out = tmp_path / "export" / "groups.jsonl"
    assert export_groups([first, second], out) == 2
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert [line["reward"] for line in lines] == [1.0, 0.0]
    text = out.read_text()
    for forbidden in ("hypothesis", "reason", "packet", "thought"):
        assert forbidden not in text
