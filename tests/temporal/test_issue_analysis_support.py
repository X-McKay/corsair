"""Host-owned fixture models/oracles; imported through native workflow pass-through."""

import json
from datetime import timedelta
from functools import cache
from pathlib import Path

from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio.common import RetryPolicy

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent
from corsair.workflows.issue_analysis import IssueAnalysisBudget
from evals.issue_analysis.evaluate import scripted_model

FIXTURES = Path(__file__).resolve().parents[2] / "evals/issue_analysis"
ORACLES = json.loads((FIXTURES / "oracles.json").read_text())["cases"]
EXPECTED = {key: IssueAnalysis.model_validate(value) for key, value in ORACLES.items()}
MODELS = {key: scripted_model(value) for key, value in EXPECTED.items()}
MODELS["unread"] = TestModel(call_tools=[], custom_output_args=ORACLES["path_traversal"])
MODELS["refused_path"] = scripted_model(EXPECTED["path_traversal"], path="../credentials")
ACTIVITY_CONFIG = {
    "start_to_close_timeout": timedelta(seconds=10),
    "schedule_to_close_timeout": timedelta(seconds=30),
    "retry_policy": RetryPolicy(maximum_attempts=1),
}
# Operator ceiling for the fixture workflow; requests use it unless a case narrows it.
BUDGET = IssueAnalysisBudget(request_limit=3, tool_calls_limit=1, total_tokens_limit=5000)


@cache
def fixture_agent():
    """One shared agent; built on first use rather than when this module is imported."""
    durability = TemporalDurability(models=MODELS, activity_config=ACTIVITY_CONFIG)
    return create_issue_analysis_agent(TestModel(call_tools=[]), output_retries=0, durability=durability)


def admitted(workflow_class):
    """Startup check: every admitted model key must be registered with the agent's durability."""
    unregistered = set(workflow_class.model_keys) - set(MODELS)
    if unregistered:
        raise AssertionError(f"Admitted model keys lack durable registration: {sorted(unregistered)}")
    return workflow_class


def inputs(key="path_traversal"):
    return IssueAnalysisInput.model_validate_json((FIXTURES / "fixtures" / f"{key}.json").read_text())
