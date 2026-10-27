"""Read-only infrastructure diagnostics, not a mock run or model qualification.

The opt-in model checks send a few minimal requests and never an agent prompt or source; their
ADK and provider imports stay inside :func:`diagnose_model`, so the default doctor loads neither.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Callable
from contextlib import closing, redirect_stdout
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import docker
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest

from corsair.adapters.temporal.client import connect
from corsair.entrypoints.terminal import failure_remedy
from corsair.observability.logging import safe_text
from corsair.settings import Decoding, Settings

if TYPE_CHECKING:
    from google.adk.models import BaseLlm
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from corsair.agents.resources import RoleName

    type ModelResolver = Callable[[Settings, RoleName], str | BaseLlm]


def _directory(path: str, *, writable=False) -> str:
    target = Path(path).absolute()
    if not writable:
        if not target.is_dir() or not os.access(target, os.R_OK | os.X_OK):
            raise ValueError("source_root must be a readable directory")
        return "Readable source admission root"
    while not target.exists():
        target = target.parent
    if not target.is_dir() or not os.access(target, os.W_OK | os.X_OK):
        raise ValueError("artifact root or its parent must be writable")
    return "Writable artifact root or parent; no files created"


def _docker(settings: Settings) -> str:
    with closing(docker.from_env(timeout=5)) as client:
        client.ping()
        tags = sorted({settings.image, *settings.images.values()})
        resolved = {tag: str(client.images.get(tag).id) for tag in tags}
        runtimes = client.info().get("Runtimes", {})
        if settings.runtime not in runtimes:
            raise ValueError(f"configured runtime {settings.runtime} is not registered")
        images = "; ".join(f"{tag}={image_id}" for tag, image_id in resolved.items())
        return f"Daemon reachable; runtime={settings.runtime}; images={images}"


def _failed_check(name: str, error: Exception) -> dict:
    """Report a failed dependency with its sanitized error and any fixed remedy."""
    check = {
        "name": name,
        "status": "fail",
        "detail": safe_text(f"{type(error).__name__}: {error}"),
    }
    remedy = failure_remedy(error)
    return check if remedy is None else {**check, "remedy": remedy}


async def diagnose(
    settings: Settings, *, model: bool = False, resolve_model: ModelResolver | None = None
) -> dict:
    """Check infrastructure and, only when ``model`` is set, the configured model routes."""
    checks = []
    for name, operation in (
        ("source_root", lambda: _directory(settings.source_root)),
        ("artifact_root", lambda: _directory(settings.artifact_root, writable=True)),
        ("docker", lambda: _docker(settings)),
    ):
        try:
            detail = await asyncio.to_thread(operation)
            checks.append({"name": name, "status": "pass", "detail": detail})
        except Exception as error:
            checks.append(_failed_check(name, error))
    try:
        async with asyncio.timeout(8):
            client = await connect(settings)
            await client.workflow_service.describe_namespace(
                DescribeNamespaceRequest(namespace=settings.temporal_namespace)
            )
            checks.append(
                {
                    "name": "temporal",
                    "status": "pass",
                    "detail": f"Namespace {settings.temporal_namespace} is accessible",
                }
            )
            queues = await asyncio.gather(
                *[
                    client.workflow_service.describe_task_queue(
                        DescribeTaskQueueRequest(
                            namespace=settings.temporal_namespace,
                            task_queue=TaskQueue(name=settings.task_queue),
                            task_queue_type=kind,
                        )
                    )
                    for kind in (
                        TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
                        TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
                    )
                ]
            )
            available = all(response.pollers for response in queues)
            checks.append(
                {
                    "name": "worker_pollers",
                    "status": "pass" if available else "warn",
                    "detail": "Workflow and activity pollers reported"
                    if available
                    else "Start corsair worker; workflow/activity pollers not both reported",
                }
            )
    except Exception as error:
        checks.append(_failed_check("temporal", error))
    if model:
        checks.extend(await diagnose_model(settings, resolve_model=resolve_model))
    return {
        "ready": all(check["status"] == "pass" for check in checks),
        "checks": checks,
        "versions": {
            name: version(name) for name in ("google-adk", "temporalio", "docker", "rich")
        },
        "qualification": _MODEL_QUALIFICATION if model else _INFRASTRUCTURE_QUALIFICATION,
    }


_INFRASTRUCTURE_QUALIFICATION = (
    "Infrastructure checks only. Poller presence is not an execution test. "
    "Model credentials, provider policy, native evidence and accuracy were not tested."
)
_MODEL_QUALIFICATION = (
    "Infrastructure checks plus one minimal request per role model and one tool round trip "
    "on the producer model. Poller presence is not an execution test. Prompt-sized requests, "
    "provider policy, role output caps, native evidence and accuracy were not tested."
)
# A tiny cap keeps the probe cheap; reasoning tokens count against it, so a truncated text
# probe still proves the route answered. The tool probe gets room for one function call.
_TEXT_PROBE_OUTPUT_TOKENS = 32
_TOOL_PROBE_OUTPUT_TOKENS = 128
# Added to models.request_timeout_seconds so the provider's own timeout normally fires first.
_PROBE_GRACE_SECONDS = 5.0
_PROBE_TOOL = "corsair_ping"
# The producer pairs its response schema with tools when the model declares that capability;
# the tool probe does the same with this trivial schema, so it exercises the producer's route.
_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
}
# LiteLLM route prefix -> (environment variable names, any one suffices; whether required).
# Names follow LiteLLM's provider conventions. Only the name is ever checked or reported.
_LITELLM_CREDENTIALS: dict[str, tuple[tuple[str, ...], bool]] = {
    "openai": (("OPENAI_API_KEY",), True),
    "anthropic": (("ANTHROPIC_API_KEY",), True),
    "gemini": (("GEMINI_API_KEY", "GOOGLE_API_KEY"), True),
    "hosted_vllm": (("HOSTED_VLLM_API_KEY",), False),
    "litellm_proxy": (("LITELLM_PROXY_API_KEY",), False),
    "openrouter": (("OPENROUTER_API_KEY",), True),
    "groq": (("GROQ_API_KEY",), True),
    "mistral": (("MISTRAL_API_KEY",), True),
    "deepseek": (("DEEPSEEK_API_KEY",), True),
    "together_ai": (("TOGETHERAI_API_KEY",), True),
    "xai": (("XAI_API_KEY",), True),
    "ollama": ((), False),
    "ollama_chat": ((), False),
}
_TIMEOUT_REMEDY = (
    "The endpoint did not answer within models.request_timeout_seconds. Check its load, or "
    "raise request_timeout_seconds in --settings (at most 300); the roles use the same timeout."
)
_AUTH_REMEDY = (
    "Export the provider credential named by the model_credentials check in the environment "
    "that runs the worker and doctor; never put it in --settings."
)
_NOT_FOUND_REMEDY = (
    "Check the model name and its route prefix in --settings against the models the "
    "endpoint serves."
)
_CONNECTION_REMEDY = "Check models.api_base in --settings and that this host can reach it."
_PROVIDERS_REMEDY = (
    "Install Corsair's providers extra with `just sync` or `uv sync --locked --extra providers`."
)
_TOOL_ROUTE_REMEDY = (
    "This route did not return a native function call, so producer episodes would never call "
    "their tools. Serve the producer on a route that returns tool calls (for vLLM, a "
    "hosted_vllm/ route with tool calling enabled); see docs/operations/troubleshooting.md."
)


def _api_base_host(api_base: str | None) -> str:
    """Report only an endpoint's host and port: never userinfo, path, query or fragment."""
    if not api_base:
        return "provider default"
    url = urlsplit(api_base)
    host = url.hostname or "unknown"
    try:
        port = url.port
    except ValueError:
        port = None
    return host if port is None else f"{host}:{port}"


def _decoding_text(decoding: Decoding) -> str:
    """Name each set sampling parameter, or the server default when none is set."""
    if decoding.unset:
        return "server default"
    values = {"temperature": decoding.temperature, "top_p": decoding.top_p, "seed": decoding.seed}
    return ", ".join(f"{key}={value}" for key, value in values.items() if value is not None)


def _model_config_check(settings: Settings) -> dict:
    models = settings.models
    keys = ", ".join(sorted(models.extra_body)) or "none"
    detail = (
        f"connector={models.connector}; producer={models.producer}; auditor={models.auditor}; "
        f"api_base host={_api_base_host(models.api_base)}; "
        f"request_timeout_seconds={models.request_timeout_seconds}; extra_body keys={keys}; "
        f"decoding producer={_decoding_text(models.decoding.producer)}; "
        f"decoding auditor={_decoding_text(models.decoding.auditor)}"
    )
    return {"name": "model_config", "status": "pass", "detail": safe_text(detail)}


def _credential_requirement(
    settings: Settings, model_name: str
) -> tuple[str, tuple[str, ...], bool] | None:
    """Return the route, credential variable names and whether one is required."""
    if settings.models.connector == "gemini":
        if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true"}:
            return "gemini (Vertex AI)", ("GOOGLE_CLOUD_PROJECT",), True
        return "gemini", ("GOOGLE_API_KEY", "GEMINI_API_KEY"), True
    prefix = model_name.split("/", 1)[0] if "/" in model_name else ""
    known = _LITELLM_CREDENTIALS.get(prefix)
    return None if known is None else (f"{prefix}/", *known)


def _model_credentials_check(settings: Settings) -> dict:
    """Confirm each role's provider variable is present, by name only; values are never read."""
    statuses: list[str] = []
    notes: list[str] = []
    for role in ("producer", "auditor"):
        model_name = getattr(settings.models, role)
        requirement = _credential_requirement(settings, model_name)
        if requirement is None:
            route = model_name.split("/", 1)[0] + "/" if "/" in model_name else "(no prefix)"
            statuses.append("warn")
            notes.append(f"{role}: no known credential variable for route {route}; not checked")
            continue
        route, names, required = requirement
        present = next((name for name in names if os.environ.get(name)), None)
        if present is not None:
            statuses.append("pass")
            notes.append(f"{role}: {present} is set")
        elif not names:
            statuses.append("pass")
            notes.append(f"{role}: route {route} needs no credential variable")
        elif required:
            statuses.append("fail")
            notes.append(f"{role}: {' or '.join(names)} is not set (required for {route})")
        else:
            statuses.append("pass")
            notes.append(
                f"{role}: {names[0]} is not set; optional for {route}, so the endpoint must "
                "accept requests without it"
            )
    status = next((kind for kind in ("fail", "warn") if kind in statuses), "pass")
    check = {"name": "model_credentials", "status": status, "detail": safe_text("; ".join(notes))}
    return {**check, "remedy": _AUTH_REMEDY} if status == "fail" else check


def _model_remedy(kinds: set[str], text: str) -> str | None:
    """Map a provider failure, by exception class names and fixed markers, to a fixed step."""
    lowered = text.lower()
    if (
        "Timeout" in kinds
        or "TimeoutError" in kinds
        or "timeout" in lowered
        or "timed out" in lowered
    ):
        return _TIMEOUT_REMEDY
    if kinds & {"AuthenticationError", "PermissionDeniedError"} or any(
        marker in lowered for marker in ("401", "403", "api key", "api_key", "unauthorized")
    ):
        return _AUTH_REMEDY
    if "NotFoundError" in kinds or "404" in lowered or "does not exist" in lowered:
        return _NOT_FOUND_REMEDY
    if "APIConnectionError" in kinds or "ConnectionError" in kinds or "connection" in lowered:
        return _CONNECTION_REMEDY
    return None


def _model_failure(name: str, error: BaseException) -> dict:
    """Report a failed model step with sanitized detail and a fixed remedy where one applies."""
    kinds = {kind.__name__ for kind in type(error).__mro__}
    detail = safe_text(f"{type(error).__name__}: {error}")
    if isinstance(error, ImportError):
        remedy = _PROVIDERS_REMEDY
    else:
        remedy = _model_remedy(kinds, str(error))
        if remedy is None:
            remedy = failure_remedy(error)
    check = {"name": name, "status": "fail", "detail": detail}
    return check if remedy is None else {**check, "remedy": remedy}


def _response_failure(name: str, response: LlmResponse) -> dict:
    """Report a provider error that ADK returned as a response rather than raised."""
    text = f"{response.error_code or ''} {response.error_message or ''}".strip()
    check = {"name": name, "status": "fail", "detail": safe_text(text or "provider error")}
    remedy = _model_remedy(set(), text)
    return check if remedy is None else {**check, "remedy": remedy}


def _probe_request(
    model: BaseLlm, *, tool: bool, decoding: types.GenerateContentConfig | None
) -> LlmRequest:
    """Build one minimal typed request: no agent prompt, no source, no Corsair content.

    ``decoding`` is the role's sampling config exactly as its agent sends it (unset
    parameters stay unset), so a route that rejects one fails here, not in an episode.
    """
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types

    sampling = decoding or types.GenerateContentConfig()
    if not tool:
        text, cap = "Reply with the single word: ready", _TEXT_PROBE_OUTPUT_TOKENS
        config = sampling.model_copy(update={"max_output_tokens": cap})
        return LlmRequest(
            model=model.model,
            contents=[types.Content(role="user", parts=[types.Part(text=text)])],
            config=config,
        )
    declaration = types.FunctionDeclaration(
        name=_PROBE_TOOL,
        description="Confirms that tool calls work. Takes no arguments.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    )
    request = LlmRequest(
        model=model.model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(text=f"Call the {_PROBE_TOOL} function now; do not reply in text.")
                ],
            )
        ],
        config=sampling.model_copy(
            update={
                "max_output_tokens": _TOOL_PROBE_OUTPUT_TOKENS,
                "tools": [types.Tool(function_declarations=[declaration])],
            }
        ),
    )
    if model.capabilities.output_schema_and_tools:
        request.set_output_schema(_PROBE_SCHEMA)
    return request


async def _send_probe(
    model: BaseLlm, request: LlmRequest, timeout: float
) -> tuple[LlmResponse | None, int]:
    """Send one non-streaming request; return the final complete response and latency."""
    started = time.perf_counter()
    final = None
    async with asyncio.timeout(timeout):
        async for response in model.generate_content_async(request, stream=False):
            if not response.partial:
                final = response
    return final, round((time.perf_counter() - started) * 1000)


def _output_tokens(response: LlmResponse) -> str:
    usage = response.usage_metadata
    count = None if usage is None else usage.candidates_token_count
    return "unknown" if count is None else str(count)


def _finish(response: LlmResponse) -> str:
    reason = response.finish_reason
    return "unreported" if reason is None else reason.name or str(reason)


def _text_probe_check(role: str, response: LlmResponse | None, latency_ms: int) -> dict:
    from google.genai import types

    name = f"model_{role}"
    if response is None:
        return {"name": name, "status": "fail", "detail": "No complete response was returned"}
    capped = response.finish_reason == types.FinishReason.MAX_TOKENS
    if response.error_code and not capped:
        return _response_failure(name, response)
    detail = (
        f"Answered in {latency_ms} ms; finish_reason={_finish(response)}; "
        f"output_tokens={_output_tokens(response)}"
    )
    if capped:
        detail += (
            f"; stopped at the {_TEXT_PROBE_OUTPUT_TOKENS}-token probe cap (reasoning tokens "
            "count against max_output_tokens; role caps are separate)"
        )
    return {"name": name, "status": "pass", "detail": safe_text(detail)}


def _tool_probe_check(response: LlmResponse | None, latency_ms: int, paired: bool) -> dict:
    """Pass only when the response is a native call of the one declared function."""
    from google.genai import types

    name = "model_producer_tools"
    if response is None:
        return {"name": name, "status": "fail", "detail": "No complete response was returned"}
    calls = [
        part.function_call.name
        for part in (response.content.parts or [] if response.content else [])
        if part.function_call is not None
    ]
    schema = "with" if paired else "without"
    if _PROBE_TOOL in calls:
        detail = (
            f"Function call {_PROBE_TOOL} returned in {latency_ms} ms, {schema} a paired "
            f"response schema; finish_reason={_finish(response)}"
        )
        return {"name": name, "status": "pass", "detail": safe_text(detail)}
    if calls:
        detail = f"Returned a call to an undeclared function in {latency_ms} ms"
        return {"name": name, "status": "fail", "detail": detail, "remedy": _TOOL_ROUTE_REMEDY}
    if response.finish_reason == types.FinishReason.MAX_TOKENS:
        detail = (
            f"No function call before the {_TOOL_PROBE_OUTPUT_TOKENS}-token probe cap "
            f"({latency_ms} ms); inconclusive, as a reasoning model may spend the cap first"
        )
        return {"name": name, "status": "warn", "detail": detail}
    if response.error_code and response.finish_reason != types.FinishReason.MALFORMED_FUNCTION_CALL:
        return _response_failure(name, response)
    detail = (
        f"Answered without a native function call in {latency_ms} ms, {schema} a paired "
        f"response schema; finish_reason={_finish(response)}"
    )
    return {
        "name": name,
        "status": "fail",
        "detail": safe_text(detail),
        "remedy": _TOOL_ROUTE_REMEDY,
    }


async def _probe_check(
    model: BaseLlm,
    role: str,
    *,
    tool: bool,
    timeout: float,
    decoding: types.GenerateContentConfig | None,
) -> dict:
    """Run one probe and turn any raised provider failure into a sanitized failed check."""
    name = "model_producer_tools" if tool else f"model_{role}"
    try:
        request = _probe_request(model, tool=tool, decoding=decoding)
        paired = request.config.response_schema is not None
        response, latency_ms = await _send_probe(model, request, timeout)
    except Exception as error:
        return _model_failure(name, error)
    if tool:
        return _tool_probe_check(response, latency_ms, paired)
    return _text_probe_check(role, response, latency_ms)


def _resolve_models(settings: Settings, resolve: ModelResolver) -> dict[str, BaseLlm]:
    """Build each role's model exactly as its agent does, without contacting the provider."""
    from google.adk.models.registry import LLMRegistry

    roles: tuple[RoleName, ...] = ("producer", "auditor")
    resolved: dict[str, BaseLlm] = {}
    for role in roles:
        model = resolve(settings, role)
        # LlmAgent.canonical_model resolves a plain model id through the same registry.
        resolved[role] = LLMRegistry.new_llm(model) if isinstance(model, str) else model
        # Capabilities load the provider SDK, so its import is never timed as request latency.
        _ = resolved[role].capabilities
    return resolved


async def diagnose_model(
    settings: Settings, *, resolve_model: ModelResolver | None = None
) -> list[dict]:
    """Check the configured model routes with minimal requests; never an agent prompt or source."""
    checks = [_model_config_check(settings), _model_credentials_check(settings)]
    try:
        from corsair.adapters.inference.models import decoding_config

        producer_decoding = decoding_config(settings.models.decoding.producer)
        auditor_decoding = decoding_config(settings.models.decoding.auditor)
        if resolve_model is None:
            from corsair.adapters.inference.models import model_for_role

            resolve_model = model_for_role
        models = await asyncio.to_thread(_resolve_models, settings, resolve_model)
    except Exception as error:
        checks.append(_model_failure("model_resolution", error))
        return checks
    timeout = settings.models.request_timeout_seconds + _PROBE_GRACE_SECONDS
    # LiteLLM prints help banners to stdout on provider errors; stdout carries only the receipt.
    with redirect_stdout(sys.stderr):
        checks.extend(
            await asyncio.gather(
                _probe_check(
                    models["producer"],
                    "producer",
                    tool=False,
                    timeout=timeout,
                    decoding=producer_decoding,
                ),
                _probe_check(
                    models["producer"],
                    "producer",
                    tool=True,
                    timeout=timeout,
                    decoding=producer_decoding,
                ),
                _probe_check(
                    models["auditor"],
                    "auditor",
                    tool=False,
                    timeout=timeout,
                    decoding=auditor_decoding,
                ),
            )
        )
    return checks
