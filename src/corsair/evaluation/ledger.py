"""Evaluator-side gate ledger: which stage stopped each round of a scored result.

The ledger only describes a result the kernel already decided; it never decides a
label, never reaches an agent, tool or workflow input, and reads no oracle. Every
entry is derived from data recorded in the ``InvestigationResult`` plus, for rounds
that reached the kernel, the prepared case recovered from that round's own validated
receipts. A round whose receipts do not validate is reported as unverified rather
than classified from unverified fields.
"""

from collections import Counter
from collections.abc import Iterable, Mapping

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    ExecutionStatus,
    FixStatus,
    InvestigationResult,
    NoGroundedCandidate,
    PreparedCase,
    RoleOutcome,
    RoundResult,
    Verdict,
    format_diagnostic,
)
from corsair.policies.verdicts import decide, fix_status, session_verdict
from corsair.settings import Settings

RoundKey = tuple[int, int]

# Case-level stops the workflow records only as its terminal reason.
_BUDGET_REASONS = frozenset(
    {
        "Investigation budget exhausted.",
        "Investigation elapsed-time budget exhausted.",
        "No budget remains for review.",
    }
)

# Fixed adapter reasons behind the non-operational producer_invalid/audit_invalid
# gates. Qualifying them separates "ran out of calls" from "returned bad output".
_INVALID_QUALIFIERS = (
    ("exhausted its runtime skill loader budget", "loader_budget"),
    ("exhausted its tool-call budget", "tool_budget"),
    ("exhausted its LLM-call budget", "llm_budget"),
    ("no remaining model-call budget", "llm_budget"),
    ("returned no structured", "no_output"),
    ("returned malformed", "malformed"),
    ("plan revision must equal", "plan_revision"),
    ("plan parent_revision", "plan_revision"),
)
_QUALIFIED_GATES = frozenset({"producer_invalid", "audit_invalid"})


def _entry(
    session: int | None, round_index: int | None, stage: str, gate: str, reason: str
) -> dict:
    return {
        "session": session,
        "round": round_index,
        "stage": stage,
        "gate": gate,
        "reason": format_diagnostic(reason),
    }


def _qualified(gate: str, reason: str) -> str:
    if gate in _QUALIFIED_GATES:
        for marker, qualifier in _INVALID_QUALIFIERS:
            if marker in reason:
                return f"{gate}:{qualifier}"
    return gate


def _audit_gate(item: RoundResult) -> tuple[str, str]:
    """The audit's own non-accepting decision, formed without any run outcome."""
    audit = item.audit
    assert audit is not None
    if audit.review is None:
        if audit.feedback is not None:
            return _qualified(audit.feedback.gate, audit.feedback.reason), audit.feedback.reason
        return "audit_missing", "independent audit is missing"
    if audit.review.decision is AuditDecision.INSUFFICIENT:
        return "audit_insufficient_context", audit.review.reason
    return "audit_reject", audit.review.reason


def _kernel_entry(item: RoundResult, prepared: PreparedCase) -> dict:
    """Name the first kernel gate, in session_verdict order, that stopped the round."""
    observation, audit = item.observation, item.audit
    assert observation is not None and audit is not None
    session, index = item.session, item.index
    _, status, reason = decide(prepared, observation, audit)
    if status is not ExecutionStatus.COMPLETED:
        return _entry(session, index, "kernel", "kernel_error", reason)
    outcome = session_verdict(prepared, observation, audit, FixStatus.NOT_REQUESTED)
    if outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED:
        return _entry(session, index, "kernel", "demonstrated", outcome.reason)
    if outcome.verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED:
        return _entry(session, index, "kernel", "component_demonstrated", outcome.reason)
    if outcome.clean_negative:
        return _entry(session, index, "kernel", "clean_negative", outcome.reason)
    if outcome.verdict is Verdict.UNABLE_TO_RUN:
        return _entry(session, index, "kernel", "target_unbound", outcome.reason)
    assert observation.control is not None and observation.adversarial is not None
    line = prepared.finding.line
    if line not in observation.control.covered_lines or (
        line not in observation.adversarial.covered_lines
    ):
        return _entry(session, index, "kernel", "coverage", outcome.reason)
    roles = (observation.control.outcome, observation.adversarial.outcome)
    if RoleOutcome.INVALID in roles:
        return _entry(session, index, "evidence", "probe_invalid", reason)
    # fix_status classifies any validated pair: NOT_BLOCKED is a control-vs-exploit
    # differential, DEMONSTRATION_BLOCKED is both runs holding. Either would have been
    # decisive with an accepted audit, so the audit is what stopped this round.
    if fix_status(observation) in {FixStatus.NOT_BLOCKED, FixStatus.DEMONSTRATION_BLOCKED}:
        gate, audit_reason = _audit_gate(item)
        return _entry(session, index, "audit", gate, audit_reason)
    return _entry(session, index, "kernel", "no_differential", reason)


def _round_entry(item: RoundResult, prepared: PreparedCase | None) -> tuple[dict, bool]:
    """One round's stopping entry and whether it was an operational stop."""
    session, index = item.session, item.index
    producer = item.producer
    if producer.decision is not None and isinstance(producer.decision.root, NoGroundedCandidate):
        return _entry(
            session, index, "producer", "producer_abstained", producer.decision.root.reason
        ), False
    if producer.submission_for_verification() is None:
        feedback = producer.feedback
        if feedback is None:
            return _entry(
                session, index, "producer", "producer_no_submission", "No submission"
            ), False
        gate = _qualified(feedback.gate, feedback.reason)
        return _entry(session, index, "producer", gate, feedback.reason), feedback.operational
    observation = item.observation
    if observation is None:
        return _entry(
            session, index, "evidence", "evidence_not_run", "no observation was recorded"
        ), False
    if observation.feedback is not None:
        feedback = observation.feedback
        return _entry(
            session, index, "evidence", feedback.gate, feedback.reason
        ), feedback.operational
    audit = item.audit
    if audit is None:
        # A missing stage was stopped outside the round; the case-level entry names why.
        return _entry(session, index, "audit", "audit_not_run", "no audit was recorded"), False
    if audit.feedback is not None and audit.feedback.operational:
        return _entry(session, index, "audit", audit.feedback.gate, audit.feedback.reason), True
    if prepared is None:
        return _entry(
            session,
            index,
            "kernel",
            "evidence_unverified",
            "the round's persisted receipts did not validate",
        ), False
    entry = _kernel_entry(item, prepared)
    return entry, entry["gate"] == "kernel_error"


def _clean_sessions(result: InvestigationResult, entries: Mapping[RoundKey, dict]) -> int:
    """Independent sessions whose last evaluated round was a clean negative."""
    last_evaluated: dict[int, dict] = {}
    for item in result.rounds:
        if item.observation is not None and item.audit is not None:
            last_evaluated[item.session] = entries[(item.session, item.index)]
    clean = {
        session for session, entry in last_evaluated.items() if entry["gate"] == "clean_negative"
    }
    if result.execution_status is not ExecutionStatus.COMPLETED and result.rounds:
        # A terminal operational failure overrides the last session's outcome.
        clean.discard(result.rounds[-1].session)
    return len(clean)


def gate_ledger(
    result: InvestigationResult, verified: Mapping[RoundKey, PreparedCase] | None = None
) -> list[dict]:
    """Pure: one stopping entry per recorded round, then any case-level policy stops.

    ``verified`` maps ``(session, round)`` to the prepared case recovered from that
    round's validated receipts; rounds absent from it never reach kernel gates.
    """
    verified = verified or {}
    entries: dict[RoundKey, dict] = {}
    ledger: list[dict] = []
    last_operational = False
    for item in result.rounds:
        entry, last_operational = _round_entry(item, verified.get((item.session, item.index)))
        entries[(item.session, item.index)] = entry
        ledger.append(entry)
    session = result.rounds[-1].session if result.rounds else None
    if result.fix_status is FixStatus.NOT_BLOCKED:
        ledger.append(
            _entry(
                session,
                None,
                "policy",
                "fix_not_blocked",
                "exploit still violates on the fixed revision",
            )
        )
    threshold = result.manifest.negative_threshold if result.manifest is not None else 2
    clean = _clean_sessions(result, entries)
    if 0 < clean < threshold and result.verdict in {None, Verdict.INCONCLUSIVE}:
        ledger.append(
            _entry(
                session,
                None,
                "policy",
                "negative_threshold_unmet",
                f"{clean} of {threshold} required independent clean negatives",
            )
        )
    if result.reason in _BUDGET_REASONS:
        ledger.append(_entry(session, None, "policy", "budget_exhausted", result.reason))
    if result.execution_status is not ExecutionStatus.COMPLETED and not last_operational:
        gate = f"execution_{result.execution_status.value.lower()}"
        ledger.append(_entry(session, None, "policy", gate, result.reason))
    if not ledger:
        ledger.append(_entry(None, None, "policy", "no_rounds", result.reason))
    return ledger


def verified_rounds(
    result: InvestigationResult, store: ArtifactStore | None
) -> dict[RoundKey, PreparedCase]:
    """Recover each round's prepared case from its own validated receipts."""
    if result.manifest is None or store is None:
        return {}
    # Imported on use: verification loads the Docker SDK, which saved-report reads never need.
    from corsair.steps.verification import EvidenceVerifier

    verifier = EvidenceVerifier(Settings(), store)
    verified: dict[RoundKey, PreparedCase] = {}
    for item in result.rounds:
        submission = item.producer.submission_for_verification()
        if item.observation is None or item.audit is None or submission is None:
            continue
        prepared = verifier.validate_saved(item.observation, submission, result.manifest)
        if prepared is not None and prepared.case_id == result.case_id:
            verified[(item.session, item.index)] = prepared
    return verified


def ledger_counts(ledgers: Iterable[Iterable[dict]]) -> dict[str, int]:
    """Count entries per gate, most frequent first, ties by gate name."""
    counts = Counter(entry["gate"] for ledger in ledgers for entry in ledger)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
