"""Plain-language explanation of a result the kernel already decided.

Pure: it reads an ``InvestigationResult`` and its gate ledger and returns ordered
statements. It never decides or changes a label, performs no evidence I/O and reads
no oracle. Every sentence is fixed text over enum values, counts and gate names; the
explanation never reads a payload, hypothesis, plan, audit rule or reason, producer
abstention, feedback reason, the result's ``reason`` or a ledger entry's ``reason``,
because any of those can carry model text.

Statement kinds, in output order: ``verdict``, ``rule``, ``session`` and
``shortfall`` (per session), ``policy``, ``fix``, ``change``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from corsair.contracts import (
    AuditOutput,
    ExecutionStatus,
    FixStatus,
    InvestigationResult,
    RoleObservation,
    RoleOutcome,
    RoundResult,
    Scope,
    Verdict,
)

# Default evidence policy, used only when an older result recorded no manifest.
_DEFAULT_THRESHOLD = 2
_DEFAULT_SESSIONS = 2

# The verdict table (policies/verdicts.py) in one sentence per label.
_RULES: dict[Verdict, str] = {
    Verdict.EXPLOIT_DEMONSTRATED: (
        "A session on the vulnerable revision showed the control held and the exploit violated, "
        "both runs executed the declared target line and the blind audit accepted, for a "
        "finding that claimed component scope."
    ),
    Verdict.COMPONENT_EXPLOIT_DEMONSTRATED: (
        "A session showed the same control-versus-exploit differential with coverage and an "
        "accepted audit, but the finding claimed application scope and the recipe exercises "
        "only the component seam, so reachability from the application entry point was not "
        "established."
    ),
    Verdict.EXPLOIT_NOT_DEMONSTRATED: (
        "At least the required number of independent sessions each ended in a clean negative "
        "(control held, exploit held, both runs covered the declared target line, audit "
        "accepted) and no session demonstrated the exploit. It is scoped to the exercised "
        "finding, payloads, revision and runtime (sensitivity unverified)."
    ),
    Verdict.INCONCLUSIVE: (
        "No session demonstrated the exploit and fewer than the required independent clean "
        "negatives were reached. It is never a negative security finding."
    ),
    Verdict.UNABLE_TO_RUN: (
        "No session could run: an operational gate blocked every session before decisive "
        "evidence existed. It is never a negative security finding."
    ),
    Verdict.ERROR: (
        "A session faulted (infrastructure, evidence integrity or cleanup confirmation) and no "
        "session reached a decisive signal. It is never a negative security finding."
    ),
}

# Ledger gate (before any ':qualifier') -> (the fact that fell short, what it needed).
_GATES: dict[str, tuple[str, str]] = {
    "producer_abstained": (
        "the producer abstained instead of proposing a payload pair",
        "a grounded payload-pair proposal for the recipe's seam",
    ),
    "producer_no_submission": (
        "the producer made no proposal",
        "a payload-pair proposal admitted for verification",
    ),
    "producer_invalid": (
        "the producer returned no admissible proposal",
        "a structured payload-pair proposal within the episode budget",
    ),
    "evidence_not_run": (
        "no observation was recorded for the pair",
        "a recorded observation of the pair",
    ),
    "audit_not_run": (
        "no audit was recorded for the pair",
        "a recorded blind audit of the pair",
    ),
    "evidence_unverified": (
        "the round's persisted receipts did not re-validate, so its kernel facts were not "
        "re-derived",
        "receipts that re-validate (see `corsair inspect RUN_ID --evidence`)",
    ),
    "kernel_error": (
        "the observation failed an integrity check (artifact, source digest, cleanup "
        "confirmation or role execution)",
        "a complete, cleanup-confirmed observation of both roles",
    ),
    "target_unbound": (
        "the finding declares no target line to bind the demonstration to",
        "a declared target line the recipe binds",
    ),
    "coverage": (
        "the declared target line did not execute in both the control and the exploit run",
        "a pair whose control and exploit runs both execute the declared target line",
    ),
    "probe_invalid": (
        "a role's native evidence was invalid",
        "natively valid evidence for both roles",
    ),
    "no_differential": (
        "the pair formed neither a differential nor a clean negative: the control did not hold "
        "validly, or the exploit neither violated nor held validly",
        "the control holding with the exploit violating (a demonstration) or holding "
        "(a clean negative)",
    ),
    "audit_reject": (
        "the blind audit rejected the pair",
        "a blind audit that accepts the pair",
    ),
    "audit_insufficient_context": (
        "the blind audit returned INSUFFICIENT_CONTEXT",
        "a blind audit that accepts the pair",
    ),
    "audit_missing": (
        "the independent audit is missing",
        "a blind audit that accepts the pair",
    ),
    "audit_invalid": (
        "the auditor returned no admissible review",
        "a blind audit that accepts the pair",
    ),
    "no_rounds": ("no round was recorded", "a round that reaches the producer"),
    "execution_blocked": (
        "an operational gate blocked the run (for example target binding, source admission "
        "or build replay)",
        "the blocking operational gate passing",
    ),
    "execution_error": (
        "the run faulted operationally",
        "the run completing without an operational fault",
    ),
    "execution_cancelled": ("the run was cancelled", "a run that is not cancelled"),
}
_QUALIFIERS = {
    "llm_budget": "the episode ran out of LLM calls",
    "tool_budget": "the episode ran out of tool calls",
    "loader_budget": "the episode ran out of runtime skill loads",
    "no_output": "the episode returned no structured output",
    "malformed": "the episode returned malformed output",
    "plan_revision": "the plan revision did not match the round",
}
_DEMONSTRATED = frozenset({"demonstrated", "component_demonstrated"})
_DECISIVE = frozenset({*_DEMONSTRATED, "clean_negative"})
# Ledger gates that are only reached after the both-runs coverage gate passed.
_COVERED = frozenset(
    {
        *_DECISIVE,
        "probe_invalid",
        "no_differential",
        "audit_reject",
        "audit_insufficient_context",
        "audit_missing",
        "audit_invalid",
    }
)
_OUTCOME_WORDS = {
    RoleOutcome.HELD: "held",
    RoleOutcome.VIOLATION: "violated",
    RoleOutcome.INVALID: "invalid",
    RoleOutcome.ERROR: "errored",
}
_FIX_TEXT = {
    FixStatus.NOT_REQUESTED: "No fixed revision was evaluated.",
    FixStatus.DEMONSTRATION_BLOCKED: (
        "On the fixed revision the control held and the exploit held: the fix blocked this "
        "demonstration. That is confirmation of this demonstration, not a patch certificate."
    ),
    FixStatus.NOT_BLOCKED: (
        "On the fixed revision the exploit still violated: the fix is incomplete or the "
        "demonstration is suspect, so a demonstration label is withheld."
    ),
    FixStatus.UNVERIFIED: (
        "The fixed-revision run could not be cleanly evaluated; the vulnerable-revision "
        "differential stands without confirmation."
    ),
}
_SESSION_REQUIREMENT = (
    "A session demonstrates only with the control held, the exploit violated, both runs "
    "covering the declared target line and an accepting audit; it is a clean negative only "
    "with the same facts and the exploit held."
)


def _statement(kind: str, text: str, *, session: int | None = None, gate: str | None = None):
    return {"kind": kind, "session": session, "gate": gate, "text": text}


def _gate_text(gate: str, stage: str | None) -> tuple[str, str]:
    """The fixed fact and requirement for a ledger gate; unknown gates name their stage."""
    base, _, qualifier = gate.partition(":")
    if base in _GATES:
        fell_short, needed = _GATES[base]
    else:
        where = f"the {stage} stage" if stage else "the run"
        fell_short, needed = f"{where} stopped at gate {gate}", f"{where} passing gate {gate}"
    if qualifier in _QUALIFIERS:
        fell_short = f"{fell_short} ({_QUALIFIERS[qualifier]})"
    return fell_short, needed


def _role(role: RoleObservation | None) -> str:
    if role is None:
        return "not observed"
    if not role.target_executed:
        return "did not run the target"
    return _OUTCOME_WORDS[role.outcome]


def _audit(audit: AuditOutput) -> str:
    if audit.review is not None:
        return audit.review.decision.value
    if audit.feedback is not None:
        return f"stopped at {audit.feedback.gate}"
    return "missing"


def _covered(gate: str | None) -> str:
    if gate in _COVERED:
        return "yes"
    if gate == "coverage":
        return "no"
    return "unknown"


def _evaluated(rounds: Sequence[RoundResult]) -> RoundResult | None:
    """The session's last round with both an observation and an audit (session_verdict's)."""
    return next(
        (
            item
            for item in reversed(rounds)
            if item.observation is not None and item.audit is not None
        ),
        None,
    )


def _sessions(result: InvestigationResult) -> dict[int, list[RoundResult]]:
    sessions: dict[int, list[RoundResult]] = {}
    for item in result.rounds:
        sessions.setdefault(item.session, []).append(item)
    return sessions


def _round_entries(ledger: Sequence[Mapping[str, Any]]) -> dict[tuple[int, int], Mapping]:
    return {
        (entry["session"], entry["round"]): entry
        for entry in ledger
        if isinstance(entry.get("session"), int) and isinstance(entry.get("round"), int)
    }


def _policy_gates(ledger: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [entry for entry in ledger if entry.get("stage") == "policy"]


def _clean_negatives(
    result: InvestigationResult, sessions: Mapping[int, list[RoundResult]], entries: Mapping
) -> int:
    """Sessions whose last evaluated round was a clean negative, as the ledger counts them."""
    clean = set()
    for session, rounds in sessions.items():
        decided = _evaluated(rounds)
        entry = entries.get((session, decided.index)) if decided is not None else None
        if entry is not None and entry.get("gate") == "clean_negative":
            clean.add(session)
    if result.execution_status is not ExecutionStatus.COMPLETED and result.rounds:
        # A terminal operational failure overrides the last session's outcome.
        clean.discard(result.rounds[-1].session)
    return len(clean)


def _session_statements(
    result: InvestigationResult,
    session: int,
    rounds: list[RoundResult],
    entries: Mapping[tuple[int, int], Mapping],
    terminal_stop: Mapping[str, Any] | None,
) -> tuple[list[dict], tuple[str, str] | None]:
    """The session's decisive facts, and its (gate, requirement) when it fell short."""
    stops = [
        str(entries[(session, item.index)]["gate"])
        for item in rounds
        if (session, item.index) in entries
    ]
    decided = _evaluated(rounds)
    facts = (
        f"Session {session}: {len(rounds)} round(s), stopped at {', '.join(stops) or 'no gate'}."
    )
    deciding: Mapping[str, Any] | None
    if decided is not None:
        assert decided.observation is not None and decided.audit is not None
        deciding = entries.get((session, decided.index))
        gate = str(deciding["gate"]) if deciding else None
        facts += (
            f" Last evaluated round {decided.index}: control {_role(decided.observation.control)},"
            f" exploit {_role(decided.observation.adversarial)}, target line covered in both runs:"
            f" {_covered(gate)}, audit {_audit(decided.audit)}."
        )
    else:
        deciding = entries.get((session, rounds[-1].index))
        facts += " No round reached both evidence and audit."
    statements = [_statement("session", facts, session=session)]
    demonstrated = deciding is not None and deciding["gate"] in _DEMONSTRATED
    if terminal_stop is not None and session == result.rounds[-1].session and not demonstrated:
        # A later operational stop overrides the session's outcome unless it demonstrated.
        deciding = terminal_stop
    if deciding is None:
        return statements, None
    gate_name = str(deciding["gate"])
    if gate_name in _DECISIVE:
        ended = {
            "demonstrated": "showed the control-versus-exploit differential on the vulnerable "
            "revision",
            "component_demonstrated": "showed the control-versus-exploit differential at "
            "component scope",
            "clean_negative": "ended in a clean negative",
        }[gate_name]
        statements.append(_statement("session", f"Session {session} {ended}.", session=session))
        return statements, None
    fell_short, needed = _gate_text(gate_name, deciding.get("stage"))
    statements.append(
        _statement(
            "shortfall",
            f"Session {session} fell short at {gate_name}: {fell_short}.",
            session=session,
            gate=gate_name,
        )
    )
    return statements, (gate_name, needed)


def _terminal_stop(
    result: InvestigationResult, ledger: Sequence[Mapping[str, Any]], entries: Mapping
) -> Mapping[str, Any] | None:
    """The operational stop that overrides the last session, when the run did not complete."""
    if result.execution_status is ExecutionStatus.COMPLETED:
        return None
    for entry in _policy_gates(ledger):
        if str(entry.get("gate", "")).startswith("execution_"):
            return entry
    if result.rounds:
        last = result.rounds[-1]
        return entries.get((last.session, last.index))
    return None


def _policy_statements(
    result: InvestigationResult,
    ledger: Sequence[Mapping[str, Any]],
    sessions_run: int,
    clean: int,
) -> list[dict]:
    manifest = result.manifest
    if manifest is None:
        policy = (
            "Evidence policy: not recorded (no manifest); the ledger assumes "
            f"{_DEFAULT_THRESHOLD} required clean negatives."
        )
    else:
        policy = (
            f"Evidence policy: {manifest.negative_threshold} independent clean negatives "
            f"required for EXPLOIT_NOT_DEMONSTRATED, at most {manifest.max_sessions} session(s)."
        )
    policy += f" {sessions_run} session(s) ran and {clean} clean negative(s) were reached."
    statements = [_statement("policy", policy)]
    gates = {str(entry.get("gate")) for entry in _policy_gates(ledger)}
    if "budget_exhausted" in gates:
        statements.append(
            _statement(
                "policy",
                "The request budget (LLM calls, tool calls or elapsed time) ran out before the "
                "investigation finished.",
                gate="budget_exhausted",
            )
        )
    budget = "Budget limits belong to the request and are identified by its digest"
    statements.append(
        _statement(
            "policy",
            f"{budget} {manifest.request_digest[:12]}." if manifest else f"{budget}; not recorded.",
        )
    )
    return statements


def _threshold(result: InvestigationResult) -> tuple[int, int]:
    manifest = result.manifest
    if manifest is None:
        return _DEFAULT_THRESHOLD, _DEFAULT_SESSIONS
    return manifest.negative_threshold, manifest.max_sessions


def _demonstration_label(result: InvestigationResult) -> str:
    if result.scope is Scope.APPLICATION:
        return "COMPONENT_EXPLOIT_DEMONSTRATED"
    return "EXPLOIT_DEMONSTRATED"


def _inconclusive_changes(
    result: InvestigationResult,
    ledger: Sequence[Mapping[str, Any]],
    sessions_run: int,
    clean: int,
    shortfalls: list[tuple[int | None, str, str]],
) -> list[dict]:
    threshold, max_sessions = _threshold(result)
    gates = {str(entry.get("gate")) for entry in _policy_gates(ledger)}
    changes: list[dict] = []
    if result.fix_status is FixStatus.NOT_BLOCKED:
        changes.append(
            _statement(
                "change",
                "The vulnerable-revision demonstration is withheld while the fixed revision "
                "still shows the violation; a fix that blocks the exploit "
                f"(DEMONSTRATION_BLOCKED) would let it stand as {_demonstration_label(result)}.",
                gate="fix_not_blocked",
            )
        )
    if 0 < clean < threshold:
        missing = threshold - clean
        text = (
            f"{missing} more independent clean-negative session(s) would make it "
            f"EXPLOIT_NOT_DEMONSTRATED; one demonstrating session would make it "
            f"{_demonstration_label(result)}."
        )
        if max_sessions < threshold:
            text += (
                f" With max_sessions {max_sessions} below negative_threshold {threshold} this "
                "configuration can never reach EXPLOIT_NOT_DEMONSTRATED."
            )
        elif "budget_exhausted" in gates:
            text += " This run's budget ran out before another session could start."
        elif sessions_run >= max_sessions:
            text += f" This run used all {max_sessions} allowed session(s)."
        changes.append(_statement("change", text, gate="negative_threshold_unmet"))
    for session, gate, needed in shortfalls:
        subject = "The run" if session is None else f"Session {session}"
        changes.append(
            _statement("change", f"{subject} needed {needed}.", session=session, gate=gate)
        )
    changes.append(_statement("change", _SESSION_REQUIREMENT))
    return changes


def _changes(
    result: InvestigationResult,
    ledger: Sequence[Mapping[str, Any]],
    sessions_run: int,
    clean: int,
    shortfalls: list[tuple[int | None, str, str]],
) -> list[dict]:
    """What would change this label, derived from the verdict table."""
    verdict = result.verdict
    withheld = (
        "Only a fixed-revision run on which the exploit still violates (NOT_BLOCKED) withholds "
        "this label, making it INCONCLUSIVE; clean negatives in other sessions never lower it."
    )
    if verdict is Verdict.EXPLOIT_DEMONSTRATED:
        changes = [_statement("change", withheld)]
        if result.fix_status in {FixStatus.NOT_REQUESTED, FixStatus.UNVERIFIED}:
            changes.append(
                _statement(
                    "change",
                    "A fixed revision that blocks the exploit would add optional confirmation.",
                )
            )
        return changes
    if verdict is Verdict.COMPONENT_EXPLOIT_DEMONSTRATED:
        return [
            _statement(
                "change",
                "EXPLOIT_DEMONSTRATED needs a finding that claims component scope; for an "
                "application-scope claim no implemented recipe establishes reachability from "
                "the application entry point.",
            ),
            _statement(
                "change",
                "Developer next step: harden the component or prove an upstream guard blocks "
                "the input.",
            ),
            _statement("change", withheld),
        ]
    if verdict is Verdict.EXPLOIT_NOT_DEMONSTRATED:
        return [
            _statement(
                "change",
                "One session that demonstrates the differential would make it "
                f"{_demonstration_label(result)}.",
            ),
            _statement(
                "change",
                "It covers only the exercised payload pairs, revision and runtime; another "
                "target line, payload pair or revision is a new investigation, not a "
                "refutation of this one.",
            ),
        ]
    if verdict is Verdict.INCONCLUSIVE:
        return _inconclusive_changes(result, ledger, sessions_run, clean, shortfalls)
    stop = next((gate for _, gate, _ in reversed(shortfalls)), None)
    if verdict is Verdict.UNABLE_TO_RUN:
        return [
            _statement(
                "change",
                "The kernel decides a label only after the blocking gate passes"
                + (f" ({stop})" if stop else "")
                + ": a declared target line the recipe binds, admitted source and a successful "
                "build replay. Rerunning the same request reproduces the stop.",
                gate=stop,
            )
        ]
    if verdict is Verdict.ERROR:
        return [
            _statement(
                "change",
                "An ERROR carries no security signal; resolve the fault"
                + (f" at {stop}" if stop else "")
                + " (`corsair doctor`, `corsair inspect RUN_ID --evidence`) and investigate "
                "again under a new run id.",
                gate=stop,
            )
        ]
    return [
        _statement(
            "change",
            "No verdict was recorded; `corsair rescore` applies the current verdict policy to "
            "the saved evidence.",
        )
    ]


def explain_result(
    result: InvestigationResult, ledger: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Pure: ordered statements explaining ``result.verdict`` from its rounds and ledger.

    ``ledger`` is the result's gate ledger (``evaluation.ledger.gate_ledger``); only its
    ``session``, ``round``, ``stage`` and ``gate`` keys are read, never ``reason``.
    """
    verdict = result.verdict
    statements = [
        _statement(
            "verdict",
            f"Verdict {verdict.value if verdict else 'not recorded'}: execution "
            f"{result.execution_status.value}, claimed scope {result.scope.value}, fix "
            f"{result.fix_status.value}.",
        )
    ]
    if verdict is not None:
        statements.append(_statement("rule", _RULES[verdict]))
    sessions = _sessions(result)
    entries = _round_entries(ledger)
    terminal_stop = _terminal_stop(result, ledger, entries)
    shortfalls: list[tuple[int | None, str, str]] = []
    for session, rounds in sessions.items():
        found, shortfall = _session_statements(result, session, rounds, entries, terminal_stop)
        statements.extend(found)
        if shortfall is not None:
            shortfalls.append((session, *shortfall))
    if not sessions:
        stop = terminal_stop or next(iter(_policy_gates(ledger)), None)
        if stop is not None:
            gate = str(stop["gate"])
            fell_short, needed = _gate_text(gate, stop.get("stage"))
            statements.append(_statement("shortfall", f"No round ran: {fell_short}.", gate=gate))
            shortfalls.append((None, gate, needed))
        else:
            statements.append(_statement("shortfall", "No round ran."))
    clean = _clean_negatives(result, sessions, entries)
    statements.extend(_policy_statements(result, ledger, len(sessions), clean))
    statements.append(_statement("fix", _FIX_TEXT[result.fix_status]))
    statements.extend(_changes(result, ledger, len(sessions), clean, shortfalls))
    return statements
