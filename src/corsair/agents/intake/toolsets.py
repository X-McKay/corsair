"""Concrete intake source, inventory comparison and native procedural tools."""

from collections.abc import Callable
from typing import Any

from google.adk.tools.skill_toolset import SkillDiscoveryMode, SkillToolset

from corsair.agents.resources import load_agent_spec, load_runtime_skills
from corsair.contracts.intake import ImageInventory
from corsair.ports.intake import InspectionReader

from .tools.compare_images import create_compare_images
from .tools.list_files import create_list_files
from .tools.read_file import create_read_file


def build_intake_toolset(
    reader: InspectionReader, inventory: ImageInventory, byte_limit: int
) -> list[Callable[..., Any] | SkillToolset]:
    spec = load_agent_spec("intake")
    tools = [
        create_read_file(reader),
        create_list_files(reader),
        create_compare_images(inventory, byte_limit),
    ]
    if [getattr(tool, "__name__", None) for tool in tools] != [
        *spec.source_tools,
        *spec.mechanical_tools,
    ]:
        raise ValueError("intake function tools do not match approved metadata")
    return [
        *tools,
        SkillToolset(
            skills=load_runtime_skills("intake"),
            discovery_mode=SkillDiscoveryMode.EAGER,
            tool_filter=list(spec.loader_tools),
        ),
    ]


class TrackedInspection:
    """Record actual source reads without attributing trusted preload to the model."""

    def __init__(self, reader: InspectionReader):
        self.reader = reader
        self.paths: set[str] = set()

    def read(self, operation: str, relative: str = "") -> dict:
        result = self.reader.read(operation, relative)
        if (
            operation == "read"
            and isinstance(result.get("content"), str)
            and not result.get("truncated")
        ):
            self.paths.add(relative)
        return result
