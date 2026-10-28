"""Fresh outcome-blind semantic review of an arbitrary generated test plan."""

import json
from importlib.resources import files

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

from corsair.contracts.execution import PlanAudit


def build_execution_auditor(model: str | BaseLlm) -> LlmAgent:
    metadata = json.loads(files("corsair.agents.auditor").joinpath("execution.json").read_text())
    if metadata != {
        "name": "auditor",
        "contract_version": "corsair.execution-agent/3",
        "schema_ref": "corsair.contracts.PlanAudit",
        "tools": [],
        "llm_call_limit": 4,
        "instruction_resource": "corsair.agents.auditor.instructions:execution.md",
    }:
        raise ValueError("unreviewed recipe-free auditor metadata")
    return LlmAgent(
        name="auditor",
        model=model,
        instruction=files("corsair.agents.auditor.instructions")
        .joinpath("execution.md")
        .read_text(),
        tools=[],
        output_schema=PlanAudit,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
