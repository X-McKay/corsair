#!/usr/bin/env python3
"""Measure auditor LLM requests rendered by native ADK for frozen auditor fixture rows.

A dataset-wide wrapper over ``corsair.evaluation.preview`` (the engine behind
``corsair agent preview``): the production ``run_auditor`` path renders each request
and a capturing model records it and returns a fixed ``INSUFFICIENT_CONTEXT`` review,
so no provider is called and no target code runs. The reply goes through
``set_model_response`` when ADK declared that tool and as plain JSON text otherwise.

Token counts are an approximation, ``ceil(bytes / 4)``, not a provider tokenizer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from google.adk.models.llm_request import LlmRequest

from corsair.contracts import AuditInput, AuditOutput
from corsair.evaluation.datasets import load_frozen_fixture
from corsair.evaluation.preview import capture_auditor, declared_tool_names, text_size
from corsair.evaluation.preview import request_sections as role_request_sections
from corsair.evaluation.scoring import dataset_root
from corsair.settings import ModelSettings

DEFAULT_DATASETS = ("evals/datasets/auditor-dev.json", "evals/datasets/auditor-expanded.json")


def request_sections(request: LlmRequest) -> dict[str, str]:
    """Split one rendered auditor request into the parts sent to the provider."""

    return role_request_sections("auditor", request)


async def render_requests(
    content: bytes, *, structured_tools: bool
) -> tuple[list[LlmRequest], AuditOutput]:
    """Render one fixture's auditor requests through the production path."""

    return await capture_auditor(
        AuditInput.model_validate_json(content), ModelSettings(), structured_tools=structured_tools
    )


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
    args = parser.parse_args()
    paths = [Path(item).resolve() for item in args.datasets]
    rows = asyncio.run(measure(paths, structured_tools=args.structured_tools))
    print(json.dumps({"token_estimate": "ceil(bytes/4)", "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
