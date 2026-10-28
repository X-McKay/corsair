"""Bounded Google ADK role invocations used inside Temporal activities.

Temporal owns durable rounds and root budgets.  This module deliberately runs a
single, fresh ADK ``Runner.run_async`` episode for each producer or auditor
activity; it does not use ADK's experimental Temporal integration.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from corsair.contracts.intake import IntakeAgentOutput, PreparedIntake
    from corsair.ports.intake import InspectionReader

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import ValidationError

from corsair.adapters.inference.models import model_for_role
from corsair.adapters.scm.local import StoredSourceReader
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.auditor.contracts import AuditInput, AuditOutput, AuditResult
from corsair.agents.auditor.factory import build_auditor
from corsair.agents.auditor.toolsets import build_auditor_toolset
from corsair.agents.producer.contracts import (
    ProducerDecision,
    ProducerInput,
    ProducerOutput,
    ProducerProposal,
)
from corsair.agents.producer.factory import build_producer
from corsair.agents.producer.toolsets import build_producer_toolset
from corsair.agents.resources import load_agent_spec
from corsair.contracts import (
    Feedback,
    Usage,
)
from corsair.observability.logging import event
from corsair.settings import ModelSettings, Settings

_MAX_PROMPT_BYTES = 32_768
_CREDENTIAL_ENV_NAME = re.compile(
    r"(?:api[_-]?key|token|secret|password|authorization|credential)", re.IGNORECASE
)
_URL_USERINFO = re.compile(r"(https?://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)
_SENSITIVE_QUERY = re.compile(
    r"([?&](?:api[_-]?key|token|secret|password|authorization)=[^&#\s]+)", re.IGNORECASE
)
_SENSITIVE_HEADER = re.compile(
    r"((?:authorization|api[_-]?key|x-api-key)\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)
_COMMON_SECRET = re.compile(r"\b(?:sk-|AIza|ghp_|xox[baprs]-)[A-Za-z0-9_=-]+")


@dataclass
class _EpisodeAccounting:
    """Native ADK callback state for a single provider episode."""

    max_llm_calls: int
    max_output_tokens: int
    max_tool_calls: int = 0
    max_loader_calls: int = 0
    role: str = ""
    loader_tool_names: frozenset[str] = frozenset()
    allowed_skill_names: frozenset[str] = frozenset()
    tool_calls: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    completion_errors: dict[str, int] = field(default_factory=dict)
    loader_calls: int = 0
    tool_limit_exhausted: bool = False
    loader_limit_exhausted: bool = False
    llm_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    llm_limit_exhausted: bool = False
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    skills_loaded: list[str] = field(default_factory=list)
    skills_preloaded: list[str] = field(default_factory=list)

    async def before_model(
        self, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        """Charge model work before dispatch and bind this episode's generation cap."""

        if self.llm_calls >= self.max_llm_calls:
            self.llm_limit_exhausted = True
            callback_context._invocation_context.end_invocation = True
            return LlmResponse(
                error_code="CORSairLlmCallLimit",
                error_message="episode LLM-call budget exhausted",
            )
        self.llm_calls += 1
        llm_request.config = llm_request.config or types.GenerateContentConfig()
        configured = llm_request.config.max_output_tokens
        llm_request.config.max_output_tokens = (
            self.max_output_tokens
            if configured is None
            else min(configured, self.max_output_tokens)
        )
        return None

    async def before_tool(
        self, tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, str] | None:
        """Charge every native tool, including ADK schema completion, before work."""

        del args
        if self.tool_calls >= self.max_tool_calls:
            self.tool_limit_exhausted = True
            tool_context._invocation_context.end_invocation = True
            return {"error": "tool-call budget exhausted"}
        if tool.name in self.loader_tool_names and self.loader_calls >= self.max_loader_calls:
            self.loader_limit_exhausted = True
            tool_context._invocation_context.end_invocation = True
            return {"error": "runtime skill loader budget exhausted"}
        self.tool_calls += 1
        if tool.name in {"read_file", "list_files", "compare_images", "set_model_response"}:
            self.tool_counts[tool.name] = self.tool_counts.get(tool.name, 0) + 1
        if tool.name in self.loader_tool_names:
            self.loader_calls += 1
        return None

    async def after_model(
        self, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        """Capture reported native response usage without manufacturing tokens."""

        del callback_context
        usage = llm_response.usage_metadata
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
            if prompt_tokens is not None:
                self.input_tokens = (self.input_tokens or 0) + int(prompt_tokens)
            if output_tokens is not None:
                self.output_tokens = (self.output_tokens or 0) + int(output_tokens)
        if llm_response.error_code or llm_response.error_message:
            self.provider_error_code = str(llm_response.error_code or "")
            self.provider_error_message = str(llm_response.error_message or "")
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

    def usage(self, seconds: float) -> Usage:
        return Usage(
            llm_calls=self.llm_calls,
            tool_calls=self.tool_calls,
            skills_loaded=self.skills_loaded,
            skills_preloaded=self.skills_preloaded,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            seconds=seconds,
        )


def _bounded_json(value: Any, byte_limit: int = _MAX_PROMPT_BYTES) -> str:
    """Render public packet data without allowing an unbounded agent prompt."""

    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw = rendered.encode("utf-8")
    if len(raw) <= byte_limit:
        return rendered
    # The output is a prompt fragment rather than another machine contract, so
    # retaining a valid JSON closing delimiter is less useful than an explicit
    # and unambiguous truncation marker.
    return raw[:byte_limit].decode("utf-8", errors="ignore") + "\n[truncated by Corsair]"


def _bounded_text(value: str, byte_limit: int = _MAX_PROMPT_BYTES) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= byte_limit:
        return value
    return raw[:byte_limit].decode("utf-8", errors="ignore") + "\n[truncated by Corsair]"


def _redact_provider_detail(value: str) -> str:
    """Remove credentials from provider/transport errors before durable storage."""

    redacted = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
    redacted = _SENSITIVE_QUERY.sub(
        lambda match: match.group(1).split("=", 1)[0] + "=[REDACTED]", redacted
    )
    redacted = _SENSITIVE_HEADER.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_TOKEN.sub("Bearer [REDACTED]", redacted)
    redacted = _COMMON_SECRET.sub("[REDACTED]", redacted)
    for name, secret in os.environ.items():
        if _CREDENTIAL_ENV_NAME.search(name) and len(secret) >= 4:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _producer_prompt(producer_input: ProducerInput) -> str:
    """Build the producer's intentionally outcome- and manifest-blind packet."""

    prepared = producer_input.prepared
    packet = {
        "finding": prepared.finding.model_dump(mode="json"),
        "recipe_public_configuration": prepared.recipe.model_dump(mode="json"),
        "observer_fixture_location": "/fixtures/private/secret.txt",
        "source_excerpt": _bounded_text(prepared.source_excerpt),
        "round": {
            "revision": producer_input.round_index,
            "parent_revision": None
            if producer_input.round_index == 1
            else producer_input.round_index - 1,
        },
        "previous_submission": None
        if producer_input.previous is None
        else producer_input.previous.model_dump(mode="json"),
        "previous_feedback": None
        if producer_input.feedback is None
        else producer_input.feedback.model_dump(mode="json"),
    }
    return (
        "Investigate this admitted work packet. It excludes execution outcomes, "
        "private fixtures, manifests, case paths, and verifier oracles.\n" + _bounded_json(packet)
    )


def _auditor_prompt(audit_input: AuditInput) -> str:
    """Build the auditor's exact outcome-blind whitelist packet."""

    packet = {
        "finding": audit_input.finding.model_dump(mode="json"),
        "recipe_public_configuration": audit_input.recipe.model_dump(mode="json"),
        "observer_fixture_location": "/fixtures/private/secret.txt",
        "source_excerpt": _bounded_text(audit_input.source_excerpt),
        "submission": audit_input.submission.model_dump(mode="json"),
    }
    return (
        "Review this outcome-blind packet only. Do not infer execution results or a final "
        "disposition. Return the requested AuditResult JSON object.\n" + _bounded_json(packet)
    )


def _feedback_for_provider(code: str | None, message: str | None) -> Feedback:
    """Classify one provider failure without retrying inside a durable activity."""

    detail = _redact_provider_detail(" ".join(part for part in (code, message) if part).strip())
    lowered = detail.lower()
    temporary_markers = (
        "429",
        "rate",
        "timeout",
        "temporar",
        "unavailable",
        "connection",
        "overloaded",
        "500",
        "502",
        "503",
        "504",
    )
    if any(marker in lowered for marker in ("cyber_policy", "content_policy", "safety policy")):
        gate = "provider_policy_blocked"
    else:
        gate = (
            "provider_temporary"
            if any(marker in lowered for marker in temporary_markers)
            else "provider_permanent"
        )
    return Feedback(
        gate=gate,
        reason=_bounded_text(detail or "provider returned an unspecified error", 2000),
        operational=True,
    )


def _feedback_for_exception(error: Exception) -> Feedback:
    return _feedback_for_provider(type(error).__name__, str(error))


def _agent_text(event: Event, author: str) -> str | None:
    """Return non-thought text when an ADK event belongs to the requested role."""

    if getattr(event, "author", None) != author:
        return None
    content = getattr(event, "content", None)
    if content is None or not content.parts:
        return None
    text = "".join(
        part.text
        for part in content.parts
        if part.text is not None and not getattr(part, "thought", False)
    )
    return text if text.strip() else None


async def _run_native_episode(
    *,
    agent: LlmAgent,
    app_name: str,
    user_id: str,
    session_id: str,
    message: str,
    author: str,
    llm_call_limit: int,
    timeout_seconds: int,
    accounting: _EpisodeAccounting,
) -> tuple[str | None, Feedback | None]:
    """Run exactly one ordinary ADK Runner episode with a fresh memory-only session."""

    service = InMemorySessionService()
    await service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
    runner = Runner(app_name=app_name, agent=agent, session_service=service)
    # Callbacks are native ADK hooks.  RunConfig still provides ADK's own
    # positive LLM-call ceiling; the callback additionally records actual
    # dispatches and constrains per-request output generation.
    agent.before_model_callback = accounting.before_model
    agent.after_model_callback = accounting.after_model
    agent.before_tool_callback = accounting.before_tool
    agent.after_tool_callback = accounting.after_tool
    last_text: str | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text=message)]),
                run_config=RunConfig(max_llm_calls=llm_call_limit),
            ):
                if text := _agent_text(event, author):
                    last_text = text
    except TimeoutError:
        return last_text, Feedback(
            gate="episode_timeout",
            reason="bounded ADK episode exceeded its elapsed-time limit",
            operational=True,
        )
    except Exception as error:  # Provider/transport failures are activity data, not retries.
        return last_text, _feedback_for_exception(error)
    if accounting.provider_error_code or accounting.provider_error_message:
        return last_text, _feedback_for_provider(
            accounting.provider_error_code, accounting.provider_error_message
        )
    return last_text, None


def _effective_limit(requested: int, configured: int) -> int:
    """Respect both caller/root remaining budget and the per-episode budget."""

    limit = min(requested, configured)
    if limit < 1:
        raise ValueError("episode LLM-call limit must be positive")
    return limit


async def run_producer(
    producer_input: ProducerInput,
    settings: Settings | ModelSettings,
    store: ArtifactStore,
    model_override: str | BaseLlm | None = None,
) -> ProducerOutput:
    """Run one bounded producer episode and return only typed decision data."""

    started = time.perf_counter()
    llm_limit = _effective_limit(
        producer_input.llm_call_limit, producer_input.budget.episode_llm_calls
    )
    tool_limit = min(producer_input.tool_call_limit, producer_input.budget.max_tool_calls)
    spec = load_agent_spec("producer")
    private_tools = build_producer_toolset(producer_input, StoredSourceReader(store))
    model = model_for_role(settings, "producer") if model_override is None else model_override
    agent = build_producer(model, private_tools)
    for skill_name in spec.runtime_skills:
        event("agent.skill_preloaded", role=spec.name, skill_name=skill_name)
    accounting = _EpisodeAccounting(
        max_llm_calls=llm_limit,
        max_output_tokens=producer_input.budget.max_output_tokens,
        max_tool_calls=tool_limit,
        max_loader_calls=spec.loader_call_limit,
        role=spec.name,
        loader_tool_names=frozenset(spec.loader_tools),
        allowed_skill_names=frozenset(spec.runtime_skills),
        skills_preloaded=list(spec.runtime_skills),
    )
    last_agent_text, operational_feedback = await _run_native_episode(
        agent=agent,
        app_name="corsair-producer",
        user_id=producer_input.run_id,
        session_id=f"producer-{producer_input.round_index}",
        message=_producer_prompt(producer_input),
        author="producer",
        llm_call_limit=llm_limit,
        timeout_seconds=producer_input.budget.max_elapsed_seconds,
        accounting=accounting,
    )
    seconds = time.perf_counter() - started
    usage = accounting.usage(seconds)
    if operational_feedback is not None:
        return ProducerOutput(usage=usage, feedback=operational_feedback)
    if accounting.loader_limit_exhausted:
        reason = "producer exhausted its runtime skill loader budget before structured completion"
    elif accounting.tool_limit_exhausted:
        reason = "producer exhausted its tool-call budget before structured completion"
    elif accounting.llm_limit_exhausted:
        reason = "producer exhausted its LLM-call budget before structured completion"
    elif last_agent_text is None:
        reason = "producer returned no structured ProducerDecision output"
    else:
        try:
            decision = ProducerDecision.model_validate_json(last_agent_text)
        except ValidationError:
            reason = "producer returned malformed ProducerDecision output"
        else:
            variant = decision.root
            if isinstance(variant, ProducerProposal):
                expected_parent = (
                    None if producer_input.round_index == 1 else producer_input.round_index - 1
                )
                if variant.submission.plan.revision != producer_input.round_index:
                    reason = "plan revision must equal the current round index"
                elif variant.submission.plan.parent_revision != expected_parent:
                    reason = "plan parent_revision does not match the preceding round"
                else:
                    return ProducerOutput(decision=decision, usage=usage)
            else:
                return ProducerOutput(decision=decision, usage=usage)
    return ProducerOutput(
        usage=usage,
        feedback=Feedback(gate="producer_invalid", reason=reason, operational=False),
    )


async def run_auditor(
    audit_input: AuditInput,
    settings: Settings | ModelSettings,
    model_override: str | BaseLlm | None = None,
) -> AuditOutput:
    """Run one fresh outcome-blind review with finite private procedure loaders."""

    started = time.perf_counter()
    spec = load_agent_spec("auditor")
    if spec.llm_call_limit is None:  # Covered by AgentSpec; retain a local safety boundary.
        raise ValueError("auditor metadata must declare a finite native LLM-call limit")
    llm_limit = min(audit_input.llm_call_limit, spec.llm_call_limit)
    tool_limit = min(audit_input.tool_call_limit, spec.loader_call_limit)
    if llm_limit == 0:
        return AuditOutput(
            usage=Usage(llm_calls=0, tool_calls=0, seconds=time.perf_counter() - started),
            feedback=Feedback(
                gate="audit_invalid",
                reason="auditor has no remaining model-call budget for a review",
                operational=False,
            ),
        )
    model = model_for_role(settings, "auditor") if model_override is None else model_override
    agent = build_auditor(model, build_auditor_toolset())
    for skill_name in spec.runtime_skills:
        event("agent.skill_preloaded", role=spec.name, skill_name=skill_name)
    accounting = _EpisodeAccounting(
        max_llm_calls=llm_limit,
        max_output_tokens=audit_input.max_output_tokens,
        max_tool_calls=tool_limit,
        max_loader_calls=tool_limit,
        role=spec.name,
        loader_tool_names=frozenset(spec.loader_tools),
        allowed_skill_names=frozenset(spec.runtime_skills),
        skills_preloaded=list(spec.runtime_skills),
    )
    last_agent_text, operational_feedback = await _run_native_episode(
        agent=agent,
        app_name="corsair-auditor",
        user_id="corsair-auditor",
        session_id="audit",
        message=_auditor_prompt(audit_input),
        author="auditor",
        llm_call_limit=llm_limit,
        timeout_seconds=300,
        accounting=accounting,
    )
    usage = accounting.usage(seconds=time.perf_counter() - started)
    if operational_feedback is not None:
        return AuditOutput(usage=usage, feedback=operational_feedback)
    if accounting.loader_limit_exhausted:
        return AuditOutput(
            usage=usage,
            feedback=Feedback(
                gate="audit_invalid",
                reason=(
                    "auditor exhausted its runtime skill loader budget before structured completion"
                ),
                operational=False,
            ),
        )
    if accounting.tool_limit_exhausted:
        return AuditOutput(
            usage=usage,
            feedback=Feedback(
                gate="audit_invalid",
                reason="auditor exhausted its tool-call budget before structured completion",
                operational=False,
            ),
        )
    if accounting.llm_limit_exhausted:
        return AuditOutput(
            usage=usage,
            feedback=Feedback(
                gate="audit_invalid",
                reason="auditor exhausted its LLM-call budget before structured completion",
                operational=False,
            ),
        )
    text = last_agent_text
    if text is None:
        return AuditOutput(
            usage=usage,
            feedback=Feedback(
                gate="audit_invalid",
                reason="auditor returned no structured output",
                operational=False,
            ),
        )
    try:
        review = AuditResult.model_validate_json(text)
    except (ValidationError, ValueError):
        return AuditOutput(
            usage=usage,
            feedback=Feedback(
                gate="audit_invalid",
                reason="auditor returned malformed AuditResult output",
                operational=False,
            ),
        )
    return AuditOutput(review=review, usage=usage)


@dataclass
class AdkInference:
    """Concrete native ADK implementation of the two bounded inference operations."""

    settings: Settings
    store: ArtifactStore
    model_override: str | BaseLlm | None = None

    async def produce(self, request: ProducerInput) -> ProducerOutput:
        return await run_producer(request, self.settings, self.store, self.model_override)

    async def audit(self, request: AuditInput) -> AuditOutput:
        return await run_auditor(request, self.settings, self.model_override)


async def run_intake(
    prepared: PreparedIntake,
    settings: Settings,
    reader: InspectionReader,
    model_override: str | BaseLlm | None = None,
) -> IntakeAgentOutput:
    """One bounded native intake episode, with inventory-constrained validation."""
    from corsair.agents.intake.factory import build_intake
    from corsair.agents.intake.toolsets import TrackedInspection
    from corsair.contracts.intake import IntakeAgentOutput, IntakeProposal, Issue
    from corsair.policies.intake import validate_proposal

    started = time.perf_counter()
    budget = prepared.request.budget
    spec = load_agent_spec("intake")
    llm_limit = min(budget.episode_llm_calls, budget.max_llm_calls, 4)
    accounting = _EpisodeAccounting(
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
    agent = build_intake(
        model_for_role(settings, "intake") if model_override is None else model_override,
        tracked,
        prepared.inventory,
        budget.tool_output_bytes,
    )
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
        timeout_seconds=min(
            budget.max_elapsed_seconds, prepared.episode_seconds or budget.max_elapsed_seconds
        ),
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
