#!/usr/bin/env python3
"""Measure auditor LLM requests rendered by native ADK for frozen auditor fixture rows.

The real production path (``run_auditor``: factory, packet and ADK request processors)
renders each request; a capturing ``BaseLlm`` records it and returns a fixed
``INSUFFICIENT_CONTEXT`` review, so no provider is called and no target code runs. The
reply goes through ``set_model_response`` when ADK declared that tool (a model without
``output_schema_and_tools`` that also has tools, as on the LiteLLM route) and as plain
JSON text otherwise.

Token counts are an approximation, ``ceil(bytes / 4)``, not a provider tokenizer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.base_llm import LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, Field

from corsair.adapters.inference.adk import run_auditor
from corsair.agents.auditor.factory import auditor_instruction
from corsair.agents.resources import load_runtime_skills
from corsair.contracts import AuditInput, AuditOutput
from corsair.evaluation.agents import load_frozen_fixture
from corsair.evaluation.scoring import dataset_root
from corsair.settings import ModelSettings

DEFAULT_DATASETS = ("evals/datasets/auditor-dev.json", "evals/datasets/auditor-expanded.json")
_REVIEW = {"decision": "INSUFFICIENT_CONTEXT", "rule": "R1", "reason": "measurement only"}


class CapturingLlm(BaseLlm):
    """Record each native request and answer with one fixed review; never a provider."""

    structured_tools: bool = False
    requests: list[LlmRequest] = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.structured_tools)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.requests.append(llm_request)
        if "set_model_response" in declared_tool_names(llm_request):
            call = types.FunctionCall(name="set_model_response", args=dict(_REVIEW))
            part = types.Part(function_call=call)
        else:
            part = types.Part(text=json.dumps(_REVIEW))
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


def text_size(text: str) -> dict[str, int]:
    """Return UTF-8 bytes and the ceil(bytes/4) token approximation."""

    raw = len(text.encode("utf-8"))
    return {"bytes": raw, "approx_tokens": math.ceil(raw / 4)}


def request_sections(request: LlmRequest) -> dict[str, str]:
    """Split one rendered request into the parts sent to the provider."""

    config = request.config or types.GenerateContentConfig()
    system = str(config.system_instruction or "")
    corsair = auditor_instruction(load_runtime_skills("auditor"))
    if not system.startswith(corsair):
        raise ValueError("rendered system instruction does not start with the auditor's own")
    declarations = [
        declaration.model_dump(mode="json", exclude_none=True)
        for tool in config.tools or []
        if isinstance(tool, types.Tool)
        for declaration in tool.function_declarations or []
    ]
    schema = config.response_schema
    response_schema = (
        _compact(schema.model_json_schema())
        if isinstance(schema, type) and issubclass(schema, BaseModel)
        else ""
    )
    packet = "".join(
        part.text or "" for content in request.contents[:1] for part in content.parts or []
    )
    conversation = _compact(
        [content.model_dump(mode="json", exclude_none=True) for content in request.contents[1:]]
    )
    return {
        "corsair_instruction": corsair,
        "adk_instruction": system.removeprefix(corsair),
        "tool_declarations": _compact(declarations) if declarations else "",
        "response_schema": response_schema,
        "user_packet": packet,
        "conversation": conversation if request.contents[1:] else "",
    }


async def render_requests(
    content: bytes, *, structured_tools: bool
) -> tuple[list[LlmRequest], AuditOutput]:
    """Render one fixture's auditor requests through the production path."""

    model = CapturingLlm(model="capturing-measurement", structured_tools=structured_tools)
    output = await run_auditor(AuditInput.model_validate_json(content), ModelSettings(), model)
    return model.requests, output


def dataset_fixtures(datasets: list[Path]) -> list[tuple[str, bytes]]:
    """Return each distinct frozen auditor input once, digest-verified, oracle unused."""

    fixtures: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for dataset_path in datasets:
        dataset = json.loads(dataset_path.read_bytes())
        root = dataset_root(dataset_path)
        for entry in dataset["entries"]:
            if entry["case_id"] in seen:
                continue
            seen.add(entry["case_id"])
            _input_path, content, _oracle = load_frozen_fixture(root, entry)
            fixtures.append((entry["case_id"], content))
    return fixtures


async def measure(datasets: list[Path], *, structured_tools: bool) -> list[dict[str, Any]]:
    """Measure the first rendered request and the episode usage of each fixture."""

    rows: list[dict[str, Any]] = []
    for case_id, content in dataset_fixtures(datasets):
        requests, output = await render_requests(content, structured_tools=structured_tools)
        sections = request_sections(requests[0])
        rows.append(
            {
                "case_id": case_id,
                "requests": len(requests),
                "llm_calls": output.usage.llm_calls,
                "tool_calls": output.usage.tool_calls,
                "declared_tools": declared_tool_names(requests[0]),
                "review_parsed": output.review is not None,
                "sections": {name: text_size(text) for name, text in sections.items()},
                "system_and_tools": text_size(
                    sections["corsair_instruction"]
                    + sections["adk_instruction"]
                    + sections["tool_declarations"]
                ),
                "total": text_size("".join(sections.values())),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", nargs="*", default=list(DEFAULT_DATASETS))
    parser.add_argument(
        "--structured-tools",
        action="store_true",
        help="model declares output_schema_and_tools (native Gemini); the default models "
        "the LiteLLM route, where ADK replaces the schema with set_model_response if tools exist",
    )
    parser.add_argument("--dump", help="write the first fixture's rendered sections here")
    args = parser.parse_args()
    paths = [Path(item).resolve() for item in args.datasets]
    rows = asyncio.run(measure(paths, structured_tools=args.structured_tools))
    print(json.dumps({"token_estimate": "ceil(bytes/4)", "rows": rows}, indent=2))
    if args.dump:
        _case_id, content = dataset_fixtures(paths)[0]
        requests, _output = asyncio.run(
            render_requests(content, structured_tools=args.structured_tools)
        )
        sections = request_sections(requests[0])
        Path(args.dump).write_text(
            "\n\n=====\n\n".join(f"[{name}]\n{text}" for name, text in sections.items()),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
