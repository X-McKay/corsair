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
from dataclasses import dataclass
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from corsair.agents.auditor.factory import build_auditor
from corsair.agents.producer.factory import build_producer
from corsair.agents.producer.tools import build_producer_tools
from corsair.contracts import (
    AuditInput,
    AuditOutput,
    AuditResult,
    Feedback,
    ProducerInput,
    ProducerOutput,
    Usage,
)
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.models import AgentModel, model_for_role
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
    llm_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    llm_limit_exhausted: bool = False
    provider_error_code: str | None = None
    provider_error_message: str | None = None

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

    def usage(self, tool_calls: int, seconds: float) -> Usage:
        return Usage(
            llm_calls=self.llm_calls,
            tool_calls=tool_calls,
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
    model_override: AgentModel | None = None,
) -> ProducerOutput:
    """Run one bounded producer episode and return only typed proposal data."""

    started = time.perf_counter()
    llm_limit = _effective_limit(
        producer_input.llm_call_limit, producer_input.budget.episode_llm_calls
    )
    tool_limit = min(producer_input.tool_call_limit, producer_input.budget.max_tool_calls)
    private_tools = build_producer_tools(producer_input, store, tool_call_limit=tool_limit)
    model = model_for_role(settings, "producer") if model_override is None else model_override
    agent = build_producer(model, private_tools.native_tools())
    accounting = _EpisodeAccounting(
        max_llm_calls=llm_limit,
        max_output_tokens=producer_input.budget.max_output_tokens,
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
    usage = accounting.usage(private_tools.tool_calls, seconds)
    if operational_feedback is not None:
        return ProducerOutput(usage=usage, feedback=operational_feedback)
    if private_tools.submission is not None:
        return ProducerOutput(submission=private_tools.submission, usage=usage)
    if private_tools.limit_exhausted:
        reason = "producer exhausted its tool-call budget before a valid submission"
    elif accounting.llm_limit_exhausted:
        reason = "producer exhausted its LLM-call budget before a valid submission"
    elif private_tools.errors:
        reason = _bounded_text(private_tools.errors[-1], 2000)
    elif last_agent_text:
        reason = "producer returned text instead of a terminal submit tool call"
    else:
        reason = "producer returned no terminal submission"
    return ProducerOutput(
        usage=usage,
        feedback=Feedback(gate="producer_invalid", reason=reason, operational=False),
    )


async def run_auditor(
    audit_input: AuditInput,
    settings: Settings | ModelSettings,
    model_override: AgentModel | None = None,
) -> AuditOutput:
    """Run one fresh, tool-free, outcome-blind audit request with no retry loop."""

    started = time.perf_counter()
    model = model_for_role(settings, "auditor") if model_override is None else model_override
    agent = build_auditor(model)
    accounting = _EpisodeAccounting(
        max_llm_calls=1, max_output_tokens=audit_input.max_output_tokens
    )
    last_agent_text, operational_feedback = await _run_native_episode(
        agent=agent,
        app_name="corsair-auditor",
        user_id="corsair-auditor",
        session_id="audit",
        message=_auditor_prompt(audit_input),
        author="auditor",
        llm_call_limit=1,
        timeout_seconds=300,
        accounting=accounting,
    )
    usage = accounting.usage(tool_calls=0, seconds=time.perf_counter() - started)
    if operational_feedback is not None:
        return AuditOutput(usage=usage, feedback=operational_feedback)
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
