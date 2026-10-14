"""The Decide stage: a fixed rule table over recorded facts (redesign section 5, amended by section 13; D4).

No model runs here. Rules are data, evaluated top to bottom; the first whose condition matches fixes the label,
the finding and the terminal reason, and its id is stored on the Verdict so a report can cite it. A rule may
refine its terminal reason from the facts (for example R3 names ``probe_not_run`` when the control never
started) but never its label.

Choices the design left open, recorded here:

- ``budget_exhausted`` is a stop, not a fault of the platform or the provider, and says nothing about the
  finding, so it is INCONCLUSIVE, not ERROR. It has its own rule, R7, evaluated right after R1 so that a budget
  stop is never misreported as ``test_invalid`` because the review never ran.
- R1 also fires when a vulnerable-revision run is ``infra``: an uncertain execution is never a decisive one.
- ``cleanup_unconfirmed`` from the chain is an infrastructure fault (R1).
- A ``stopped`` reason that none of R0, R1 and R7 owns (for example ``probe_not_run`` after the single D3
  correction) is not a label by itself: the evidence rules below still read the recorded runs.
- R6 names ``probe_not_run`` or ``probe_errored`` when the exploit run shows it, else ``no_valid_observation``.
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


def _not_started(outcome: Outcome | None) -> TerminalReason | None:
    if outcome is None or outcome is Outcome.NOT_RUN:
        return R.PROBE_NOT_RUN
    if outcome is Outcome.ERRORED:
        return R.PROBE_ERRORED
    return None


def _r3(f: Facts) -> TerminalReason | None:
    outcome = f.outcome("vulnerable", "control")
    if outcome is Outcome.PASSED:
        return None
    return _not_started(outcome) or R.CONTROL_FAILED


def _r4(f: Facts) -> TerminalReason | None:
    return R.OK if f.outcome("vulnerable", "exploit") is Outcome.ASSERTION_FAILED else None


def _r5(f: Facts) -> TerminalReason | None:
    return R.OK if f.outcome("vulnerable", "exploit") is Outcome.PASSED else None


def _r6(f: Facts) -> TerminalReason | None:
    return _not_started(f.outcome("vulnerable", "exploit")) or R.NO_VALID_OBSERVATION


RULES: tuple[Rule, ...] = (
    Rule("R0", "Stopped before evidence: no matrix row, build failed, plan unsupported_scope or target_not_found",
         Label.UNABLE_TO_RUN, "none", _r0),
    Rule("R1", "Provider or infrastructure failure, including an infra run on the vulnerable revision",
         Label.ERROR, "none", _r1),
    Rule("R7", "Budget exhausted before a decisive observation", Label.INCONCLUSIVE, "inconclusive", _r7),
    Rule("R2", "Review missing, bound to another patch, or negative for either probe on the vulnerable revision",
         Label.INCONCLUSIVE, "inconclusive", _r2),
    Rule("R3", "Vulnerable control not passed", Label.INCONCLUSIVE, "inconclusive", _r3),
    Rule("R4", "Vulnerable exploit assertion_failed", Label.LIKELY_EXPLOITABLE, "reproduced", _r4),
    Rule("R5", "Vulnerable exploit passed", Label.LIKELY_NOT_EXPLOITABLE, "not_reproduced", _r5),
    Rule("R6", "Anything else", Label.INCONCLUSIVE, "inconclusive", _r6),
)
"""Evaluation order is the tuple order; ids name rules, not ranks (R7 is checked after R1)."""

FIX_RULE = ("verified: R4 on the vulnerable revision, control and exploit passed on the fixed revision, a positive "
            "review of the fixed revision, and one frozen patch throughout; not_applicable without a fixed revision; "
            "otherwise not_verified")


def _fix(f: Facts, rule: Rule) -> Literal["verified", "not_verified", "not_applicable"]:
    if f.case.fixed_revision is None:
        return "not_applicable"
    validity = f.bound_validity("fixed")
    verified = (rule.id == "R4"
                and f.patch_sha256 is not None
                and f.outcome("fixed", "control") is Outcome.PASSED
                and f.outcome("fixed", "exploit") is Outcome.PASSED
                and validity is not None and validity.control.valid and validity.exploit.valid)
    return "verified" if verified else "not_verified"


def _origins(f: Facts) -> dict[str, Origin]:
    """Where each fact the verdict rests on came from (A5)."""
    origins: dict[str, Origin] = {}
    if f.stopped is not None:
        origins["stopped"] = Origin.PLATFORM_OBSERVED
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
    return origins


def _gather(case: Case, runtime: Runtime | None, build: BuildResult | None, plan: ProbePlan | None,
            validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...], stopped: str | None) -> Facts:
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
    return Facts(case, runtime, build, plan, TerminalReason(stopped) if stopped is not None else None, by_key,
                 reviews, patch)


def decide(case: Case, *, runtime: Runtime | None, build: BuildResult | None, plan: ProbePlan | None,
           validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...], stopped: str | None = None) -> Verdict:
    """The label, rule id, terminal reason, finding and fix verification for one case, from recorded facts only.

    ``stopped`` is the terminal reason a stage reported when the chain stopped early (a ``TerminalReason`` value);
    an unknown string raises ValueError. Duplicate runs for one (revision, role), or two reviews of one revision,
    raise ValueError: the chain runs each probe exactly once.
    """
    facts = _gather(case, runtime, build, plan, validity, runs, stopped)
    for rule in RULES:
        reason = rule.match(facts)
        if reason is not None:
            break
    else:  # pragma: no cover - R6 always matches
        raise AssertionError("the rule table has no catch-all")
    return Verdict(case_id=case.case_id, label=rule.label, rule_id=rule.id, terminal_reason=reason,
                   finding=rule.finding, fix=_fix(facts, rule), runs=tuple(runs), validity=tuple(validity),
                   facts_origin=_origins(facts))
