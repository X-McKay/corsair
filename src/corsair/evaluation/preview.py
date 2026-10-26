"""Model-free agent request preview: exactly what one role would receive, with sizes.

The production path (``run_producer`` or ``run_auditor``: role factory, toolset, packet
builder and ADK request processors) renders the role's request; a capturing ``BaseLlm``
records it and answers with a fixed abstention or review, so no provider is called, no
target code runs and no oracle is read. The rendered request is split into parts (the
role prompt, each preloaded procedure, text ADK appends, one part per declared tool, the
response schema, the packet) whatever tools the factory returns.

Sizes are UTF-8 bytes; ``approx_tokens`` is ``ceil(bytes / 4)``, not a provider tokenizer.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import tempfile
from collections.abc import AsyncGenerator, Mapping, Sequence
from pathlib import Path
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.base_llm import LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from google.genai import types
from pydantic import BaseModel, Field

from corsair.adapters.inference.adk import run_auditor, run_producer
from corsair.adapters.inference.models import model_for_role
from corsair.adapters.scm.local import prepare_case, read_source
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.resources import RoleName, load_runtime_skills, prompt_text
from corsair.contracts import (
    AuditInput,
    AuditOutput,
    Feedback,
    InvestigationRequest,
    PreparedCase,
    ProducerInput,
    Submission,
    digest,
)
from corsair.policies.target_binding import target_binding
from corsair.settings import ModelSettings, Settings
from corsair.steps.manifest import build_manifest

PREVIEW_SCHEMA = "corsair.agent-preview/1"
DIFF_SCHEMA = "corsair.agent-preview-diff/1"
TOKEN_ESTIMATE = "ceil(bytes/4)"
# Part kinds in request order; totals are reported per kind and for the whole request.
PART_KINDS = ("instruction", "tool", "response_schema", "packet", "conversation")
ROLES: tuple[RoleName, ...] = ("producer", "auditor")
_ABSTAIN = {"kind": "no_grounded_candidate", "reason": "preview only; no model was called"}
_REVIEW = {"decision": "INSUFFICIENT_CONTEXT", "rule": "R1", "reason": "preview only"}
_MANIFEST_IMAGE = "preview:no-native-execution"


class CapturingLlm(BaseLlm):
    """Record each native request and answer from a fixed script; never a provider.

    ``leading_calls`` are function calls answered, in order, before the fixed ``reply``;
    the reply goes through ``set_model_response`` when ADK declared that tool and as JSON
    text otherwise.
    """

    reply: dict[str, Any]
    structured_tools: bool = False
    leading_calls: list[dict[str, Any]] = Field(default_factory=list)
    requests: list[LlmRequest] = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.structured_tools)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.requests.append(llm_request)
        index = len(self.requests) - 1
        if index < len(self.leading_calls):
            scripted = self.leading_calls[index]
            call = types.FunctionCall(name=scripted["name"], args=dict(scripted["args"]))
            part = types.Part(function_call=call)
        elif "set_model_response" in declared_tool_names(llm_request):
            call = types.FunctionCall(name="set_model_response", args=dict(self.reply))
            part = types.Part(function_call=call)
        else:
            part = types.Part(text=json.dumps(self.reply))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def declared_tool_names(request: LlmRequest) -> list[str]:
    """Return the function names ADK declared to the provider for one request."""

    config = request.config or types.GenerateContentConfig()
    return [
        declaration.name or ""
        for tool in config.tools or []
        if isinstance(tool, types.Tool)
        for declaration in tool.function_declarations or []
    ]


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def size_of(byte_count: int) -> dict[str, int]:
    """Return a byte count and its ``ceil(bytes/4)`` token approximation."""

    return {"bytes": byte_count, "approx_tokens": math.ceil(byte_count / 4)}


def text_size(text: str) -> dict[str, int]:
    """Return UTF-8 bytes and the ``ceil(bytes/4)`` token approximation of ``text``."""

    return size_of(len(text.encode("utf-8")))


def _part(name: str, kind: str, text: str) -> dict[str, Any]:
    raw = text.encode("utf-8")
    return {
        "name": name,
        "kind": kind,
        **size_of(len(raw)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": text,
    }


def _schema_text(schema: object) -> str:
    """Render a configured response schema as compact JSON, whatever form ADK set."""

    if schema is None:
        return ""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return _compact(schema.model_json_schema())
    if isinstance(schema, BaseModel):
        return _compact(schema.model_dump(mode="json", exclude_none=True))
    return _compact(schema)


def _instruction_parts(role: RoleName, system: str) -> list[dict[str, Any]]:
    """Split the system instruction into the role prompt, each preloaded procedure and
    whatever ADK request processors appended after them."""

    prompt = prompt_text(role)
    if not system.startswith(prompt):
        raise ValueError(f"rendered system instruction does not start with the {role} prompt")
    parts = [_part("instruction.prompt", "instruction", prompt)]
    cursor = len(prompt)
    for skill in load_runtime_skills(role):
        found = system.find(skill.instructions, cursor)
        if found < 0:
            continue
        end = found + len(skill.instructions)
        parts.append(_part(f"instruction.skill.{skill.name}", "instruction", system[cursor:end]))
        cursor = end
    if system[cursor:]:
        parts.append(_part("instruction.adk", "instruction", system[cursor:]))
    return parts


def request_parts(role: RoleName, request: LlmRequest) -> list[dict[str, Any]]:
    """Split one rendered request into the parts sent to the provider, in request order."""

    config = request.config or types.GenerateContentConfig()
    parts = _instruction_parts(role, str(config.system_instruction or ""))
    parts.extend(
        _part(
            f"tool.{declaration.name}",
            "tool",
            _compact(declaration.model_dump(mode="json", exclude_none=True)),
        )
        for tool in config.tools or []
        if isinstance(tool, types.Tool)
        for declaration in tool.function_declarations or []
    )
    schema = _schema_text(config.response_schema) or _schema_text(config.response_json_schema)
    if schema:
        parts.append(_part("response_schema", "response_schema", schema))
    packet = "".join(
        part.text or "" for content in request.contents[:1] for part in content.parts or []
    )
    parts.append(_part("packet", "packet", packet))
    if request.contents[1:]:
        conversation = _compact(
            [content.model_dump(mode="json", exclude_none=True) for content in request.contents[1:]]
        )
        parts.append(_part("conversation", "conversation", conversation))
    return parts


def request_sections(role: RoleName, request: LlmRequest) -> dict[str, str]:
    """Group one request's parts into the sections the measurement scripts report.

    The Corsair instruction is the role prompt plus its preloaded procedures; the tool
    declarations are one compact JSON list, empty when no tool is declared.
    """

    parts = request_parts(role, request)

    def kind_text(kind: str) -> str:
        return "".join(part["text"] for part in parts if part["kind"] == kind)

    adk = [part for part in parts if part["name"] == "instruction.adk"]
    tools = [part["text"] for part in parts if part["kind"] == "tool"]
    return {
        "corsair_instruction": "".join(
            part["text"]
            for part in parts
            if part["kind"] == "instruction" and part["name"] != "instruction.adk"
        ),
        "adk_instruction": "".join(part["text"] for part in adk),
        "tool_declarations": "[" + ",".join(tools) + "]" if tools else "",
        "response_schema": kind_text("response_schema"),
        "user_packet": kind_text("packet"),
        "conversation": kind_text("conversation"),
    }


def part_totals(parts: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Sum part bytes per kind and for the whole request."""

    totals = {
        kind: size_of(sum(int(part["bytes"]) for part in parts if part["kind"] == kind))
        for kind in PART_KINDS
    }
    totals["request"] = size_of(sum(int(part["bytes"]) for part in parts))
    return totals


async def capture_producer(
    producer_input: ProducerInput,
    settings: Settings,
    store: ArtifactStore,
    *,
    structured_tools: bool,
    leading_calls: Sequence[Mapping[str, Any]] = (),
) -> list[LlmRequest]:
    """Run the production producer episode against a capturing model; return its requests."""

    model = CapturingLlm(
        model="corsair-preview",
        reply=_ABSTAIN,
        structured_tools=structured_tools,
        leading_calls=[dict(call) for call in leading_calls],
    )
    await run_producer(producer_input, settings, store, model)
    return model.requests


async def capture_auditor(
    audit_input: AuditInput, settings: Settings | ModelSettings, *, structured_tools: bool
) -> tuple[list[LlmRequest], AuditOutput]:
    """Run the production auditor episode against a capturing model."""

    model = CapturingLlm(model="corsair-preview", reply=_REVIEW, structured_tools=structured_tools)
    output = await run_auditor(audit_input, settings, model)
    return model.requests, output


def describe_route(
    settings: Settings, role: RoleName, structured_tools: bool | None
) -> dict[str, Any]:
    """Describe the role's configured model route without contacting it.

    Whether ADK pairs the response schema with tools natively, or declares a
    ``set_model_response`` tool instead, is the model's capability; ``structured_tools``
    overrides what the configured route reports.
    """

    models = settings.models
    if structured_tools is None:
        configured = model_for_role(settings, role)
        model = LLMRegistry.new_llm(configured) if isinstance(configured, str) else configured
        capable = model.capabilities.output_schema_and_tools
    else:
        capable = structured_tools
    return {
        "connector": models.connector,
        "model": getattr(models, role),
        "output_schema_and_tools": capable,
        "capability": "configured" if structured_tools is None else "override",
    }


def _prepare(
    request: InvestigationRequest, settings: Settings, store: ArtifactStore
) -> PreparedCase:
    """Admit the request's sources and refuse a case the workflow stops before any model."""

    prepared = prepare_case(
        request.case, settings, store, build_manifest(request, settings, _MANIFEST_IMAGE)
    )
    module_text = read_source(
        prepared.source, prepared.recipe.module_file, store, settings.source_limit_bytes
    )
    failure = target_binding(prepared.finding, prepared.recipe, module_text)
    if failure is not None:
        raise ValueError(
            f"agent preview: the workflow stops this case before any model request ({failure})"
        )
    return prepared


def _check_role_inputs(
    role: RoleName,
    request: InvestigationRequest,
    *,
    round_index: int,
    previous: Submission | None,
    feedback: Feedback | None,
    submission: Submission | None,
) -> None:
    if role not in ROLES:
        raise ValueError(f"agent preview: unknown role {role!r}; use producer or auditor")
    if role == "auditor":
        if submission is None:
            raise ValueError("agent preview: the auditor reviews a submission; pass --submission")
        if round_index != 1 or previous is not None or feedback is not None:
            raise ValueError(
                "agent preview: --round, --previous and --feedback are producer inputs; "
                "the auditor sees only the submission"
            )
        return
    if submission is not None:
        raise ValueError(
            "agent preview: --submission is the auditor's input; "
            "use --previous for a producer retry"
        )
    if not 1 <= round_index <= request.budget.max_rounds:
        raise ValueError(
            f"agent preview: --round must be between 1 and the request's max_rounds "
            f"({request.budget.max_rounds})"
        )
    if round_index == 1 and (previous is not None or feedback is not None):
        raise ValueError(
            "agent preview: round 1 never carries --previous or --feedback; pass --round 2"
        )


def load_request(request_path: Path, content: bytes | None = None) -> InvestigationRequest:
    """Validate one investigation request, resolving its sources relative to its file."""

    raw = request_path.read_bytes() if content is None else content
    return normalize_request_sources(InvestigationRequest.model_validate_json(raw), request_path)


async def render_requests(
    role: RoleName,
    request: InvestigationRequest,
    settings: Settings,
    *,
    structured_tools: bool,
    round_index: int = 1,
    previous: Submission | None = None,
    feedback: Feedback | None = None,
    submission: Submission | None = None,
    leading_calls: Sequence[Mapping[str, Any]] = (),
) -> list[LlmRequest]:
    """Run one role episode for ``request`` through the production path; return every
    request it sent to the capturing model.

    Sources are admitted into a throwaway artifact store; nothing is written to the
    configured ``artifact_root`` and no provider, container or oracle is touched.
    """

    _check_role_inputs(
        role,
        request,
        round_index=round_index,
        previous=previous,
        feedback=feedback,
        submission=submission,
    )
    with tempfile.TemporaryDirectory(prefix="corsair-preview-") as artifacts:
        scratch = settings.model_copy(update={"artifact_root": artifacts})
        store = ArtifactStore(Path(artifacts))
        prepared = _prepare(request, scratch, store)
        if role == "producer":
            return await capture_producer(
                ProducerInput(
                    run_id="agent-preview",
                    prepared=prepared,
                    budget=request.budget,
                    round_index=round_index,
                    previous=previous,
                    feedback=feedback,
                    llm_call_limit=request.budget.episode_llm_calls,
                    tool_call_limit=request.budget.max_tool_calls,
                ),
                scratch,
                store,
                structured_tools=structured_tools,
                leading_calls=leading_calls,
            )
        if submission is None:  # Refused by _check_role_inputs; narrows the type.
            raise ValueError("agent preview: the auditor reviews a submission; pass --submission")
        requests, _output = await capture_auditor(
            AuditInput(
                finding=prepared.finding,
                recipe=prepared.recipe,
                source_excerpt=prepared.source_excerpt,
                submission=submission,
                line_provenance=prepared.line_provenance,
                max_output_tokens=request.budget.max_output_tokens,
            ),
            scratch,
            structured_tools=structured_tools,
        )
        return requests


async def preview_request(
    role: RoleName,
    request_path: Path,
    settings: Settings,
    *,
    round_index: int = 1,
    previous: Submission | None = None,
    feedback: Feedback | None = None,
    submission: Submission | None = None,
    structured_tools: bool | None = None,
) -> dict[str, Any]:
    """Render the first request ``role`` would receive for one investigation request."""

    request = load_request(request_path)
    described = describe_route(settings, role, structured_tools)
    requests = await render_requests(
        role,
        request,
        settings,
        structured_tools=bool(described["output_schema_and_tools"]),
        round_index=round_index,
        previous=previous,
        feedback=feedback,
        submission=submission,
    )
    if not requests:
        raise ValueError(f"agent preview: the {role} episode sent no model request")
    return build_preview(
        role,
        requests[0],
        inputs={
            "request": str(request_path),
            "case_id": request.case.case_id,
            "round": round_index,
            "previous_submission": None if previous is None else digest(previous),
            "feedback_gate": None if feedback is None else feedback.gate,
            "submission": None if submission is None else digest(submission),
        },
        route=described,
    )


def build_preview(
    role: RoleName,
    request: LlmRequest,
    *,
    inputs: Mapping[str, Any],
    route: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the JSON preview of one captured request."""

    config = request.config or types.GenerateContentConfig()
    parts = request_parts(role, request)
    return {
        "schema_version": PREVIEW_SCHEMA,
        "role": role,
        "inputs": dict(inputs),
        "route": dict(route),
        "generation": {
            "max_output_tokens": config.max_output_tokens,
            "response_mime_type": config.response_mime_type,
        },
        "token_estimate": TOKEN_ESTIMATE,
        "declared_tools": declared_tool_names(request),
        "parts": parts,
        "totals": part_totals(parts),
        "request_sha256": hashlib.sha256(
            "".join(part["text"] for part in parts).encode("utf-8")
        ).hexdigest(),
    }


def load_preview(path: Path) -> dict[str, Any]:
    """Read a preview saved with ``--output`` or ``--format json``."""

    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or value.get("schema_version") != PREVIEW_SCHEMA:
        raise ValueError(
            f"agent preview: {path} is not a saved {PREVIEW_SCHEMA} preview; "
            "save one with --output or --format json"
        )
    return value


def _diff_lines(text: str) -> list[str]:
    """Lines for a readable unified diff; a line holding JSON is pretty-printed."""

    lines: list[str] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            lines.append(line)
            continue
        if isinstance(value, dict | list):
            lines.extend(
                json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
            )
        else:
            lines.append(line)
    return lines


def _field(part: Mapping[str, Any] | None, key: str) -> int | None:
    return None if part is None else int(part[key])


def _delta(before: int | None, after: int | None) -> dict[str, int | None]:
    return {
        "baseline": before,
        "candidate": after,
        "delta": (after or 0) - (before or 0),
    }


def diff_previews(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two previews of the same role part by part."""

    for value in (baseline, candidate):
        if value.get("schema_version") != PREVIEW_SCHEMA:
            raise ValueError(f"agent preview: --diff compares two {PREVIEW_SCHEMA} previews")
    if baseline["role"] != candidate["role"]:
        raise ValueError(
            f"agent preview: --diff compares one role; baseline is {baseline['role']}, "
            f"candidate is {candidate['role']}"
        )
    before = {part["name"]: part for part in baseline["parts"]}
    after = {part["name"]: part for part in candidate["parts"]}
    names = [*after, *(name for name in before if name not in after)]
    rows: list[dict[str, Any]] = []
    for name in names:
        old, new = before.get(name), after.get(name)
        if old is None:
            status = "added"
        elif new is None:
            status = "removed"
        else:
            status = "unchanged" if old["sha256"] == new["sha256"] else "changed"
        row: dict[str, Any] = {
            "name": name,
            "kind": (new if new is not None else old or {})["kind"],
            "status": status,
            "bytes": _delta(_field(old, "bytes"), _field(new, "bytes")),
            "approx_tokens": _delta(_field(old, "approx_tokens"), _field(new, "approx_tokens")),
        }
        if status != "unchanged":
            row["unified_diff"] = "\n".join(
                difflib.unified_diff(
                    _diff_lines(old["text"]) if old else [],
                    _diff_lines(new["text"]) if new else [],
                    fromfile=f"baseline/{name}",
                    tofile=f"candidate/{name}",
                    lineterm="",
                    n=2,
                )
            )
        rows.append(row)
    totals = {
        key: {
            "bytes": _delta(baseline["totals"][key]["bytes"], candidate["totals"][key]["bytes"]),
            "approx_tokens": _delta(
                baseline["totals"][key]["approx_tokens"],
                candidate["totals"][key]["approx_tokens"],
            ),
        }
        for key in (*PART_KINDS, "request")
    }
    return {
        "schema_version": DIFF_SCHEMA,
        "role": candidate["role"],
        "baseline": {**baseline["inputs"], "request_sha256": baseline["request_sha256"]},
        "candidate": {**candidate["inputs"], "request_sha256": candidate["request_sha256"]},
        "changed": baseline["request_sha256"] != candidate["request_sha256"],
        "token_estimate": TOKEN_ESTIMATE,
        "parts": rows,
        "totals": totals,
    }
