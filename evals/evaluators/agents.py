"""Isolated live-model fixture evaluations; no target code or arbitrary probes run on the host.

This developer runner does not claim native-workspace or whole-system qualification.
Use the production factories unchanged, then score against external frozen oracle data.
"""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from corsair.cli import request_from_file
from corsair.contracts import AuditInput, ProducerInput, digest
from corsair.observability.evaluation import dataset_root, summarize
from corsair.runtime.agent_runner import run_auditor, run_producer
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.manifest import build_manifest
from corsair.settings import load_settings
from corsair.tools.security.sources import prepare_case


async def evaluate(args):
    settings = load_settings(args.settings)
    store = ArtifactStore(settings.artifact_root)
    path = Path(args.dataset)
    dataset = json.loads(path.read_text())
    if dataset["schema_version"] != "corsair.agent-dataset/1":
        raise ValueError("Unsupported isolated agent dataset")
    root = dataset_root(path)
    rows = []
    for repeat in range(args.repeats):
        for entry in dataset["entries"]:
            files = {}
            for field in ("input", "oracle"):
                file = (root / entry[field]).resolve()
                if not file.is_relative_to(root):
                    raise ValueError("agent dataset path escapes its root")
                if digest(file.read_bytes()) != entry[f"{field}_digest"]:
                    raise ValueError("frozen isolated fixture changed")
                files[field] = file
            # Oracle only lives here. None of its fields enter the agent invocation.
            oracle = json.loads(files["oracle"].read_text())
            identity = f"isolated-{uuid4().hex}"
            if args.agent == "producer":
                request = request_from_file(files["input"])
                prepared = prepare_case(
                    request.case,
                    settings,
                    store,
                    build_manifest(request, settings, "fixture-only:no-native-execution"),
                )
                output = await run_producer(
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
                accepted = (
                    output.submission is not None
                    and output.submission.control_payload == oracle["control_payload"]
                    and output.submission.exploit_payload in oracle["candidate_payloads"]
                )
            else:
                packet = AuditInput.model_validate_json(files["input"].read_bytes())
                output = await run_auditor(packet, settings)
                accepted = (
                    output.review is not None and output.review.decision == oracle["decision"]
                )
            artifact = store.put_json(output)
            rows.append(
                {
                    "run_id": identity,
                    "case_id": entry["case_id"],
                    "repeat": repeat,
                    "status": "pass" if accepted else "fail",
                    "cohort": "live-model-fixture",
                    "execution_status": "ERROR"
                    if output.feedback and output.feedback.operational
                    else "COMPLETED",
                    "agent": args.agent,
                    "output_artifact": artifact.model_dump(mode="json"),
                    "config_digest": settings.identity,
                    "llm_calls": output.usage.llm_calls,
                    "tool_calls": output.usage.tool_calls,
                    "input_tokens": output.usage.input_tokens,
                    "output_tokens": output.usage.output_tokens,
                    "agent_seconds": output.usage.seconds,
                    "feedback": output.feedback.model_dump(mode="json")
                    if output.feedback
                    else None,
                }
            )
    report = {"dataset_digest": digest(dataset), "rows": rows, "summary": summarize(rows)}
    destination = Path(args.output or f".runs/evaluations/{args.agent}-{uuid4().hex}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(destination), "summary": report["summary"]}, indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=["producer", "auditor"])
    parser.add_argument("dataset")
    parser.add_argument("--settings", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--output")
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))
