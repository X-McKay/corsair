"""One native ADK intake episode, reusing the main runner and provider boundary."""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import ValidationError

from corsair.adapters.inference.adk import _EpisodeAccounting, _run_native_episode
from corsair.adapters.inference.models import model_for_role
from corsair.agents.resources import load_agent_spec
from corsair.contracts.intake_agent import IntakeAgentOutput, PreparedIntake
from corsair.observability.logging import event
from corsair.policies.time_bounds import episode_bounds
from corsair.ports.intake import InspectionReader
from corsair.settings import Settings


@dataclass
class IntakeAccounting(_EpisodeAccounting):
    explicit_tool_object_types: bool = False
    max_loader_calls: int = 0
    loader_tool_names: frozenset[str] = frozenset()
    allowed_skill_names: frozenset[str] = frozenset()
    loader_calls: int = 0
    loader_limit_exhausted: bool = False
    tool_counts: dict[str, int] = field(default_factory=dict)
    completion_errors: dict[str, int] = field(default_factory=dict)
    skills_loaded: list[str] = field(default_factory=list)

    async def before_model(
        self, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        denied = await super().before_model(callback_context, llm_request)
        if denied is not None or not self.explicit_tool_object_types or llm_request.config is None:
            return denied
        # vLLM's Qwen parser reads a parameter's type without following $ref.
        # Keep ADK's generated schema and canonical validation; expose only the
        # existing referenced object type, before dispatch, without touching output.
        for tool in llm_request.config.tools or []:
            if not isinstance(tool, types.Tool):
                continue
            for declaration in tool.function_declarations or []:
                schema = declaration.parameters_json_schema
                if declaration.name != "set_model_response" or not isinstance(schema, dict):
                    continue
                issue = schema.get("properties", {}).get("issue", {})
                definition = schema.get("$defs", {}).get("Issue", {})
                if issue.get("$ref") == "#/$defs/Issue" and definition.get("type") == "object":
                    issue["type"] = "object"
        return None

    async def before_tool(self, tool, args, tool_context):
        if tool.name in self.loader_tool_names and self.loader_calls >= self.max_loader_calls:
            self.loader_limit_exhausted = True
            tool_context._invocation_context.end_invocation = True
            return {"error": "runtime skill loader budget exhausted"}
        denied = await super().before_tool(tool, args, tool_context)
        if denied is not None:
            return denied
        if tool.name in {"read_file", "list_files", "compare_images", "set_model_response"}:
            self.tool_counts[tool.name] = self.tool_counts.get(tool.name, 0) + 1
        if tool.name in self.loader_tool_names:
            self.loader_calls += 1
        return None

    async def after_tool(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
        tool_response: dict[str, Any],
    ) -> None:
        """Record only an ADK-confirmed successful load of an admitted skill."""

        del args, tool_context
        if tool.name == "set_model_response" and isinstance(tool_response, dict):
            error = tool_response.get("error")
            if isinstance(error, str):
                fields = {
                    "issue",
                    "scope",
                    "surface",
                    "language",
                    "execution_mode",
                    "requirements",
                    "suggested_image",
                    "reason_codes",
                    "locations",
                }
                for name, kind in re.findall(
                    r"\n([A-Za-z_][A-Za-z_0-9.]*)\n[^\n]*\[type=([a-z_]+)", error
                ):
                    field_name = name.split(".")[0]
                    if field_name in fields:
                        key = f"{kind}:{field_name}"
                        if len(self.completion_errors) < 32 or key in self.completion_errors:
                            self.completion_errors[key] = self.completion_errors.get(key, 0) + 1
        if tool.name != "load_skill" or not isinstance(tool_response, dict):
            return None
        skill_name = tool_response.get("skill_name")
        if (
            tool_response.get("error") is None
            and isinstance(skill_name, str)
            and skill_name in self.allowed_skill_names
            and skill_name not in self.skills_loaded
        ):
            self.skills_loaded.append(skill_name)
            event("agent.skill_loaded", role=self.role, skill_name=skill_name)
        return None

    def usage(self, seconds):
        return super().usage(seconds).model_copy(update={"skills_loaded": self.skills_loaded})


async def run_intake(
    prepared: PreparedIntake,
    settings: Settings,
    reader: InspectionReader,
    model_override: str | BaseLlm | None = None,
) -> IntakeAgentOutput:
    """One bounded native intake episode, with inventory-constrained validation."""
    from corsair.agents.intake.factory import build_intake
    from corsair.agents.intake.toolsets import TrackedInspection
    from corsair.contracts.intake_agent import IntakeAgentOutput, IntakeProposal, Issue
    from corsair.policies.intake_agent import validate_proposal

    if (
        model_override is None
        and settings.models.connector == "litellm"
        and settings.models.intake.startswith("openai/")
    ):
        # Preserve main's known tool/schema route restriction for this tool-using role.
        return IntakeAgentOutput(error_code="MODEL_CONFIGURATION_UNSUPPORTED")
    started = time.perf_counter()
    budget = prepared.request.budget
    spec = load_agent_spec("intake")
    llm_limit = min(budget.episode_llm_calls, budget.max_llm_calls, 4)
    accounting = IntakeAccounting(
        explicit_tool_object_types=(
            settings.models.connector == "litellm"
            and settings.models.intake.startswith("hosted_vllm/")
        ),
        max_llm_calls=llm_limit,
        max_output_tokens=budget.max_output_tokens,
        max_tool_calls=budget.max_tool_calls,
        role="intake",
        max_loader_calls=spec.loader_call_limit,
        loader_tool_names=frozenset(spec.loader_tools),
        allowed_skill_names=frozenset(spec.runtime_skills),
        skills_preloaded=list(spec.runtime_skills),
    )
    canonical = None
    with suppress(ValidationError):
        canonical = Issue.model_validate(prepared.payload)
    if budget.max_tool_calls < 3:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID", output_failure="TOOL_BUDGET_EXHAUSTED"
        )
    tracked = TrackedInspection(reader)
    listing = await asyncio.to_thread(tracked.read, "list")
    paths = listing.get("files", [])
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        return IntakeAgentOutput(error_code="INSPECTION_FAILED")
    serialized_input = json.dumps(prepared.payload, ensure_ascii=False)
    manifests = {
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "pom.xml",
        "build.gradle",
        "Dockerfile",
        "Cargo.toml",
        "go.mod",
    }
    ordered = sorted(
        paths,
        key=lambda path: (
            path not in serialized_input,
            path.rsplit("/", 1)[-1] not in manifests,
            path,
        ),
    )
    context = []
    preloaded = []
    remaining_bytes = budget.tool_output_bytes
    preload_calls = 1
    for path in ordered[: min(4, budget.max_tool_calls - 2)]:
        record = await asyncio.to_thread(tracked.read, "read", path)
        preload_calls += 1
        content = record.get("content")
        if not isinstance(content, str):
            context.append({"path": path, "error": "read_unavailable"})
            continue
        raw = content.encode()
        truncated = len(raw) > remaining_bytes or bool(record.get("truncated"))
        excerpt = raw[:remaining_bytes].decode("utf-8", errors="ignore")
        context.append({"path": path, "content": excerpt, "truncated": truncated})
        remaining_bytes -= len(excerpt.encode())
        if truncated:
            tracked.paths.discard(path)
        else:
            preloaded.append(path)
        if remaining_bytes <= 0:
            break
    accounting.max_tool_calls = budget.max_tool_calls - preload_calls
    packet = {
        "source_context": context,
        "source_listing_truncated": listing.get("truncated", False),
        "issue_input": prepared.payload if canonical is None else None,
        "inspected_paths": preloaded,
        "canonical_issue": None if canonical is None else canonical.model_dump(mode="json"),
        "available_images": prepared.inventory.model_dump(mode="json")["images"],
    }
    message = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(message.encode()) > 131072:
        return IntakeAgentOutput(error_code="INPUT_LIMIT_EXCEEDED")
    remaining_seconds = min(
        budget.max_elapsed_seconds, prepared.episode_seconds or budget.max_elapsed_seconds
    ) - (time.perf_counter() - started)
    if remaining_seconds <= 0:
        return IntakeAgentOutput(
            error_code="MODEL_FAILED",
            usage=accounting.usage(time.perf_counter() - started),
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
        )
    bounds = episode_bounds(remaining_seconds, settings.models.request_timeout_seconds)
    agent = build_intake(
        model_for_role(settings, "intake", request_timeout_seconds=bounds.request_seconds)
        if model_override is None
        else model_override,
        tracked,
        prepared.inventory,
        budget.tool_output_bytes,
    )
    agent.after_tool_callback = accounting.after_tool
    for skill_name in spec.runtime_skills:
        event("agent.skill_preloaded", role=spec.name, skill_name=skill_name)
    text, feedback = await _run_native_episode(
        agent=agent,
        app_name="corsair-intake",
        user_id=prepared.run_id,
        session_id="intake",
        message=message,
        author="intake",
        llm_call_limit=llm_limit,
        timeout_seconds=bounds.episode_seconds,
        accounting=accounting,
    )
    usage = accounting.usage(time.perf_counter() - started)
    if feedback is not None:
        return IntakeAgentOutput(
            error_code="MODEL_FAILED",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    if accounting.llm_limit_exhausted:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="LLM_BUDGET_EXHAUSTED",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    if accounting.tool_limit_exhausted or accounting.loader_limit_exhausted:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="TOOL_BUDGET_EXHAUSTED",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    if text is None:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="NO_STRUCTURED_OUTPUT",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    try:
        proposal = IntakeProposal.model_validate_json(text)
    except ValidationError as error:
        for failure in error.errors(include_input=False, include_context=False, include_url=False):
            category = f"schema:{failure['type']}"
            if category in accounting.completion_errors or len(accounting.completion_errors) < 32:
                accounting.completion_errors[category] = (
                    accounting.completion_errors.get(category, 0) + 1
                )
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="SCHEMA_INVALID",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    try:
        validate_proposal(proposal, prepared.inventory)
    except ValueError:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="IMAGE_OUTSIDE_INVENTORY",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    if canonical is not None and proposal.issue != canonical:
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="CANONICAL_ISSUE_MODIFIED",
            usage=usage,
            tool_counts=accounting.tool_counts,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            completion_errors=accounting.completion_errors,
        )
    if any(location.path not in tracked.paths for location in proposal.locations):
        return IntakeAgentOutput(
            error_code="OUTPUT_INVALID",
            output_failure="SOURCE_NOT_INSPECTED",
            usage=usage,
            source_preloaded=preloaded,
            inspection_reads=preload_calls,
            tool_counts=accounting.tool_counts,
        )
    return IntakeAgentOutput(
        proposal=proposal,
        usage=usage,
        tool_counts=accounting.tool_counts,
        source_preloaded=preloaded,
        inspection_reads=preload_calls,
        completion_errors=accounting.completion_errors,
    )
