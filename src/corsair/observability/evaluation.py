"""External evaluator: oracle files are never passed to agents, tools or workflows."""

import json
from pathlib import Path

from pydantic import Field

from corsair.contracts import (
    Contract,
    Digest,
    Disposition,
    ExecutionStatus,
    FixStatus,
    InvestigationRequest,
    InvestigationResult,
    digest,
)
from corsair.policy.verdicts import decide, fix_status
from corsair.runtime.artifacts import ArtifactStore
from corsair.settings import Settings
from corsair.tools.security.evidence import EvidenceVerifier


class Oracle(Contract):
    acceptable: list[Disposition] = Field(min_length=1)
    forbidden: list[Disposition] = Field(default_factory=list)
    expected_execution: ExecutionStatus = ExecutionStatus.COMPLETED
    expected_fix: FixStatus | None = None


class DatasetEntry(Contract):
    case_id: str
    family: str
    request: str
    oracle: str
    request_digest: Digest
    oracle_digest: Digest
    split: str


class Dataset(Contract):
    schema_version: str = "corsair.dataset/1"
    entries: list[DatasetEntry] = Field(min_length=1, max_length=64)


def dataset_root(path: Path) -> Path:
    # Reference-layout manifests in evals/datasets address the enclosing evals tree.
    parent = path.parent.resolve()
    return parent.parent if parent.name == "datasets" else parent


def _under(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("dataset path escapes its root or is missing")
    return path


def load_dataset(path: Path) -> tuple[Dataset, list[InvestigationRequest], dict[str, Oracle]]:
    """Verify the frozen files first. Return oracle data only to the evaluator caller."""
    dataset = Dataset.model_validate_json(path.read_bytes())
    root = dataset_root(path)
    requests, oracles = [], {}
    family_splits: dict[str, str] = {}
    for entry in dataset.entries:
        if entry.case_id in oracles:
            raise ValueError("duplicate case identity")
        if entry.family in family_splits and family_splits[entry.family] != entry.split:
            raise ValueError("related family variants may not cross dataset splits")
        family_splits[entry.family] = entry.split
        request_path = _under(root, entry.request)
        oracle_path = _under(root, entry.oracle)
        if digest(request_path.read_bytes()) != entry.request_digest:
            raise ValueError("frozen request digest changed")
        if digest(oracle_path.read_bytes()) != entry.oracle_digest:
            raise ValueError("frozen oracle digest changed")
        request = InvestigationRequest.model_validate_json(request_path.read_bytes())
        if request.case.case_id != entry.case_id:
            raise ValueError("dataset and request case identities disagree")
        # Resolve source paths at the client edge, never expose dataset/oracle paths to an agent.
        source = request.case.source.model_copy(
            update={"path": str((request_path.parent / request.case.source.path).absolute())}
        )
        fixed = request.case.fixed_source
        if fixed is not None:
            fixed = fixed.model_copy(
                update={"path": str((request_path.parent / fixed.path).absolute())}
            )
        case = request.case.model_copy(update={"source": source, "fixed_source": fixed})
        requests.append(request.model_copy(update={"case": case}))
        oracles[entry.case_id] = Oracle.model_validate_json(oracle_path.read_bytes())
    return dataset, requests, oracles


def valid_positive_evidence(result: InvestigationResult, store: ArtifactStore | None) -> bool:
    if result.manifest is None or store is None:
        return False
    verifier = EvidenceVerifier(Settings(), store)
    for item in result.rounds:
        observation, audit = item.observation, item.audit
        submission = item.producer.submission
        if observation is None or submission is None or audit is None:
            continue
        prepared = verifier.validate_saved(observation, submission, result.manifest)
        if (
            prepared is not None
            and prepared.case_id == result.case_id
            and decide(prepared, observation, audit)[0] == result.disposition
        ):
            return True
    return False


def score(result: InvestigationResult, oracle: Oracle, store: ArtifactStore | None = None) -> dict:
    """One final-policy result, including invalid evidence and operational failures."""
    positive = result.disposition in {Disposition.SUPPORTED, Disposition.CONDITIONAL}
    evidence_valid = valid_positive_evidence(result, store) if positive else True
    allowed = result.disposition in oracle.acceptable and result.disposition not in oracle.forbidden
    fix_correct = oracle.expected_fix is None or result.fix_status == oracle.expected_fix
    if result.fix_status in {FixStatus.DEMONSTRATION_BLOCKED, FixStatus.NOT_BLOCKED}:
        fixed = result.fix_observation
        fixed_valid = False
        if fixed is not None and store is not None and result.manifest is not None:
            verifier = EvidenceVerifier(Settings(), store)
            fixed_valid = any(
                item.producer.submission is not None
                and (
                    prepared := verifier.validate_saved(
                        fixed, item.producer.submission, result.manifest, expected_fixed=True
                    )
                )
                is not None
                and prepared.case_id == result.case_id
                for item in result.rounds
            )
        fix_correct = fix_correct and fixed_valid and fix_status(fixed) == result.fix_status
    passed = (
        allowed
        and evidence_valid
        and fix_correct
        and result.execution_status == oracle.expected_execution
    )
    return {
        "run_id": result.run_id,
        "case_id": result.case_id,
        "status": "pass" if passed else "fail",
        "disposition": result.disposition.value,
        "execution_status": result.execution_status.value,
        "evidence_valid": evidence_valid,
        "fix_correct": fix_correct,
        "forbidden_label": result.disposition in oracle.forbidden,
        "correctly_resolved": passed and result.disposition != Disposition.INCONCLUSIVE,
        **usage_metrics(result),
        "config_digest": result.manifest.config_digest if result.manifest else None,
        "reason": result.reason,
    }


def usage_metrics(result: InvestigationResult) -> dict:
    """One usage calculation shared by scoring and human CLI presentation."""
    usage = [item.producer.usage for item in result.rounds]
    usage += [item.audit.usage for item in result.rounds if item.audit is not None]
    input_tokens = (
        sum(item.input_tokens for item in usage)
        if result.usage_complete and usage and all(item.input_tokens is not None for item in usage)
        else None
    )
    output_tokens = (
        sum(item.output_tokens for item in usage)
        if result.usage_complete and usage and all(item.output_tokens is not None for item in usage)
        else None
    )
    return {
        "llm_calls": sum(item.llm_calls for item in usage) if result.usage_complete else None,
        "tool_calls": sum(item.tool_calls for item in usage) if result.usage_complete else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "agent_seconds": sum(item.seconds for item in usage) if result.usage_complete else None,
    }


def known_total(rows: list[dict], field: str) -> int | None:
    return (
        sum(row[field] for row in rows)
        if rows and all(row.get(field) is not None for row in rows)
        else None
    )


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    passed = sum(row.get("status") == "pass" for row in rows)
    return {
        "attempts": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else None,
        "correctly_resolved": sum(row.get("correctly_resolved", False) for row in rows),
        "invalid_positive_evidence": sum(row.get("evidence_valid") is False for row in rows),
        "forbidden_labels": sum(row.get("forbidden_label", False) for row in rows),
        "inconclusive": sum(row.get("disposition") == "INCONCLUSIVE" for row in rows),
        "operational_failures": sum(
            row.get("execution_status") in {"BLOCKED", "ERROR", "CANCELLED"} for row in rows
        ),
        "unavailable_results": sum(row.get("status") == "unavailable" for row in rows),
        "llm_calls": known_total(rows, "llm_calls"),
        "tool_calls": known_total(rows, "tool_calls"),
        "input_tokens": (
            sum(row["input_tokens"] for row in rows)
            if rows and all(row.get("input_tokens") is not None for row in rows)
            else None
        ),
        "output_tokens": (
            sum(row["output_tokens"] for row in rows)
            if rows and all(row.get("output_tokens") is not None for row in rows)
            else None
        ),
        "cost_usd": None,
    }


def save_report(path: Path, rows: list[dict]) -> dict:
    report = {"rows": rows, "summary": summarize(rows)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report
