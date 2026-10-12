"""Host-owned fixture models/oracles; imported through native workflow pass-through."""

import json
from datetime import timedelta
from pathlib import Path

from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio.common import RetryPolicy

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput, create_issue_analysis_agent
from evals.issue_analysis.evaluate import scripted_model

FIXTURES = Path(__file__).resolve().parents[2] / "evals/issue_analysis"
ORACLES = json.loads((FIXTURES / "oracles.json").read_text())["cases"]
EXPECTED = {key: IssueAnalysis.model_validate(value) for key, value in ORACLES.items()}
MODELS = {key: scripted_model(value) for key, value in EXPECTED.items()}
MODELS["unread"] = TestModel(call_tools=[], custom_output_args=ORACLES["path_traversal"])
MODELS["refused_path"] = scripted_model(EXPECTED["path_traversal"], path="../credentials")
DURABILITY = TemporalDurability(models=MODELS, activity_config={
    "start_to_close_timeout": timedelta(seconds=10),
    "schedule_to_close_timeout": timedelta(seconds=30),
    "retry_policy": RetryPolicy(maximum_attempts=1),
})
AGENT = create_issue_analysis_agent(TestModel(call_tools=[]), output_retries=0, durability=DURABILITY)


def inputs(key="path_traversal"):
    return IssueAnalysisInput.model_validate_json((FIXTURES / "fixtures" / f"{key}.json").read_text())
