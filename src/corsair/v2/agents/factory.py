"""Construction-time factory for Corsair v2's six native cognitive roles."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model
from pydantic_ai_harness import ClearToolResults, FileSystem, Planning, ToolOutputLimits
from pydantic_ai_harness.planning import SqlitePlanStore
from pydantic_ai_harness.skills import Skills
from pydantic_ai_harness.tool_output_limits import Band, Truncate
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from ..contracts import (
    InvestigationPlan,
    OperatorConfig,
    ProbeDraft,
    RepairDraft,
    SourceAssessment,
    ValidityReview,
    digest,
)
from ..telemetry import instrumentation
from .dependencies import AgentDeps
from .models import build_model
from .prompts import ROLE_SPECS, ROLES, Role, skill_id
from .validation import validate_role_output
from .workspace import SourceWorkspaceCapability

_AGENT_NAMES: dict[Role, str] = {role: f"corsair.v2.{role}.v1" for role in ROLES}
_MODEL_IDS: dict[Role, str] = {role: f"corsair.v2.{role}.model.v1" for role in ROLES}
_OUTPUT_TYPES: dict[Role, type[Any]] = {
    "analysis": SourceAssessment,
    "investigator": InvestigationPlan,
    "control_author": ProbeDraft,
    "exploit_author": ProbeDraft,
    "validity": ValidityReview,
    "repair": RepairDraft,
}
_SOURCE_FILE_TOOLS = ("read_file", "list_directory", "search_files", "find_files", "file_info")
_SOURCE_DENY_PATTERNS = (
    ".env", "**/.env", "**/.env.*", "*.pem", "**/*.pem", "*.key", "**/*.key", "*.p12", "**/*.p12",
    "*.pfx", "**/*.pfx", "**/secrets*", "**/*credentials*", "**/id_rsa", "**/id_ed25519",
)


def _plan_store_resolver(storage_root: str):
    database = str(Path(storage_root).expanduser().absolute() / "agent-plans.sqlite3")

    def resolve(ctx):  # type: ignore[no-untyped-def]
        # Constructor is side-effect free; actual SQL operations are native
        # Planning durable operations. Session identity is stable across replay.
        return SqlitePlanStore(database, session=f"{ctx.deps.run_id}:{ctx.deps.stage_id}")

    return resolve


def _capabilities(config: OperatorConfig, role: Role, model: Model, durable: bool) -> list[object]:
    values: list[object] = [
        SourceWorkspaceCapability(config.storage_root),
        # The primary workspace is the managed workspace root; Filesystem is
        # explicitly narrowed to its ``source`` child. Skills reads only the
        # fixed sibling bundle by an exact package-owned identifier.
        Skills("../operator-skills", include={skill_id(role)}),
        FileSystem(
            # Harness 0.55.0 rejects ``root_dir='source'`` before a custom
            # capability can report its source working directory. The
            # workspace itself reports the immutable ``source`` child as cwd,
            # so None is the SDK's native spelling for exactly that root.
            root_dir=None,
            allowed_patterns=("*", "**"),
            denied_patterns=_SOURCE_DENY_PATTERNS,
            read_only=True,
            tools=_SOURCE_FILE_TOOLS,
            max_read_lines=1200,
            max_read_chars=16_384,
            max_list_results=512,
            max_search_results=256,
            max_find_results=256,
            id="corsair.v2.source-files.v1",
        ),
        ToolOutputLimits(
            bands=[Band(over=8_000, action=Truncate(max_chars=8_000))],
            id="corsair.v2.tool-output-limits.v1",
        ),
        ClearToolResults(max_tokens=12_000, keep_pairs=2, id="corsair.v2.clear-tool-results.v1"),
        instrumentation(capture_content=config.capture_content),
    ]
    if role == "investigator":
        values.insert(3, Planning(
            tools=["write_plan", "read_plan"],
            store_resolver=_plan_store_resolver(config.storage_root),
            id="corsair.v2.investigator-planning.v1",
        ))
    if durable:
        values.append(TemporalDurability(
            models={_MODEL_IDS[role]: model},
            name=_AGENT_NAMES[role],
            deps_type=AgentDeps,
            activity_config=ActivityConfig(
                start_to_close_timeout=timedelta(seconds=config.budget.stage_timeout_seconds),
                retry_policy=RetryPolicy(maximum_attempts=1),
            ),
            model_activity_config=ActivityConfig(
                start_to_close_timeout=timedelta(seconds=config.budget.stage_timeout_seconds),
                retry_policy=RetryPolicy(maximum_attempts=1),
            ),
        ))
    return values


def _build_role(config: OperatorConfig, role: Role, *, durable: bool, model_override: Model | None) -> Agent:
    model = model_override if model_override is not None else build_model(config.model_for(role), config.budget)
    if not isinstance(model, Model):
        raise TypeError("model_override must be an explicit native PydanticAI Model")
    agent = Agent.from_spec(
        ROLE_SPECS[role],
        model=model,
        name=_AGENT_NAMES[role],
        deps_type=AgentDeps,
        output_type=_OUTPUT_TYPES[role],
        model_settings={},
        retries={"output": min(1, config.budget.max_plan_revisions), "tools": 1},
        capabilities=_capabilities(config, role, model, durable),
    )

    @agent.output_validator
    def _authority(ctx, output):  # type: ignore[no-untyped-def]
        return validate_role_output(ctx, output, role)

    @agent.instructions
    def _completion_contract(ctx):  # type: ignore[no-untyped-def]
        return ("Finish by calling the final_result output tool with the declared typed fields. "
                "Do not return a prose answer or Markdown. File names alone are not file contents; "
                "use the read-only tools whenever source bytes are not present in the authorized input.")

    return agent


def build_agents(config: OperatorConfig, durable: bool = False, model_override: Model | None = None) -> dict[str, Agent]:
    """Build all static role agents before a worker/workflow starts.

    There is no model/provider fallback.  ``model_override`` is a test seam for
    native TestModel/FunctionModel and must never be supplied by production
    runtime configuration.
    """
    if not isinstance(config, OperatorConfig):
        raise ValueError("A v2 OperatorConfig is required")  # noqa: TRY004 - invalid admission is consistently ValueError
    if not isinstance(durable, bool):
        raise ValueError("durable must be a boolean")  # noqa: TRY004 - invalid admission is consistently ValueError
    models = {}
    agents = {}
    for role in ROLES:
        key = digest(config.model_for(role))
        if key not in models:
            models[key] = model_override if model_override is not None else build_model(config.model_for(role), config.budget)
        agents[role] = _build_role(config, role, durable=durable, model_override=models[key])
    return agents


async def close_agents(agents) -> None:
    """Close unique owned native provider clients after the agent set stops."""
    seen = set()
    for agent in agents.values():
        model = agent.model
        if id(model) in seen:
            continue
        seen.add(id(model))
        close = getattr(model, "aclose", None)
        if close is not None:
            await close()


__all__ = ["build_agents", "close_agents"]
