"""The Decide stage: a fixed rule table over recorded facts (redesign section 5, amended by section 13 and the
corrections from review of SPEC-0082; D4).

No model runs here. Rules are data, evaluated top to bottom; the first whose condition matches fixes the label,
the finding and the terminal reason, and its id is stored on the Verdict so a report can cite it. A rule may
refine its terminal reason from the facts (for example R3 names ``probe_not_run`` when the control never
started) but never its label.

Every INCONCLUSIVE from the evidence has its own reason. A probe that did not give a decisive outcome maps to
``probe_not_run`` (not run, or no run recorded), ``probe_errored`` or ``probe_anomalous``, in that order of
precedence; ``no_valid_observation`` is left for the rest. The fix result uses the same mapping for its reason.

ERROR is scoped to the vulnerable revision: R1 reads only the chain's ``stopped`` reason (which the chain sets only
for failures before or on the vulnerable revision) and vulnerable-revision ``infra`` runs. A failure on the fixed
revision (``fix_stopped``, or a fixed ``infra`` run) only makes the fix ``not_verified``.

Choices the design left open, recorded here:

- ``budget_exhausted`` is a stop, not a fault of the platform or the provider, and says nothing about the
  finding, so it is INCONCLUSIVE, not ERROR. It has its own rule, R7, evaluated right after R1 so that a budget
  stop is never misreported as ``test_invalid`` because the review never ran.
- R1 also fires when a vulnerable-revision run is ``infra``: an uncertain execution is never a decisive one.
- ``cleanup_unconfirmed`` from the chain is an infrastructure fault (R1).
- A ``stopped`` reason that none of R0, R1 and R7 owns (for example ``probe_not_run`` after the single D3
  correction) is not a label by itself: the evidence rules below still read the recorded runs.
- R3 names ``control_failed`` only when the control's own assertion failed (``assertion_failed``); any other
  non-passing control maps to ``probe_not_run``, ``probe_errored`` or ``probe_anomalous``.
- A review or run bound to a different frozen patch than the vulnerable runs counts as missing.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .contracts import (BuildResult, Case, Label, Origin, Outcome, ProbePlan, ProbeRun, Runtime, TerminalReason,
                        Validity, Verdict)

R = TerminalReason


@dataclass(frozen=True)
class Facts:
    """Everything the rules read, gathered once so each condition stays a one-liner."""

    case: Case
    runtime: Runtime | None
    build: BuildResult | None
    plan: ProbePlan | None
    stopped: TerminalReason | None
    fix_stopped: TerminalReason | None
    runs: dict[tuple[str, str], ProbeRun]
    validity: dict[str, Validity]
    patch_sha256: str | None

    def outcome(self, revision: str, role: str) -> Outcome | None:
        run = self.runs.get((revision, role))
        return None if run is None else run.outcome

    def bound_validity(self, revision: str) -> Validity | None:
        """The review of this revision, only if it judged the same frozen patch the runs executed."""
        validity = self.validity.get(revision)
        if validity is None or (self.patch_sha256 is not None and validity.patch_sha256 != self.patch_sha256):
            return None
        return validity


@dataclass(frozen=True)
class Rule:
    """One row of the table. ``match`` returns the terminal reason when the rule applies, else None."""

    id: str
    condition: str
    label: Label
    finding: Literal["reproduced", "not_reproduced", "inconclusive", "none"]
    match: Callable[[Facts], TerminalReason | None]


def _r0(f: Facts) -> TerminalReason | None:
    if f.stopped in (R.NO_RUNTIME, R.BUILD_FAILED, R.UNSUPPORTED_SCOPE, R.PLAN_UNRESOLVED):
        return f.stopped
    if f.runtime is None:
        return R.NO_RUNTIME
    if f.plan is not None and f.plan.status == "unsupported_scope":
        return R.UNSUPPORTED_SCOPE
    if f.plan is not None and f.plan.status == "target_not_found":
        return R.PLAN_UNRESOLVED
    if f.build is not None and not f.build.replayed:
        return R.BUILD_FAILED
    return None


def _r1(f: Facts) -> TerminalReason | None:
    if f.stopped in (R.PROVIDER_ERROR, R.INFRA_ERROR, R.CLEANUP_UNCONFIRMED):
        return f.stopped
    if any(run.outcome is Outcome.INFRA for (revision, _), run in f.runs.items() if revision == "vulnerable"):
        return R.INFRA_ERROR
    return None


def _r7(f: Facts) -> TerminalReason | None:
    return R.BUDGET_EXHAUSTED if f.stopped is R.BUDGET_EXHAUSTED else None


def _r2(f: Facts) -> TerminalReason | None:
    validity = f.bound_validity("vulnerable")
    if validity is None or not (validity.control.valid and validity.exploit.valid):
        return R.TEST_INVALID
    return None


_PROBE_REASONS = ((R.PROBE_NOT_RUN, (None, Outcome.NOT_RUN)), (R.PROBE_ERRORED, (Outcome.ERRORED,)),
                  (R.PROBE_ANOMALOUS, (Outcome.ANOMALOUS,)))
"""Non-decisive probe outcomes and their reasons, in order of precedence; a missing run counts as not run."""


def _probe_reason(*outcomes: Outcome | None) -> TerminalReason | None:
    """The first reason in precedence order that any of these outcomes shows, else None."""
    for reason, shown_by in _PROBE_REASONS:
        if any(outcome in shown_by for outcome in outcomes):
            return reason
    return None


def _r3(f: Facts) -> TerminalReason | None:
    outcome = f.outcome("vulnerable", "control")
    if outcome is Outcome.PASSED:
        return None
    if outcome is Outcome.ASSERTION_FAILED:
        return R.CONTROL_FAILED
    return _probe_reason(outcome) or R.NO_VALID_OBSERVATION


def _r4(f: Facts) -> TerminalReason | None:
    return R.OK if f.outcome("vulnerable", "exploit") is Outcome.ASSERTION_FAILED else None


def _r5(f: Facts) -> TerminalReason | None:
    return R.OK if f.outcome("vulnerable", "exploit") is Outcome.PASSED else None


def _r6(f: Facts) -> TerminalReason | None:
    return _probe_reason(f.outcome("vulnerable", "exploit")) or R.NO_VALID_OBSERVATION


RULES: tuple[Rule, ...] = (
    Rule("R0", "Stopped before evidence: no matrix row, build failed, plan unsupported_scope or target_not_found",
         Label.UNABLE_TO_RUN, "none", _r0),
    Rule("R1", "Provider or infrastructure failure affecting the vulnerable revision, including an infra run on it",
         Label.ERROR, "none", _r1),
    Rule("R7", "Budget exhausted before a decisive observation", Label.INCONCLUSIVE, "inconclusive", _r7),
    Rule("R2", "Review missing, bound to another patch, or negative for either probe on the vulnerable revision",
         Label.INCONCLUSIVE, "inconclusive", _r2),
    Rule("R3", "Vulnerable control not passed: control_failed when its assertion failed, else probe_not_run, "
         "probe_errored or probe_anomalous", Label.INCONCLUSIVE, "inconclusive", _r3),
    Rule("R4", "Vulnerable exploit assertion_failed", Label.LIKELY_EXPLOITABLE, "reproduced", _r4),
    Rule("R5", "Vulnerable exploit passed", Label.LIKELY_NOT_EXPLOITABLE, "not_reproduced", _r5),
    Rule("R6", "Anything else: probe_not_run, probe_errored or probe_anomalous from the vulnerable exploit, else "
         "no_valid_observation", Label.INCONCLUSIVE, "inconclusive", _r6),
)
"""Evaluation order is the tuple order; ids name rules, not ranks (R7 is checked after R1)."""

FIX_RULE = ("verified: R4 on the vulnerable revision, control and exploit passed on the fixed revision, a positive "
            "review of the fixed revision, and one frozen patch throughout; not_applicable without a fixed revision; "
            "otherwise not_verified, with the first matching reason: the verdict's own reason when it is not R4 "
            "(no_valid_observation for R5), the fixed-revision stop, infra_error for a fixed infra run, test_invalid "
            "for a missing or negative fixed review, probe_not_run / probe_errored / probe_anomalous over the fixed "
            "runs, control_failed for a fixed control assertion failure, else no_valid_observation")


def _fix(f: Facts, rule: Rule, reason: TerminalReason
         ) -> tuple[Literal["verified", "not_verified", "not_applicable"], TerminalReason | None]:
    if f.case.fixed_revision is None:
        return "not_applicable", None
    if rule.id != "R4":
        return "not_verified", reason if reason is not R.OK else R.NO_VALID_OBSERVATION
    if f.fix_stopped is not None:
        return "not_verified", f.fix_stopped
    control, exploit = f.outcome("fixed", "control"), f.outcome("fixed", "exploit")
    if Outcome.INFRA in (control, exploit):
        return "not_verified", R.INFRA_ERROR
    validity = f.bound_validity("fixed")
    if f.patch_sha256 is None or validity is None or not (validity.control.valid and validity.exploit.valid):
        return "not_verified", R.TEST_INVALID
    if control is Outcome.PASSED and exploit is Outcome.PASSED:
        return "verified", R.OK
    if probe := _probe_reason(control, exploit):
        return "not_verified", probe
    if control is Outcome.ASSERTION_FAILED:
        return "not_verified", R.CONTROL_FAILED
    return "not_verified", R.NO_VALID_OBSERVATION  # the exploit still fails on the fixed revision


def _origins(f: Facts) -> dict[str, Origin]:
    """Where each fact the verdict rests on came from (A5)."""
    origins: dict[str, Origin] = {}
    if f.stopped is not None:
        origins["stopped"] = Origin.PLATFORM_OBSERVED
    if f.fix_stopped is not None:
        origins["fix_stopped"] = Origin.PLATFORM_OBSERVED
    if f.runtime is not None:
        origins["runtime"] = Origin.DECLARED  # operator-owned matrix row
    if f.build is not None:
        origins["build"] = Origin.PLATFORM_OBSERVED  # trusted replay of the recipe
    if f.plan is not None:
        origins["plan"] = Origin.DECLARED  # the Investigator's claim, checked only for citations
    for revision, validity in f.validity.items():
        origins[f"{revision}.validity"] = Origin.MODEL_REVIEWED
    for (revision, role) in f.runs:
        origins[f"{revision}.{role}.exit_class"] = Origin.NATIVE_TEST_REPORTED
        origins[f"{revision}.{role}.markers"] = Origin.PLATFORM_OBSERVED
        origins[f"{revision}.{role}.token"] = Origin.PLATFORM_OBSERVED
        origins[f"{revision}.{role}.check"] = Origin.PLATFORM_OBSERVED
    return origins


def _gather(case: Case, runtime: Runtime | None, build: BuildResult | None, plan: ProbePlan | None,
            validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...], stopped: str | None,
            fix_stopped: str | None) -> Facts:
    by_key: dict[tuple[str, str], ProbeRun] = {}
    for run in runs:
        key = (run.revision, run.role)
        if key in by_key:
            raise ValueError(f"more than one {run.role} run on the {run.revision} revision; a probe runs exactly once")
        by_key[key] = run
    reviews: dict[str, Validity] = {}
    for item in validity:
        if item.revision in reviews:
            raise ValueError(f"more than one review of the {item.revision} revision")
        reviews[item.revision] = item
    vulnerable = [run.patch_sha256 for run in runs if run.revision == "vulnerable"]
    patch = vulnerable[0] if vulnerable else (reviews["vulnerable"].patch_sha256 if "vulnerable" in reviews else None)
    # A run bound to another patch than the vulnerable one is not this experiment's evidence.
    by_key = {key: run for key, run in by_key.items() if run.patch_sha256 == patch}
    return Facts(case, runtime, build, plan, TerminalReason(stopped) if stopped is not None else None,
                 TerminalReason(fix_stopped) if fix_stopped is not None else None, by_key, reviews, patch)


def decide(case: Case, *, runtime: Runtime | None, build: BuildResult | None, plan: ProbePlan | None,
           validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...], stopped: str | None = None,
           fix_stopped: str | None = None) -> Verdict:
    """The label, rule id, terminal reason, finding and fix verification for one case, from recorded facts only.

    ``stopped`` is the terminal reason a stage reported when the chain stopped early (a ``TerminalReason`` value);
    ``fix_stopped`` is the reason the fixed-revision steps stopped, which only affects the fix result. An unknown
    string raises ValueError. Duplicate runs for one (revision, role), or two reviews of one revision,
    raise ValueError: the chain runs each probe exactly once.
    """
    facts = _gather(case, runtime, build, plan, validity, runs, stopped, fix_stopped)
    for rule in RULES:
        reason = rule.match(facts)
        if reason is not None:
            break
    else:  # pragma: no cover - R6 always matches
        raise AssertionError("the rule table has no catch-all")
    fix, fix_reason = _fix(facts, rule, reason)
    return Verdict(case_id=case.case_id, label=rule.label, rule_id=rule.id, terminal_reason=reason,
                   finding=rule.finding, fix=fix, fix_reason=fix_reason, runs=tuple(runs), validity=tuple(validity),
                   facts_origin=_origins(facts))
