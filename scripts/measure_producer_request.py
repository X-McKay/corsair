#!/usr/bin/env python3
"""Measure producer LLM requests rendered by native ADK for frozen fixture rows.

The real production path (``run_producer``: factory, toolset, packet and ADK request
processors) renders each request; a capturing ``BaseLlm`` records it and abstains, so
no provider is called and no target code runs.

Token counts are an approximation, ``ceil(bytes / 4)``, not a provider tokenizer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.base_llm import LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, Field

from corsair.adapters.inference.adk import run_producer
from corsair.adapters.scm.local import prepare_case
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.producer.factory import producer_instruction
from corsair.agents.resources import load_runtime_skills
from corsair.contracts import InvestigationRequest, ProducerInput
from corsair.evaluation.agents import load_frozen_fixture
from corsair.evaluation.scoring import dataset_root
from corsair.settings import Settings
from corsair.steps.manifest import build_manifest

DEFAULT_DATASETS = ("evals/datasets/producer-dev.json", "evals/datasets/producer-expanded.json")
_ABSTAIN = {"kind": "no_grounded_candidate", "reason": "measurement only"}


class CapturingLlm(BaseLlm):
    """Record each native request and answer from a fixed script; never a provider."""

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
        if self.structured_tools:
            part = types.Part(text=json.dumps(_ABSTAIN))
        else:
            call = types.FunctionCall(name="set_model_response", args=dict(_ABSTAIN))
            part = types.Part(function_call=call)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


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
    corsair = producer_instruction(load_runtime_skills("producer"))
    if not system.startswith(corsair):
        raise ValueError("rendered system instruction does not start with the producer's own")
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
        "tool_declarations": _compact(declarations),
        "response_schema": response_schema,
        "user_packet": packet,
        "conversation": conversation if request.contents[1:] else "",
    }


async def render_requests(
    request_path: Path, content: bytes, *, structured_tools: bool
) -> list[LlmRequest]:
    """Render one fixture's producer requests through the production path."""

    with tempfile.TemporaryDirectory(prefix="corsair-measure-") as artifacts:
        settings = Settings(artifact_root=artifacts)
        store = ArtifactStore(Path(artifacts))
        request = normalize_request_sources(
            InvestigationRequest.model_validate_json(content), request_path
        )
        prepared = prepare_case(
            request.case,
            settings,
            store,
            build_manifest(request, settings, "fixture-only:no-native-execution"),
        )
        model = CapturingLlm(model="capturing-measurement", structured_tools=structured_tools)
        await run_producer(
            ProducerInput(
                run_id="measure-producer-request",
                prepared=prepared,
                budget=request.budget,
                round_index=1,
                llm_call_limit=request.budget.episode_llm_calls,
                tool_call_limit=request.budget.max_tool_calls,
            ),
            settings,
            store,
            model,
        )
    return model.requests


def dataset_fixtures(datasets: list[Path]) -> list[tuple[str, Path, bytes]]:
    """Return each distinct frozen producer input once, digest-verified, oracle unused."""

    fixtures: list[tuple[str, Path, bytes]] = []
    seen: set[str] = set()
    for dataset_path in datasets:
        dataset = json.loads(dataset_path.read_bytes())
        root = dataset_root(dataset_path)
        for entry in dataset["entries"]:
            if entry["case_id"] in seen:
                continue
            seen.add(entry["case_id"])
            input_path, content, _oracle = load_frozen_fixture(root, entry)
            fixtures.append((entry["case_id"], input_path, content))
    return fixtures


async def measure(datasets: list[Path], *, structured_tools: bool) -> list[dict[str, Any]]:
    """Measure the final rendered request of each fixture's scripted episode."""

    rows: list[dict[str, Any]] = []
    for case_id, input_path, content in dataset_fixtures(datasets):
        requests = await render_requests(input_path, content, structured_tools=structured_tools)
        sections = request_sections(requests[-1])
        rows.append(
            {
                "case_id": case_id,
                "request_index": len(requests),
                "sections": {name: text_size(text) for name, text in sections.items()},
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
        help="model declares output_schema_and_tools (response_schema replaces the "
        "set_model_response tool)",
    )
    parser.add_argument("--dump", help="write the first fixture's rendered sections here")
    args = parser.parse_args()
    paths = [Path(item).resolve() for item in args.datasets]
    rows = asyncio.run(measure(paths, structured_tools=args.structured_tools))
    print(json.dumps({"token_estimate": "ceil(bytes/4)", "rows": rows}, indent=2))
    if args.dump:
        _case_id, input_path, content = dataset_fixtures(paths)[0]
        requests = asyncio.run(
            render_requests(input_path, content, structured_tools=args.structured_tools)
        )
        sections = request_sections(requests[-1])
        Path(args.dump).write_text(
            "\n\n=====\n\n".join(f"[{name}]\n{text}" for name, text in sections.items()),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
