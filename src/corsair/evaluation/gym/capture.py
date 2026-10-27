"""Capture a failed case as frozen regression material.

For each failed repeat of a case in a gym run this writes:

- a kernel case (``KernelCase``): the stored rounds and observations, the prepared case
  recovered from the rounds' own validated receipts, and the recorded verdict. Replaying it
  through ``corsair.policies.verdicts`` (``kernel_verdict``) must reproduce that verdict, so
  it is a model-free regression guard for the kernel;
- isolated agent fixtures in the ``corsair.agent-dataset/1`` form ``eval-agent`` and
  ``load_frozen_fixture`` consume, only where trusted code can state the expected answer:
  an auditor fixture when the audit disagreed with a validated control-vs-exploit
  differential on a case whose frozen oracle decides the label, and a producer fixture when
  some run of the case demonstrated a payload pair the kernel validated.

Expected agent answers are derived from the human-reviewed case oracle plus validated
receipts, never from model output; anything else is skipped and reported. Fixture outputs
keep only the structured decision and payloads plus the full output's digest, never the
hypothesis, plan or review text. Existing files are never overwritten.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditInput,
    AuditOutput,
    AuditResult,
    AuditRule,
    ExecutionStatus,
    FixStatus,
    InvestigationRequest,
    InvestigationResult,
    KernelCase,
    Oracle,
    PlanRevision,
    PreparedCase,
    ProducerDecision,
    RoundResult,
    Verdict,
    digest,
)
from corsair.evaluation.comparison import read_report
from corsair.evaluation.datasets import AGENT_SCHEMA, dataset_root, load_dataset
from corsair.evaluation.gym.scoring import (
    DEMONSTRATED,
    REPORT_FILE,
    allowed_verdicts,
    load_results,
)
from corsair.evaluation.ledger import verified_rounds
from corsair.policies.verdicts import (
    case_verdict,
    session_verdict,
    status_outcome,
    terminal_outcome,
    terminal_round,
)

# A trusted stand-in used only to ask the kernel whether a round's evidence is a valid
# differential; it never becomes a recorded review or a fixture output.
_DIFFERENTIAL_PROBE = AuditOutput(
    review=AuditResult(decision=AuditDecision.ACCEPT, rule=AuditRule.ALL, reason="capture probe")
)


def kernel_verdict(case: KernelCase) -> Verdict:
    """Replay a kernel case's sessions through the pure verdict policy, as the workflow does."""
    sessions: dict[int, list[RoundResult]] = {}
    for item in case.rounds:
        sessions.setdefault(item.session, []).append(item)
    if not sessions:
        return case_verdict([status_outcome(case.execution_status, case.reason)])[0]
    order = sorted(sessions)
    outcomes = []
    for position, session in enumerate(order):
        last = position == len(order) - 1
        terminal = terminal_round(sessions[session])
        if case.prepared is not None and terminal is not None:
            outcome = terminal_outcome(case.prepared, terminal, case.fix_status)
        else:
            status = case.execution_status if last else ExecutionStatus.COMPLETED
            outcome = status_outcome(status, case.reason)
        if (
            last
            and case.execution_status is not ExecutionStatus.COMPLETED
            and outcome.verdict not in DEMONSTRATED
        ):
            outcome = status_outcome(case.execution_status, case.reason)
        outcomes.append(outcome)
    return case_verdict(outcomes, case.negative_threshold)[0]


def read_kernel_case(path: Path) -> KernelCase:
    return KernelCase.model_validate_json(path.read_bytes())


def _write_new(path: Path, content: bytes) -> str:
    """Create a frozen file once; an identical rewrite is a no-op, a different one an error."""
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"refusing to overwrite frozen file {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return digest(content)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _evaluated(item: RoundResult) -> bool:
    return item.observation is not None and item.audit is not None


REDACTED = "redacted at capture"


def redacted_round(item: RoundResult) -> RoundResult:
    """The round without model-authored prose; payloads and decisions are kept verbatim.

    The kernel reads only payloads, observations and audit decisions, so the hypothesis,
    plan, abstention reason and review reason are replaced by fixed text.
    """
    producer, audit = item.producer, item.audit
    decision = producer.decision
    if decision is not None and decision.submission is not None:
        plan = decision.submission.plan
        submission = decision.submission.model_copy(
            update={
                "hypothesis": REDACTED,
                "plan": PlanRevision(
                    revision=plan.revision,
                    parent_revision=plan.parent_revision,
                    objective=REDACTED,
                    next_steps=[REDACTED],
                    reason=REDACTED,
                ),
            }
        )
        decision = decision.model_copy(update={"submission": submission})
    elif decision is not None:
        decision = ProducerDecision(kind=decision.kind, reason=REDACTED)
    if audit is not None and audit.review is not None:
        audit = audit.model_copy(
            update={"review": audit.review.model_copy(update={"reason": REDACTED})}
        )
    return item.model_copy(
        update={"producer": producer.model_copy(update={"decision": decision}), "audit": audit}
    )


def build_kernel_case(
    result: InvestigationResult, oracle: Oracle, kind: str, prepared: PreparedCase | None
) -> KernelCase:
    return KernelCase(
        case_id=result.case_id,
        run_id=result.run_id,
        kind=kind,
        oracle=oracle,
        recorded_verdict=result.verdict,
        execution_status=result.execution_status,
        # The final reason may quote a review; the replayed verdict never reads it.
        reason=REDACTED,
        fix_status=result.fix_status,
        negative_threshold=result.manifest.negative_threshold if result.manifest else 2,
        prepared=prepared,
        rounds=[redacted_round(item) for item in result.rounds],
    )


def _differential(prepared: PreparedCase, item: RoundResult) -> bool:
    """Whether the round's validated evidence is a covered control-vs-exploit differential."""
    assert item.observation is not None
    outcome = session_verdict(
        prepared, item.observation, _DIFFERENTIAL_PROBE, FixStatus.NOT_REQUESTED
    )
    return outcome.verdict in DEMONSTRATED


def expected_review(prepared: PreparedCase, item: RoundResult, oracle: Oracle) -> dict | None:
    """The auditor answer trusted code can state for a disagreeing round, else None."""
    review = item.audit.review if item.audit is not None else None
    if review is None or item.observation is None or not _differential(prepared, item):
        return None
    allowed = allowed_verdicts(oracle)
    if allowed and allowed <= DEMONSTRATED and review.decision is not AuditDecision.ACCEPT:
        return {"decision": AuditDecision.ACCEPT.value, "rule": AuditRule.ALL.value}
    if not allowed & DEMONSTRATED and review.decision is AuditDecision.ACCEPT:
        return {"decision": AuditDecision.REJECT.value}
    return None


def _demonstrated_pairs(result: InvestigationResult, store: ArtifactStore) -> list[tuple[str, str]]:
    """String payload pairs of rounds whose validated evidence the kernel decided demonstrated."""
    pairs = []
    for key, prepared in sorted(verified_rounds(result, store).items()):
        item = next(entry for entry in result.rounds if (entry.session, entry.index) == key)
        submission = item.producer.submission_for_verification()
        assert submission is not None and item.observation is not None and item.audit is not None
        outcome = session_verdict(prepared, item.observation, item.audit, FixStatus.NOT_REQUESTED)
        control, exploit = submission.control_payload, submission.exploit_payload
        if (
            outcome.verdict in DEMONSTRATED
            and isinstance(control, str)
            and isinstance(exploit, str)
        ):
            pairs.append((control, exploit))
    return pairs


def producer_oracle(pairs: Sequence[tuple[str, str]]) -> dict | None:
    """The first demonstrated control and every distinct exploit demonstrated beside it."""
    if not pairs:
        return None
    control = pairs[0][0]
    candidates: list[str] = []
    for pair_control, exploit in pairs:
        if pair_control == control and exploit != control and exploit not in candidates:
            candidates.append(exploit)
    return {"control_payload": control, "candidate_payloads": candidates} if candidates else None


def _case_rows(report: Mapping[str, Any], case_id: str) -> list[dict[str, Any]]:
    return [row for row in report["rows"] if row.get("case_id") == case_id]


def _report(run_dir: Path, dataset_digest: str) -> dict[str, Any]:
    report = read_report(run_dir / REPORT_FILE)
    if report.get("dataset_digest") != dataset_digest:
        raise ValueError(f"{run_dir} scored a different dataset than the capture manifest")
    return report


class _Capture:
    """Accumulates one capture's files, dataset entries and skipped repeats."""

    def __init__(self, out_root: Path, fixture_id: str) -> None:
        self.out_root = out_root
        self.fixture_dir = out_root / "fixtures" / fixture_id
        self.fixture_id = fixture_id
        self.files: dict[str, str] = {}
        self.auditor: list[dict[str, str]] = []
        self.producer: list[dict[str, str]] = []
        self.kernel_cases: list[str] = []
        self.skipped: list[dict[str, str]] = []

    def write(self, path: Path, content: bytes) -> str:
        file_digest = _write_new(path, content)
        self.files[str(path)] = file_digest
        return file_digest

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.out_root.resolve()).as_posix()

    def skip(self, subject: str, reason: str) -> None:
        """Record a run id or case id that produced no file, with a fixed reason code."""
        self.skipped.append({"subject": subject, "reason": reason})


def _capture_kernel(
    capture: _Capture,
    result: InvestigationResult,
    oracle: Oracle,
    kind: str,
    verified: Mapping[tuple[int, int], PreparedCase],
    kernel_dir: Path,
) -> None:
    if any(
        _evaluated(item) and (item.session, item.index) not in verified for item in result.rounds
    ):
        capture.skip(result.run_id, "receipts_unverified")
        return
    prepared = next(iter(verified.values()), None)
    case = build_kernel_case(result, oracle, kind, prepared)
    if kernel_verdict(case) != result.verdict:
        capture.skip(result.run_id, "kernel_replay_disagrees")
        return
    path = kernel_dir / f"{result.case_id}.{result.run_id}.json"
    capture.write(path, _json_bytes(case.model_dump(mode="json")))
    capture.kernel_cases.append(str(path))


def _capture_auditor(
    capture: _Capture,
    result: InvestigationResult,
    oracle: Oracle,
    request: InvestigationRequest,
    verified: Mapping[tuple[int, int], PreparedCase],
) -> None:
    for (session, index), prepared in sorted(verified.items()):
        item = next(
            entry for entry in result.rounds if (entry.session, entry.index) == (session, index)
        )
        expected = expected_review(prepared, item, oracle)
        submission = item.producer.submission_for_verification()
        if expected is None or submission is None or item.audit is None:
            continue
        assert item.audit.review is not None
        directory = capture.fixture_dir / f"audit-{result.run_id}-s{session}r{index}"
        packet = AuditInput(
            finding=prepared.finding,
            recipe=prepared.recipe,
            source_excerpt=prepared.source_excerpt,
            submission=submission,
            line_provenance=prepared.line_provenance,
            max_output_tokens=request.budget.max_output_tokens,
        )
        input_digest = capture.write(
            directory / "input.json", _json_bytes(packet.model_dump(mode="json"))
        )
        oracle_digest = capture.write(directory / "oracle.json", _json_bytes(expected))
        capture.write(
            directory / "output.json",
            _json_bytes(
                {
                    "decision": item.audit.review.decision.value,
                    "rule": item.audit.review.rule.value,
                    "output_digest": digest(item.audit),
                }
            ),
        )
        capture.auditor.append(
            {
                "case_id": f"{result.case_id}.{result.run_id}.s{session}r{index}",
                "input": capture.relative(directory / "input.json"),
                "oracle": capture.relative(directory / "oracle.json"),
                "input_digest": input_digest,
                "oracle_digest": oracle_digest,
            }
        )


def _producer_outputs(results: Iterable[InvestigationResult]) -> list[dict[str, Any]]:
    outputs = []
    for result in results:
        for item in result.rounds:
            submission = item.producer.submission_for_verification()
            outputs.append(
                {
                    "run_id": result.run_id,
                    "session": item.session,
                    "round": item.index,
                    "kind": None if item.producer.decision is None else item.producer.decision.kind,
                    "control_payload": None if submission is None else submission.control_payload,
                    "exploit_payload": None if submission is None else submission.exploit_payload,
                    "output_digest": digest(item.producer),
                }
            )
    return outputs


def _capture_producer(
    capture: _Capture,
    case_id: str,
    request_path: Path,
    request_digest: str,
    failed: Sequence[InvestigationResult],
    pairs: Sequence[tuple[str, str]],
) -> None:
    expected = producer_oracle(pairs)
    if expected is None:
        capture.skip(case_id, "no_validated_demonstration")
        return
    if not request_path.resolve().is_relative_to(capture.out_root.resolve()):
        capture.skip(case_id, "request_outside_capture_root")
        return
    oracle_path = capture.fixture_dir / "producer-oracle.json"
    oracle_digest = capture.write(oracle_path, _json_bytes(expected))
    capture.write(
        capture.fixture_dir / "producer-outputs.json", _json_bytes(_producer_outputs(failed))
    )
    capture.producer.append(
        {
            "case_id": case_id,
            "input": capture.relative(request_path),
            "oracle": capture.relative(oracle_path),
            "input_digest": request_digest,
            "oracle_digest": oracle_digest,
        }
    )


def _write_agent_dataset(capture: _Capture, role: str, entries: list[dict[str, str]]) -> str | None:
    if not entries:
        return None
    path = capture.out_root / "datasets" / f"{capture.fixture_id}-{role}.json"
    capture.write(path, _json_bytes({"schema_version": AGENT_SCHEMA, "entries": entries}))
    return str(path)


def capture(
    run_dir: Path,
    case_id: str,
    *,
    dataset_path: Path,
    store: ArtifactStore,
    out_root: Path,
    kernel_dir: Path,
    references: Sequence[Path] = (),
    manifest_root: Path | None = None,
) -> dict[str, Any]:
    """Capture every failed repeat of ``case_id`` in a gym run.

    ``out_root`` is the evaluation root that agent datasets address (``evals/`` in the
    repository); fixtures go to ``fixtures/gym-<run>-<case>/`` and manifests to
    ``datasets/``. ``references`` are other run directories over the same dataset whose
    demonstrated payloads may supply the producer oracle (a case that flipped to failing).
    ``manifest_root`` resolves the entries of a manifest copied out of its evaluation tree
    (the run directory's pinned ``dataset.json``).
    """
    root = dataset_root(dataset_path) if manifest_root is None else manifest_root
    dataset, requests, oracles = load_dataset(dataset_path, root=root)
    dataset_digest = digest(dataset)
    report = _report(run_dir, dataset_digest)
    if case_id not in oracles:
        raise ValueError(f"{case_id} is not in the capture dataset")
    failed_rows = [row for row in _case_rows(report, case_id) if row.get("status") != "pass"]
    if not failed_rows:
        raise ValueError(f"{case_id} has no failed repeat in {run_dir}")
    request = next(item for item in requests if item.case.case_id == case_id)
    entry = next(item for item in dataset.entries if item.case_id == case_id)
    oracle, kind = oracles[case_id], request.case.recipe.kind
    capture_state = _Capture(out_root, f"gym-{run_dir.name}-{case_id}")
    results = load_results(store, [str(row.get("run_id")) for row in failed_rows])
    failed: list[InvestigationResult] = []
    for run_id, result in results.items():
        if result is None or result.case_id != case_id:
            capture_state.skip(run_id, "result_unavailable")
            continue
        failed.append(result)
        verified = verified_rounds(result, store)
        _capture_kernel(capture_state, result, oracle, kind, verified, kernel_dir)
        _capture_auditor(capture_state, result, oracle, request, verified)
    pairs: list[tuple[str, str]] = []
    allowed = allowed_verdicts(oracle)
    if allowed and allowed <= DEMONSTRATED:
        sources = [report] + [_report(path, dataset_digest) for path in references]
        run_ids = [
            str(row.get("run_id")) for source in sources for row in _case_rows(source, case_id)
        ]
        for result in load_results(store, run_ids).values():
            if result is not None and result.case_id == case_id:
                pairs.extend(_demonstrated_pairs(result, store))
    request_path = root / entry.request
    _capture_producer(capture_state, case_id, request_path, entry.request_digest, failed, pairs)
    return {
        "case_id": case_id,
        "kernel_cases": capture_state.kernel_cases,
        "auditor_dataset": _write_agent_dataset(capture_state, "auditor", capture_state.auditor),
        "producer_dataset": _write_agent_dataset(capture_state, "producer", capture_state.producer),
        "files": capture_state.files,
        "skipped": capture_state.skipped,
    }
