"""Isolated live-model evaluations; no target code or arbitrary probes run on the host."""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.console import Console

from corsair.adapters.inference.adk import run_auditor, run_producer
from corsair.adapters.scm.local import prepare_case
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.resources import load_agent_spec, prompt_text, runtime_skill_digest
from corsair.contracts import (
    AuditInput,
    AuditOutput,
    InvestigationRequest,
    MatchKind,
    ProducerInput,
    ProducerOutput,
    digest,
)
from corsair.evaluation.scoring import dataset_root, summarize
from corsair.observability.logging import configure_logging, event, safe_error_detail
from corsair.settings import Settings, load_settings
from corsair.steps.manifest import build_manifest


def load_frozen_fixture(root: Path, entry: dict[str, Any]) -> tuple[Path, bytes, dict[str, Any]]:
    """Read/verify once; the oracle remains local to this evaluator."""
    contents: dict[str, bytes] = {}
    paths: dict[str, Path] = {}
    for field in ("input", "oracle"):
        path = (root / entry[field]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("agent dataset path escapes its root")
        content = path.read_bytes()
        if digest(content) != entry[f"{field}_digest"]:
            raise ValueError("frozen isolated fixture changed")
        paths[field], contents[field] = path, content
    oracle = json.loads(contents["oracle"])
    if not isinstance(oracle, dict):
        raise ValueError("isolated oracle must be a JSON object")
    return paths["input"], contents["input"], oracle


async def invoke_fixture_agent(
    agent: str,
    path: Path,
    content: bytes,
    identity: str,
    settings: Settings,
    store: ArtifactStore,
) -> ProducerOutput | AuditOutput:
    """Invoke a production factory with only its admitted input, never oracle data."""
    if agent == "auditor":
        return await run_auditor(AuditInput.model_validate_json(content), settings)
    if agent != "producer":
        raise ValueError("unknown isolated agent")
    request = normalize_request_sources(InvestigationRequest.model_validate_json(content), path)
    prepared = prepare_case(
        request.case,
        settings,
        store,
        build_manifest(request, settings, "fixture-only:no-native-execution"),
    )
    return await run_producer(
        ProducerInput(
            run_id=identity,
            prepared=prepared,
            budget=request.budget,
            round_index=1,
            llm_call_limit=request.budget.episode_llm_calls,
            tool_call_limit=request.budget.max_tool_calls,
        ),
        settings,
        store,
    )


def fixture_matches_oracle(output: ProducerOutput | AuditOutput, oracle: dict[str, Any]) -> bool:
    """Compare output outside the agent boundary; no native-evidence claim is made."""
    if isinstance(output, ProducerOutput):
        submission = output.submission_for_verification()
        return (
            submission is not None
            and submission.control_payload == oracle["control_payload"]
            and submission.exploit_payload in oracle["candidate_payloads"]
        )
    return output.review is not None and output.review.decision == oracle["decision"]


def fixture_match_kind(output: ProducerOutput | AuditOutput, oracle: dict[str, Any]) -> MatchKind:
    """Classify exact fixture output without changing the evaluator's pass predicate."""
    if output.feedback is not None and output.feedback.operational:
        return MatchKind.OPERATIONAL_FAILURE
    if isinstance(output, ProducerOutput):
        submission = output.submission_for_verification()
        if submission is None:
            return MatchKind.NO_VALID_OUTPUT
        if submission.control_payload != oracle["control_payload"]:
            return MatchKind.CONTROL_MISMATCH
        if submission.exploit_payload not in oracle["candidate_payloads"]:
            return MatchKind.CANDIDATE_EXACT_MISMATCH
        return MatchKind.EXACT_MATCH
    if output.review is None:
        return MatchKind.NO_VALID_OUTPUT
    if output.review.decision != oracle["decision"]:
        return MatchKind.CANDIDATE_EXACT_MISMATCH
    return MatchKind.EXACT_MATCH


def fixture_score_row(
    output: ProducerOutput | AuditOutput,
    oracle: dict[str, Any],
    *,
    identity: str,
    case_id: str,
    repeat: int,
    agent: str,
    settings: Settings,
    store: ArtifactStore,
) -> dict[str, Any]:
    """Persist the output and retain errors, unknown accounting, and evaluation identity."""
    review = output.review if isinstance(output, AuditOutput) else None
    return {
        "run_id": identity,
        "case_id": case_id,
        "repeat": repeat,
        "status": "pass" if fixture_matches_oracle(output, oracle) else "fail",
        "match_kind": fixture_match_kind(output, oracle),
        "cohort": "live-model-fixture",
        "execution_status": "ERROR"
        if output.feedback and output.feedback.operational
        else "COMPLETED",
        "agent": agent,
        # The auditor's own decisive rubric id makes a rejection attributable in the
        # report; it is model output, so it never changes the oracle pass predicate.
        "audit_decision": None if review is None else review.decision.value,
        "audit_rule": None if review is None else review.rule,
        "output_artifact": store.put_json(output).model_dump(mode="json"),
        "config_digest": settings.identity,
        "agent_resources_digest": digest(
            {
                "spec": load_agent_spec(agent).model_dump(mode="json"),
                "instruction": prompt_text(agent),
                "runtime_skills_digest": runtime_skill_digest(agent),
            }
        ),
        "llm_calls": output.usage.llm_calls,
        "tool_calls": output.usage.tool_calls,
        "skills_loaded": output.usage.skills_loaded,
        "skills_preloaded": output.usage.skills_preloaded,
        "input_tokens": output.usage.input_tokens,
        "output_tokens": output.usage.output_tokens,
        "agent_seconds": output.usage.seconds,
        "feedback": output.feedback.model_dump(mode="json") if output.feedback else None,
    }


async def evaluate(args: argparse.Namespace) -> int:
    """Coordinate one finite isolated evaluation and save its external report."""
    settings = load_settings(args.settings)
    store = ArtifactStore(settings.artifact_root)
    path = Path(args.dataset)
    dataset = json.loads(path.read_bytes())
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "corsair.agent-dataset/1":
        raise ValueError("Unsupported isolated agent dataset")
    entries = dataset.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError("isolated dataset requires 1..64 entries")
    root = dataset_root(path)
    fixtures = [(entry, load_frozen_fixture(root, entry)) for entry in entries]
    rows = []
    for repeat in range(args.repeats):
        for entry, (input_path, content, oracle) in fixtures:
            identity = f"isolated-{uuid4().hex}"
            event(
                "isolated_agent.started",
                run_id=identity,
                case_id=entry["case_id"],
                round=repeat + 1,
            )
            output = await invoke_fixture_agent(
                args.agent, input_path, content, identity, settings, store
            )
            row = fixture_score_row(
                output,
                oracle,
                identity=identity,
                case_id=entry["case_id"],
                repeat=repeat,
                agent=args.agent,
                settings=settings,
                store=store,
            )
            rows.append(row)
            event(
                "isolated_agent.completed",
                run_id=identity,
                status=row["status"],
                llm_calls=output.usage.llm_calls,
                gate=output.feedback.gate if output.feedback else None,
            )
    report = {"dataset_digest": digest(dataset), "rows": rows, "summary": summarize(rows)}
    destination = Path(args.output or f".runs/evaluations/{args.agent}-{uuid4().hex}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(destination), "summary": report["summary"]}, indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=["producer", "auditor"])
    parser.add_argument("dataset")
    parser.add_argument("--settings", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--output")
    args = parser.parse_args()
    configure_logging(Console(stderr=True, no_color=True), format="json")
    try:
        code = asyncio.run(evaluate(args))
    except KeyboardInterrupt:
        event("isolated_agent.interrupted", level=logging.WARNING)
        raise SystemExit(130) from None
    except Exception as error:
        event(
            "isolated_agent.failed",
            level=logging.ERROR,
            error_type=type(error).__name__,
            message=safe_error_detail(error),
        )
        raise SystemExit(2) from None
    raise SystemExit(code)


if __name__ == "__main__":
    main()
