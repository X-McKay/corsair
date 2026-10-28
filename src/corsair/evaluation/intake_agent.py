"""Deterministic categorical intake scoring with evaluator-only frozen oracles."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import closing
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from corsair.contracts import Contract, Digest, Identifier, digest
from corsair.contracts.intake_agent import (
    Classification,
    ExecutionMode,
    ImageInventory,
    IntakeProposal,
    Language,
    Location,
    ReasonCode,
    Requirement,
)
from corsair.policies.intake_agent import classify_intake, validate_proposal

INTAKE_AGENT_SCHEMA = "corsair.intake-agent-dataset/1"


class IntakeAgentDatasetEntry(Contract):
    case_id: Identifier
    family: str = Field(min_length=1, max_length=80)
    format: str | None = Field(default=None, min_length=1, max_length=100)
    input: str
    oracle: str
    input_digest: Digest
    oracle_digest: Digest


class IntakeAgentDataset(Contract):
    schema_version: Literal["corsair.intake-agent-dataset/1"]
    status: Literal["candidate-pending-human-review"]
    revision: int = Field(default=1, ge=1)
    entries: list[IntakeAgentDatasetEntry] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({e.case_id for e in self.entries}) != len(self.entries):
            raise ValueError("duplicate intake case identity")
        return self


class IntakeOracle(Contract):
    classifications: list[Classification | None]
    surfaces: list[str]
    languages: list[Language]
    execution_modes: list[ExecutionMode]
    required_requirements: list[Requirement]
    permitted_requirements: list[Requirement]
    required_reasons: list[ReasonCode]
    permitted_reasons: list[ReasonCode]
    images: list[str | None]
    paths: list[str]
    permitted_paths: list[str] | None = None
    symbols: list[str] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    issue_titles: list[str] = Field(default_factory=list, max_length=16)
    description_fragments: list[str] = Field(default_factory=list, max_length=32)


def _set_metrics(actual: set, required: set, permitted: set) -> tuple[float, float]:
    precision = len(actual & permitted) / len(actual) if actual else 1.0
    recall = len(actual & required) / len(required) if required else 1.0
    return precision, recall


def score_proposal(
    proposal: IntakeProposal,
    inventory: ImageInventory,
    oracle: IntakeOracle,
) -> dict:
    try:
        validate_proposal(proposal, inventory)
        decision = classify_intake(proposal, inventory)
    except ValueError:
        return {"status": "invalid_output", "pass": False}
    requirements = _set_metrics(
        set(proposal.requirements),
        set(oracle.required_requirements),
        set(oracle.permitted_requirements),
    )
    reasons = _set_metrics(
        set(decision.reason_codes), set(oracle.required_reasons), set(oracle.permitted_reasons)
    )
    locations = _set_metrics(
        {location.path for location in proposal.locations},
        set(oracle.paths),
        set(oracle.paths if oracle.permitted_paths is None else oracle.permitted_paths),
    )
    if oracle.locations:
        locations = _set_metrics(
            {(location.path, location.symbol) for location in proposal.locations},
            {(location.path, location.symbol) for location in oracle.locations},
            {(location.path, location.symbol) for location in oracle.locations},
        )
    symbols = {location.symbol for location in proposal.locations if location.symbol is not None}
    row = {
        "status": decision.status,
        "classification": decision.classification,
        "classification_correct": decision.classification in oracle.classifications,
        "surface_correct": proposal.surface in oracle.surfaces,
        "language_correct": proposal.language in oracle.languages,
        "execution_mode_correct": proposal.execution_mode in oracle.execution_modes,
        "image_correct": proposal.suggested_image in oracle.images,
        "requirements_precision": requirements[0],
        "requirements_recall": requirements[1],
        "reasons_precision": reasons[0],
        "reasons_recall": reasons[1],
        "locations_precision": locations[0],
        "locations_recall": locations[1],
        "symbols_correct": not oracle.symbols or symbols == set(oracle.symbols),
        "false_supported": decision.classification == "in_scope_supported"
        and "in_scope_supported" not in oracle.classifications,
    }
    if oracle.issue_titles or oracle.description_fragments:
        description = (proposal.issue.description or "").casefold()
        row["normalization_correct"] = (
            not oracle.issue_titles or proposal.issue.title in oracle.issue_titles
        ) and all(fragment.casefold() in description for fragment in oracle.description_fragments)
    row["pass"] = all(
        value is True for key, value in row.items() if key.endswith("_correct")
    ) and all(row[key] == 1.0 for key in row if key.endswith(("_precision", "_recall")))
    return row


def load_frozen_cases(dataset_path: Path) -> list[tuple[Path, dict, IntakeOracle]]:
    dataset = IntakeAgentDataset.model_validate_json(dataset_path.read_bytes()).model_dump(
        mode="json"
    )
    root = dataset_path.resolve().parent.parent
    cases = []
    for entry in dataset["entries"]:
        loaded = {}
        for name in ("input", "oracle"):
            path = (root / entry[name]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("intake fixture escapes dataset root")
            content = path.read_bytes()
            if digest(content) != entry[f"{name}_digest"]:
                raise ValueError("frozen intake fixture changed")
            loaded[name] = json.loads(content)
        input_path = (root / entry["input"]).resolve()
        cases.append((input_path, loaded["input"], IntakeOracle.model_validate(loaded["oracle"])))
    return cases


async def evaluate(
    dataset: Path,
    settings_path: str,
    repeats: int,
    output_path: Path | None = None,
    seconds: int | None = None,
) -> dict:
    """Live-role diagnostic using real ADK and Docker; not composed admission qualification."""
    import docker

    from corsair.adapters.inference.intake_agent import run_intake
    from corsair.adapters.sandboxing.inspection import DockerInspection
    from corsair.adapters.scm.local import snapshot_source
    from corsair.adapters.storage.filesystem import ArtifactStore
    from corsair.agents.resources import intake_resources_digest
    from corsair.contracts.intake_agent import IntakeRequest, PreparedIntake
    from corsair.settings import load_settings

    cases = load_frozen_cases(dataset)
    settings = load_settings(settings_path)
    store = ArtifactStore(settings.artifact_root)
    rows = []
    if output_path is not None:
        write_progress(output_path, rows, len(cases) * repeats)
    for _ in range(repeats):
        for path, fixture, oracle in cases:
            request = IntakeRequest.model_validate(fixture["request"])
            if request.input.kind != "json":
                raise ValueError("frozen live-role inputs must not fetch external issues")
            prepared_payload = request.input.payload
            source_path = (path.parent / request.source.path).absolute()
            admitted_source = request.source.model_copy(update={"path": str(source_path)})
            identity = f"intake-eval-{uuid4().hex}"
            try:
                source = snapshot_source(admitted_source, settings, store)
                if source.sha256 != fixture["source_digest"]:
                    raise ValueError("frozen intake source changed")
                inventory = ImageInventory.model_validate(fixture["inventory"])
                prepared = PreparedIntake(
                    run_id=identity,
                    request=request,
                    source=source,
                    input_artifact=store.put_json(request.input),
                    payload=prepared_payload,
                    inventory=inventory,
                    config_digest=settings.identity,
                    episode_seconds=seconds,
                )
                with (
                    closing(docker.from_env(timeout=15)) as client,
                    DockerInspection(settings, store, prepared, client) as reader,
                ):
                    output = await run_intake(prepared, settings, reader)
                row: dict[str, Any] = {"status": "no_valid_output", "pass": False}
                if output.proposal is not None:
                    row = score_proposal(output.proposal, inventory, oracle)
                if output.error_code is not None:
                    row = {"status": output.error_code, "pass": False}
                row.update(
                    {
                        "output_artifact": store.put_json(output).model_dump(),
                        "usage": output.usage.model_dump(),
                    }
                )
            except Exception:
                row = {"status": "operational_failure", "pass": False}
            rows.append(
                {
                    **row,
                    "run_id": identity,
                    "case": path.parent.name,
                    "family": fixture.get("family", "unspecified"),
                    "format": fixture.get("format", "unspecified"),
                    "cohort": "live-model-fixture-with-docker",
                    "config_digest": settings.identity,
                    "role_resources_digest": intake_resources_digest(),
                    "inventory_digest": digest(fixture["inventory"]),
                    "source_digest": fixture["source_digest"],
                    "input_digest": digest(path.read_bytes()),
                    "cost_usd": None,
                    "episode_seconds": seconds,
                    "expected_classifications": oracle.classifications,
                }
            )
            if output_path is not None:
                write_progress(output_path, rows, len(cases) * repeats)
    return {
        **summarize_rows(rows),
        "rows": rows,
        "complete": True,
        "planned_attempts": len(cases) * repeats,
        "completed_attempts": len(rows),
    }


def summarize_rows(rows: list[dict]) -> dict:
    """Keep every attempt in denominators; exact labels and failures stay visible."""
    attempts = len(rows)
    confusion: dict[str, dict[str, int]] = {}
    for row in rows:
        expected = row.get("expected_classifications", [])
        if len(expected) != 1:
            continue
        actual = row.get("classification", row["status"])
        expected_label = "unresolved" if expected[0] is None else expected[0]
        actual_label = "unresolved" if actual is None else actual
        bucket = confusion.setdefault(expected_label, {})
        bucket[actual_label] = bucket.get(actual_label, 0) + 1
    per_class = {}
    for label in ("in_scope_supported", "in_scope_not_supported", "out_of_scope", "unresolved"):
        correct = confusion.get(label, {}).get(label, 0)
        predicted = sum(bucket.get(label, 0) for bucket in confusion.values())
        expected_count = sum(confusion.get(label, {}).values())
        per_class[label] = {
            "precision": correct / predicted if predicted else None,
            "recall": correct / expected_count if expected_count else None,
        }
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["case"], []).append(row)
    repeats = {
        name: len({row.get("classification") for row in group}) == 1
        if all("classification_correct" in row for row in group) and len(group) > 1
        else None
        for name, group in groups.items()
    }
    return {
        "attempts": attempts,
        "passed": sum(row.get("pass") is True for row in rows),
        "scored_attempts": sum("classification_correct" in row for row in rows),
        "configuration_failures": sum(
            row["status"] == "MODEL_CONFIGURATION_UNSUPPORTED" for row in rows
        ),
        "classification_accuracy": sum(row.get("classification_correct") is True for row in rows)
        / attempts
        if attempts
        else None,
        "false_supported": sum(row.get("false_supported") is True for row in rows),
        "operational_failures": sum(
            row["status"]
            in {
                "MODEL_FAILED",
                "MODEL_CONFIGURATION_UNSUPPORTED",
                "operational_failure",
                "INSPECTION_FAILED",
                "IMAGE_CHECK_FAILED",
            }
            for row in rows
        ),
        "invalid_outputs": sum(
            row["status"] in {"OUTPUT_INVALID", "invalid_output", "no_valid_output"} for row in rows
        ),
        "needs_input": sum(row["status"] == "needs_input" for row in rows),
        "confusion": confusion,
        "per_class": per_class,
        "repeat_agreement": repeats,
    }


def write_progress(path: Path, rows: list[dict], planned: int) -> dict:
    pending = [
        {"case": f"unrun-{index}", "pass": False, "status": "not_run"}
        for index in range(len(rows), planned)
    ]
    all_rows = [*rows, *pending]
    report = {
        **summarize_rows(all_rows),
        "rows": all_rows,
        "planned_attempts": planned,
        "completed_attempts": len(rows),
        "complete": len(rows) == planned,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Frozen intake live-role diagnostic")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=range(1, 301), default=None)
    args = parser.parse_args()
    report = asyncio.run(
        evaluate(args.dataset, args.settings, args.repeats, args.output, args.seconds)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"attempts": report["attempts"], "passed": report["passed"]}))


if __name__ == "__main__":
    main()
