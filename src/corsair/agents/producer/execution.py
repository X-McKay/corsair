"""Native recipe-free producer; tools only inspect sandboxed source."""

import asyncio
import json
from importlib.resources import files

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

from corsair.contracts.execution import TestPlan
from corsair.ports.intake import InspectionReader


def build_execution_producer(model: str | BaseLlm, reader: InspectionReader) -> LlmAgent:
    metadata = json.loads(files("corsair.agents.producer").joinpath("execution.json").read_text())
    if metadata != {
        "name": "producer",
        "contract_version": "corsair.execution-agent/3",
        "schema_ref": "corsair.contracts.TestPlan",
        "tools": ["read_file", "list_files"],
        "llm_call_limit": 4,
        "instruction_resource": "corsair.agents.producer.instructions:execution.md",
    }:
        raise ValueError("unreviewed recipe-free producer metadata")

    async def read_file(path: str) -> dict:
        """Read an admitted relative source path, never execute it."""
        return await asyncio.to_thread(reader.read, "read", path)

    async def list_files() -> dict:
        """List bounded admitted repository paths."""
        return await asyncio.to_thread(reader.read, "list")

    return LlmAgent(
        name="producer",
        model=model,
        instruction=files("corsair.agents.producer.instructions")
        .joinpath("execution.md")
        .read_text(),
        tools=[read_file, list_files],
        output_schema=TestPlan,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
