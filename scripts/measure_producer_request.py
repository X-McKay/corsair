#!/usr/bin/env python3
"""Measure producer LLM requests rendered by native ADK for frozen fixture rows.

A dataset-wide wrapper over ``corsair.evaluation.preview`` (the engine behind
``corsair agent preview``): the production ``run_producer`` path renders each request
and a capturing model records it and abstains, so no provider is called and no target
code runs. ``corsair agent preview producer REQUEST --full`` prints one request whole.

Token counts are an approximation, ``ceil(bytes / 4)``, not a provider tokenizer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from google.adk.models.llm_request import LlmRequest

from corsair.evaluation.datasets import load_frozen_fixture
from corsair.evaluation.preview import load_request, text_size
from corsair.evaluation.preview import render_requests as render_role_requests
from corsair.evaluation.preview import request_sections as role_request_sections
from corsair.evaluation.scoring import dataset_root
from corsair.settings import Settings

DEFAULT_DATASETS = ("evals/datasets/producer-dev.json", "evals/datasets/producer-expanded.json")


def request_sections(request: LlmRequest) -> dict[str, str]:
    """Split one rendered producer request into the parts sent to the provider."""

    return role_request_sections("producer", request)


async def render_requests(
    request_path: Path, content: bytes, *, structured_tools: bool
) -> list[LlmRequest]:
    """Render one fixture's producer requests through the production path."""

    return await render_role_requests(
        "producer",
        load_request(request_path, content),
        Settings(),
        structured_tools=structured_tools,
    )


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
    args = parser.parse_args()
    paths = [Path(item).resolve() for item in args.datasets]
    rows = asyncio.run(measure(paths, structured_tools=args.structured_tools))
    print(json.dumps({"token_estimate": "ceil(bytes/4)", "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
