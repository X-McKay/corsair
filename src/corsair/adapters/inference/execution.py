"""One native ADK episode per recipe-free role; Temporal owns all revisions."""

from __future__ import annotations

import asyncio
import json
import time
from importlib.resources import files

from google.adk.models import BaseLlm
from pydantic import ValidationError

from corsair.adapters.inference.adk import _EpisodeAccounting, _run_native_episode
from corsair.adapters.inference.models import model_for_role
from corsair.agents.auditor.execution import build_execution_auditor
from corsair.agents.producer.execution import build_execution_producer
from corsair.contracts import digest
from corsair.contracts.execution import ExecutionEpisode, ExecutionRoundInput, PlanAudit, TestPlan
from corsair.ports.intake import InspectionReader
from corsair.settings import Settings


class GroundedReader:
    def __init__(self, reader: InspectionReader):
        self.reader = reader
        self.paths: set[str] = set()

    def read(self, operation: str, relative: str = "") -> dict:
        record = self.reader.read(operation, relative)
        if (
            operation == "read"
            and isinstance(record.get("content"), str)
            and not record.get("truncated")
        ):
            self.paths.add(relative)
        return record


async def preload_source(
    reader: GroundedReader, item: ExecutionRoundInput, paths: list[str], *, maximum_files: int = 4
) -> tuple[list[dict], int]:
    listing = await asyncio.to_thread(reader.read, "list")
    available = listing.get("files", [])
    if not isinstance(available, list) or any(not isinstance(path, str) for path in available):
        raise ValueError("invalid sandbox source listing")
    prioritized = sorted(available, key=lambda path: (path not in paths, path))
    context = []
    remaining = item.prepared.request.budget.tool_output_bytes
    calls = 1
    for path in prioritized[: min(maximum_files, max(0, item.tool_limit - 2))]:
        record = await asyncio.to_thread(reader.read, "read", path)
        calls += 1
        text = record.get("content")
        if not isinstance(text, str):
            context.append({"path": path, "error": "READ_UNAVAILABLE"})
            continue
        encoded = text.encode()
        truncated = len(encoded) > remaining or bool(record.get("truncated"))
        text = encoded[:remaining].decode("utf-8", errors="ignore")
        remaining -= len(text.encode())
        context.append({"path": path, "content": text, "truncated": truncated})
        if truncated:
            reader.paths.discard(path)
        if remaining <= 0:
            break
    return context, calls


def execution_resources_digest() -> str:
    resources = {}
    for package, names in {
        "corsair.agents.producer": ["execution.py", "execution.json", "instructions/execution.md"],
        "corsair.agents.auditor": ["execution.py", "execution.json", "instructions/execution.md"],
        "corsair.adapters.inference": ["execution.py", "adk.py"],
        "corsair.adapters.sandboxing": ["execution.py", "inspection.py", "inspection_reader.py"],
        "corsair.policies": ["execution.py", "risk.md"],
    }.items():
        for name in names:
            resources[f"{package}:{name}"] = digest(files(package).joinpath(name).read_bytes())
    from corsair.contracts.execution import ExecutionRequest, ExecutionResult

    resources["schema"] = digest(
        [
            model.model_json_schema()
            for model in (
                ExecutionRequest,
                ExecutionResult,
                TestPlan,
                PlanAudit,
            )
        ]
    )
    return digest(resources)


async def _episode(
    item: ExecutionRoundInput,
    settings: Settings,
    reader: InspectionReader,
    plan: TestPlan | None,
    model_override: str | BaseLlm | None,
) -> ExecutionEpisode:
    started = time.perf_counter()
    role = "producer" if plan is None else "auditor"
    tracked = GroundedReader(reader)
    paths = [
        location.path
        for location in (item.prepared.request.issue.locations if plan is None else plan.locations)
    ]
    if item.tool_limit < 3:
        return ExecutionEpisode(error="BUDGET_EXHAUSTED")
    context, preload_calls = await preload_source(
        tracked, item, paths, maximum_files=4 if plan is None else 16
    )
    if plan is not None and any(path not in tracked.paths for path in paths):
        from corsair.contracts import Usage

        return ExecutionEpisode(
            error="SOURCE_UNGROUNDED",
            source_paths=sorted(tracked.paths),
            usage=Usage(tool_calls=preload_calls, seconds=time.perf_counter() - started),
        )
    packet: dict = {
        "issue": item.prepared.request.issue.model_dump(mode="json"),
        "source_context": context,
        "selected_image": item.prepared.request.image.model_dump(mode="json"),
    }
    if plan is None:
        packet.update(
            {
                "revision": item.revision,
                "parent_revision": None if item.revision == 1 else item.revision - 1,
            }
        )
        if item.previous is not None:
            previous = item.previous
            packet["previous_plan"] = (
                None if previous.plan is None else previous.plan.model_dump(mode="json")
            )
            packet["previous_audit"] = (
                None if previous.audit is None else previous.audit.model_dump(mode="json")
            )
            packet["previous_error"] = previous.error
            if previous.observation is not None:
                packet["mechanical_feedback"] = [
                    {"state": receipt.state, "exit_code": receipt.exit_code}
                    for receipt in previous.observation.receipts
                ]
    else:
        packet["plan"] = plan.model_dump(mode="json")
    message = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(message.encode()) > 524288:
        return ExecutionEpisode(error="OUTPUT_INVALID")
    model = model_for_role(settings, role) if model_override is None else model_override
    agent = (
        build_execution_producer(model, tracked) if plan is None else build_execution_auditor(model)
    )
    accounting = _EpisodeAccounting(
        max_llm_calls=min(item.llm_limit, 4),
        max_output_tokens=item.prepared.request.budget.max_output_tokens,
        max_tool_calls=item.tool_limit - preload_calls,
        role=role,
    )
    text, feedback = await _run_native_episode(
        agent=agent,
        app_name=f"corsair-execution-{role}",
        user_id=item.prepared.run_id,
        session_id=f"{role}-{item.revision}",
        message=message,
        author=role,
        llm_call_limit=accounting.max_llm_calls,
        timeout_seconds=item.seconds,
        accounting=accounting,
    )
    usage = accounting.usage(time.perf_counter() - started)
    # Root tool budget includes mandatory sandbox reads; role diagnostics separate their origin.
    usage = usage.model_copy(update={"tool_calls": usage.tool_calls + preload_calls})
    result = ExecutionEpisode(
        usage=usage,
        source_paths=sorted(tracked.paths),
        completion_errors=accounting.completion_errors,
    )
    if feedback is not None:
        return result.model_copy(update={"error": "MODEL_FAILED"})
    if accounting.llm_limit_exhausted or accounting.tool_limit_exhausted:
        return result.model_copy(update={"error": "BUDGET_EXHAUSTED"})
    try:
        if text is None:
            raise ValueError("no output")
        output = (
            TestPlan.model_validate_json(text)
            if plan is None
            else PlanAudit.model_validate_json(text)
        )
    except ValueError as error:
        counts = dict(result.completion_errors)
        if isinstance(error, ValidationError):
            for item_error in error.errors(include_input=False, include_context=False):
                category = item_error["type"]
                if category in counts or len(counts) < 32:
                    counts[category] = counts.get(category, 0) + 1
        else:
            counts["NO_STRUCTURED_OUTPUT"] = 1
        return result.model_copy(update={"error": "OUTPUT_INVALID", "completion_errors": counts})
    if isinstance(output, TestPlan):
        if output.revision != item.revision:
            return result.model_copy(update={"error": "OUTPUT_INVALID"})
        if any(location.path not in tracked.paths for location in output.locations):
            return result.model_copy(update={"error": "SOURCE_UNGROUNDED"})
        return result.model_copy(update={"plan": output})
    if (
        plan is not None
        and output.decision == "accepted"
        and any(location.path not in tracked.paths for location in plan.locations)
    ):
        return result.model_copy(update={"error": "SOURCE_UNGROUNDED"})
    return result.model_copy(update={"audit": output})


async def run_execution_producer(
    item: ExecutionRoundInput,
    settings: Settings,
    reader: InspectionReader,
    model_override: str | BaseLlm | None = None,
) -> ExecutionEpisode:
    return await _episode(item, settings, reader, None, model_override)


async def run_execution_auditor(
    item: ExecutionRoundInput,
    plan: TestPlan,
    settings: Settings,
    reader: InspectionReader,
    model_override: str | BaseLlm | None = None,
) -> ExecutionEpisode:
    return await _episode(item, settings, reader, plan, model_override)
