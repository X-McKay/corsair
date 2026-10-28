"""Frozen v3 role scoring never treats structural scores as vulnerability accuracy."""

from pathlib import Path

from corsair.contracts.execution import ExecutionEpisode, PlanAudit
from corsair.evaluation.execution import load_role_cases, score_episode
from tests.unit.execution import plan


def test_frozen_role_cohort_hashes_and_categorical_scores():
    cases = load_role_cases(Path("evals/datasets/execution-roles.json"))
    assert len(cases) == 4
    producer = cases[0]
    output = ExecutionEpisode(
        plan=plan(
            files=[
                {
                    "path": "check.py",
                    "content": "import sys; sys.path.insert(0,'/source'); import reader",
                }
            ]
        )
    )
    assert score_episode(output, producer["oracle"])["pass"]
    assert not score_episode(ExecutionEpisode(error="OUTPUT_INVALID"), producer["oracle"])["pass"]
    for case in cases[1:]:
        audit = PlanAudit.model_validate(case["oracle"]["audit"])
        assert score_episode(ExecutionEpisode(audit=audit), case["oracle"])["pass"]
        assert not score_episode(
            ExecutionEpisode(audit=PlanAudit(decision="accepted")),
            {"role": "auditor", "audit": {"decision": "rejected", "reasons": ["UNRELATED_TEST"]}},
        )["pass"]
