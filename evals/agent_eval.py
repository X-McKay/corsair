"""Shared runner for a v2 agent's isolated eval: ``python -m corsair.v2.agents.<agent>.evals.evaluate``.

Each v2 agent's ``evals/evaluate.py`` declares one ``AgentEval`` and calls ``main``. The runner owns everything that
must mean the same for every agent:

- cases come from the agent's frozen sets (``evals.cases.load_set`` on ``agent_root``), optionally one language;
- each attempt runs the agent's real stage once, in a fresh working directory, with native Pydantic Evals
  (``Dataset.evaluate``, ``repeat``, one at a time); scripted mode replays the case oracle through the agent's own
  ``FunctionModel`` with real requests blocked, live mode uses ``corsair.v2.models`` for that agent's profile;
- every assertion is tagged with exactly one dimension (``AgentEval.dimensions``) so the summary can roll accuracy up
  per eval type, language and case kind;
- efficiency comes from the stage's ``AgentUsage``: a value the provider did not report stays null, never zero.

Evidence written under ``--evidence``: ``configuration.json`` (identity), ``attempts.jsonl`` (one row per attempt,
the input of ``evals/run.py``'s summary.json) and ``receipts/<n>.json`` (output, usage, messages per attempt).
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any

from pydantic import BaseModel, TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from corsair.v2.contracts import AgentUsage
from evals.cases import DIMENSIONS, LANGUAGES, EvalCase, agent_root, load_set, set_digest

SCHEMA = "corsair-agent-attempts/v1"
USAGE_FIELDS = ("requests", "tool_calls", "input_tokens", "output_tokens")
# Attempt.facts keys copied into the attempt row when an agent reports them (D3 corrections: at most two revisions
# per probe author, three reviews in total).
ROW_FACTS = ("revisions", "accepted_within_limit")
# Chain dispositions (evals/agent_summary.py dispositions): copied into the row only when the attempt reports them.
LABEL_FACTS = ("label", "expected_label", "terminal_reason")


@dataclass
class Attempt:
    """What one run of the stage produced; ``facts`` carries anything else the checks read (paths read, files)."""
    output: Any
    usage: AgentUsage | None
    facts: dict[str, Any] = field(default_factory=dict)
    messages: list[ModelMessage] = field(default_factory=list)


@dataclass(frozen=True)
class AgentEval:
    agent: str
    # assertion name -> dimension; every name ``check`` returns must be listed here, and nothing else
    dimensions: Mapping[str, str]
    # run the agent's stage once for this case in ``workdir`` (fresh, empty) with ``model``
    run: Callable[[EvalCase, Model, Path], Awaitable[Attempt]]
    # deterministic checks over the attempt and the case oracle; never calls a model
    check: Callable[[EvalCase, Attempt], Mapping[str, bool]]
    # the oracle-replay model for scripted mode
    scripted: Callable[[EvalCase], Model]
    # prompt_version, skill_sha256, toolset_sha256 ... recorded in configuration.json
    identity: Mapping[str, Any] = field(default_factory=dict)
    # the eval root; None means the agent's own package evals/ (evals.cases.agent_root)
    root: Path | None = None
    # assertions ``check`` may leave out when they do not apply to an attempt (e.g. no citation to resolve)
    optional: frozenset[str] = frozenset()
    # live mode: build these agents' models and hand ``run`` the mapping (a composition, e.g. the chain); empty means
    # this one agent's model
    live_agents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = set(self.dimensions.values()) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"{self.agent}: unknown dimensions {sorted(unknown)}")


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return TypeAdapter(Any).dump_python(value, mode="json")


class _Checks(Evaluator):
    def __init__(self, spec: AgentEval):
        self.spec = spec

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, bool]:
        values = dict(self.spec.check(ctx.metadata, ctx.output))
        declared = set(self.spec.dimensions)
        if not declared - set(self.spec.optional) <= set(values) <= declared:
            raise ValueError(f"{self.spec.agent}: checks returned {sorted(values)}, declared "
                             f"{sorted(self.spec.dimensions)}")
        return values


@asynccontextmanager
async def _live_model(spec: AgentEval, provider_config: Path):
    from corsair.v2.models import agent_models, load_provider_config
    agents = spec.live_agents or (spec.agent,)
    async with agent_models(load_provider_config(provider_config), agents) as built:
        yield dict(built) if spec.live_agents else built[spec.agent]


def _model_name(model: Any) -> Any:
    if isinstance(model, Mapping):
        return {name: getattr(item, "model_name", None) for name, item in model.items()}
    return getattr(model, "model_name", None)


def provider_identity(provider_config: Path, agents: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Per agent: the operator profile it resolved to (name, endpoint, served model). No credential is read."""
    from corsair.v2.models import load_provider_config
    config = load_provider_config(provider_config)
    return {agent: {"profile": config.agents[agent], "base_url": config.profile(agent).base_url,
                    "model_name": config.profile(agent).model_name} for agent in agents}


async def evaluate(spec: AgentEval, evidence: Path, set_name: str, *, language: str | None = None,
                   repeat: int = 1, model: Model | None = None, provider: Mapping[str, Any] | None = None) -> bool:
    """Run every case of ``set_name`` ``repeat`` times; True when every attempt passed every check."""
    root = spec.root or agent_root(spec.agent)
    cases = load_set(root, set_name, language)
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / "receipts").mkdir()
    scripted = model is None
    configuration = {"agent": spec.agent, "mode": "scripted" if scripted else "live", "dataset": set_name,
                     "language": language, "dataset_sha256": set_digest(root, set_name), "repeat": repeat,
                     "model": "scripted-oracle-replay" if scripted else _model_name(model),
                     # live runs record the resolved provider profile(s); release policies require it
                     "provider": None if scripted else dict(provider or {}) or None,
                     "dimensions": dict(spec.dimensions), **spec.identity}
    (evidence / "configuration.json").write_text(json.dumps(configuration, indent=2))
    by_key = {case.key: case for case in cases}
    counter = iter(range(1, 1_000_000))

    async def task(key: str) -> Attempt:
        case = by_key[key]
        number = next(counter)
        attempt, failure = None, None
        with tempfile.TemporaryDirectory(prefix=f"{spec.agent}-eval-") as workdir, capture_run_messages() as messages:
            try:
                with models.override_allow_model_requests(not scripted):
                    attempt = await spec.run(case, spec.scripted(case) if scripted else model, Path(workdir))
                attempt.messages = list(messages)
                return attempt
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "detail": str(exc)[:2_000]}
                raise
            finally:
                usage = attempt.usage if attempt is not None else None
                receipt = {"case": key, "failure": failure,
                           "output": _dump(attempt.output) if attempt is not None else None,
                           "usage": _dump(usage), "facts": _dump(attempt.facts) if attempt is not None else None,
                           "messages": TypeAdapter(list[ModelMessage]).dump_python(list(messages), mode="json")}
                (evidence / "receipts" / f"{number:04d}.json").write_text(json.dumps(receipt, indent=2))
                set_eval_attribute("receipt", f"{number:04d}")
                for name in USAGE_FIELDS + ("wall_s", "status"):
                    value = getattr(usage, name, None) if usage is not None else None
                    set_eval_attribute(name, value)
                for name in ROW_FACTS + LABEL_FACTS:
                    set_eval_attribute(name, attempt.facts.get(name) if attempt is not None else None)

    dataset = Dataset(name=f"{spec.agent}-{set_name}", cases=[Case(name=case.key, inputs=case.key, metadata=case)
                                                             for case in cases], evaluators=[_Checks(spec)])
    report = await dataset.evaluate(task, repeat=repeat, max_concurrency=1, retry_task=None, progress=False)
    rows = []
    for item in report.cases:
        key = item.source_case_name or item.name
        values = {name: bool(result.value) for name, result in item.assertions.items()}
        rows.append(_row(spec, by_key[key], values, item.attributes, failure=(
            "; ".join(f"{f.name}: {f.error_message}" for f in item.evaluator_failures) or None)))
    for failure in report.failures:
        key = failure.source_case_name or failure.name
        rows.append(_row(spec, by_key[key], {}, {}, failure=failure.error_message[:2_000]))
    with (evidence / "attempts.jsonl").open("w") as out:
        out.write(json.dumps({"schema": SCHEMA, "agent": spec.agent, "set": set_name, "language": language}) + "\n")
        for row in rows:
            out.write(json.dumps(row) + "\n")
    return bool(rows) and all(row["passed"] for row in rows)


def _row(spec: AgentEval, case: EvalCase, values: dict[str, bool], attributes: Mapping[str, Any], *,
         failure: str | None) -> dict:
    # A dimension counts only where the case declares it measures it, so an assertion that passes trivially on a case
    # it does not apply to (no injection, no target) cannot inflate that dimension's rate. Pass/fail still uses all.
    declared = set(case.case.get("dimensions") or DIMENSIONS)
    dimensions: dict[str, bool] = {}
    for name, dimension in spec.dimensions.items():
        if name in values and dimension in declared:
            dimensions[dimension] = dimensions.get(dimension, True) and values[name]
    metrics = {name: attributes.get(name) for name in USAGE_FIELDS}
    return {"case": case.key, "language": case.language, "kind": case.case.get("kind"),
            "receipt": attributes.get("receipt"), "status": attributes.get("status"),
            "passed": bool(values) and failure is None and all(values.values()),
            "assertions": values, "dimensions": dimensions,
            "failed_assertions": sorted(name for name, value in values.items() if not value),
            "failure": failure, "latency_s": attributes.get("wall_s"), **metrics,
            **{name: attributes.get(name) for name in ROW_FACTS},
            **{name: attributes[name] for name in LABEL_FACTS if attributes.get(name) is not None}}


def main(spec: AgentEval, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Isolated eval of the v2 {spec.agent} agent")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--set", dest="set_name", required=True)
    parser.add_argument("--language", choices=LANGUAGES)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--provider-config", type=Path, help="v2 provider JSON; omitted means scripted replay")
    args = parser.parse_args(argv)
    if args.evidence.exists():
        parser.error("evidence path already exists")

    async def go() -> bool:
        if args.provider_config is None:
            return await evaluate(spec, args.evidence, args.set_name, language=args.language, repeat=args.repeat)
        provider = provider_identity(args.provider_config, spec.live_agents or (spec.agent,))
        async with _live_model(spec, args.provider_config) as model:
            return await evaluate(spec, args.evidence, args.set_name, language=args.language, repeat=args.repeat,
                                  model=model, provider=provider)
    return 0 if asyncio.run(go()) else 1
