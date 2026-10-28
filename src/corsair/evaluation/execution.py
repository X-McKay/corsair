"""Frozen independent v3 role diagnostics; no model judge or vulnerability scoring."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from corsair.adapters.inference.execution import (
    execution_resources_digest,
    run_execution_auditor,
    run_execution_producer,
)
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source, digest
from corsair.contracts.execution import (
    ExecutionEpisode,
    ExecutionRequest,
    ExecutionRoundInput,
    PlanAudit,
    PreparedExecution,
    TestPlan,
)
from corsair.contracts.intake import AvailableImage, Issue
from corsair.settings import load_settings


def load_role_cases(path: Path) -> list[dict]:
    dataset = json.loads(path.read_bytes())
    if (
        dataset["schema_version"] != "corsair.execution-role-dataset/1"
        or not 1 <= len(dataset["entries"]) <= 64
    ):
        raise ValueError("invalid frozen role dataset")
    root = path.resolve().parent.parent
    cases = []
    for entry in dataset["entries"]:
        values = {"case_id": entry["case_id"]}
        for name in ("input", "oracle"):
            target = (root / entry[name]).resolve()
            if not target.is_relative_to(root) or target.stat().st_size > 524288:
                raise ValueError("role fixture escapes dataset or exceeds bound")
            content = target.read_bytes()
            if digest(content) != entry[f"{name}_digest"]:
                raise ValueError("frozen role fixture changed")
            values[name] = json.loads(content)
        cases.append(values)
    return cases


def score_episode(output: ExecutionEpisode, oracle: dict) -> dict:
    if output.error is not None:
        return {"pass": False, "status": output.error}
    if oracle["role"] == "auditor":
        return {
            "pass": output.audit == PlanAudit.model_validate(oracle["audit"]),
            "status": "scored",
        }
    plan = output.plan
    if plan is None:
        return {"pass": False, "status": "OUTPUT_MISSING"}
    content = (
        "\n".join(file.content for file in plan.files)
        + "\n"
        + json.dumps([command.argv for command in plan.commands])
    )
    checks = {
        "revision": plan.revision == 1 and plan.parent_revision is None,
        "source_location": any(location.path == oracle["path"] for location in plan.locations),
        "source_reference": oracle["source_reference"] in content,
        "target_reference": oracle["path"].removesuffix(".py") in content,
    }
    return {"pass": all(checks.values()), "status": "scored", "checks": checks}


class FixtureReader:
    def __init__(self, source: dict[str, str]):
        self.source = source

    def read(self, operation: str, relative: str = "") -> dict:
        if operation == "list":
            return {"files": sorted(self.source), "truncated": False}
        return {"path": relative, "content": self.source[relative], "truncated": False}


async def evaluate_roles(
    dataset: Path, settings_path: str, output_path: Path, *, repeats: int = 1, seconds: int = 90
) -> dict:
    cases = load_role_cases(dataset)
    settings = load_settings(settings_path)
    store = ArtifactStore(settings.artifact_root)
    rows = []
    planned = len(cases) * repeats
    write_role_progress(output_path, rows, planned)
    for repeat in range(repeats):
        for case in cases:
            payload = case["input"]
            request = ExecutionRequest(
                case_id=case["case_id"],
                issue=Issue.model_validate(payload["issue"]),
                source=Source(path="fixture"),
                image=AvailableImage(
                    reference=settings.image,
                    image_id="sha256:" + "1" * 64,
                    language="python",
                    execution_mode="callable",
                ),
            )
            source = store.put_json(payload["source"])
            prepared = PreparedExecution(
                run_id=f"role-{case['case_id']}-{repeat}",
                request=request,
                source=source,
                config_digest=settings.identity,
                request_digest=digest(request),
                resources_digest=execution_resources_digest(),
            )
            item = ExecutionRoundInput(
                prepared=prepared, revision=1, llm_limit=4, tool_limit=24, seconds=seconds
            )
            reader = FixtureReader(payload["source"])
            try:
                if payload["role"] == "producer":
                    result = await run_execution_producer(item, settings, reader)
                else:
                    result = await run_execution_auditor(
                        item, TestPlan.model_validate(payload["plan"]), settings, reader
                    )
                row: dict[str, Any] = {
                    **score_episode(result, case["oracle"]),
                    "output_artifact": store.put_json(result).model_dump(),
                }
            except Exception:
                row = {"pass": False, "status": "OPERATIONAL_FAILURE"}
            row.update(
                {
                    "case": case["case_id"],
                    "role": payload["role"],
                    "repeat": repeat,
                    "config_digest": settings.identity,
                    "resources_digest": prepared.resources_digest,
                    "input_digest": digest(payload),
                    "cost_usd": None,
                    "seconds_limit": seconds,
                }
            )
            rows.append(row)
            report = write_role_progress(output_path, rows, planned)
    return report


def write_role_progress(output_path: Path, rows: list[dict], planned: int) -> dict:
    report = {
        "cohort": "live-model-frozen-role-fixtures",
        "planned_attempts": planned,
        "completed_attempts": len(rows),
        "complete": len(rows) == planned,
        "passed": sum(row["pass"] is True for row in rows),
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".partial")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(output_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent frozen v3 role diagnostics")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--seconds", type=int, choices=range(1, 301), default=90)
    args = parser.parse_args()
    result = asyncio.run(
        evaluate_roles(
            args.dataset, args.settings, args.output, repeats=args.repeats, seconds=args.seconds
        )
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("planned_attempts", "completed_attempts", "passed", "complete")
            }
        )
    )


if __name__ == "__main__":
    main()
