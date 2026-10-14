"""The Decide rule table: one table-driven case per rule and terminal reason, then fix verification and origins.

The exploit probe is a proof-of-vulnerability test (SPEC-0082 D12): ``passed`` on the vulnerable revision means the
reported condition was demonstrated."""
import pytest

from corsair.v2.contracts import (BuildResult, Case, Citation, ExitClass, Finding, Label, Origin, Outcome, ProbeBrief,
                                  ProbeFacts, ProbePlan, ProbeRun, ProbeValidity, Recipe, Revision, Runtime,
                                  TerminalReason as T, Validity)
from corsair.v2.rules import RULES, decide

PATCH, OTHER = "a" * 64, "b" * 64
REV = Revision(source="/tmp/rev", tree_sha256="c" * 64)
CASE = Case(case_id="case-1", finding=Finding(title="t"), revision=REV)
FIXED_CASE = Case(case_id="case-1", finding=Finding(title="t"), revision=REV,
                  fixed_revision=Revision(source="/tmp/fix", tree_sha256="d" * 64))
RUNTIME = Runtime(row_id="r", image="img", framework="f", skill="f", run_template=("run",),
                  exit_codes={0: ExitClass.PASS}, evidence="image-only")
BUILD_OK = BuildResult(recipe=Recipe(baseline_test=("t",)), replayed=True, baseline_exit_code=0)
BUILD_FAILED = BuildResult(recipe=None, replayed=False, reason="no recipe")
CITE = (Citation(path="app.py", start_line=1, end_line=1),)


def brief(role):
    return ProbeBrief(role=role, test_file="tests/test_x.py", test_name="test_x", target="t", seam="s",
                      input_description="i", property_to_assert="p", citations=CITE)


PLAN = ProbePlan(status="planned", target="t", control=brief("control"), exploit=brief("exploit"))


def pv(role, valid=True):
    return ProbeValidity(role=role, valid=valid, calls_real_target=valid, exercises_condition=valid,
                         assertion_relevant=valid, doubles_only_dependencies=valid)


def review(revision="vulnerable", control=True, exploit=True, patch=PATCH):
    return Validity(patch_sha256=patch, revision=revision, control=pv("control", control),
                    exploit=pv("exploit", exploit))


def run(role, outcome, revision="vulnerable", patch=PATCH):
    facts = ProbeFacts(exit_code=0, exit_class=ExitClass.PASS, start_marker=True, end_marker=True,
                       token_in_output=False)
    return ProbeRun(role=role, revision=revision, patch_sha256=patch, facts=facts, outcome=Outcome(outcome))


def runs(control="passed", exploit="passed", revision="vulnerable", patch=PATCH):
    return tuple(r for r in (control and run("control", control, revision, patch),
                             exploit and run("exploit", exploit, revision, patch)) if r)


def full(**overrides):
    kwargs = dict(runtime=RUNTIME, build=BUILD_OK, plan=PLAN, validity=(review(),), runs=runs(), stopped=None)
    kwargs.update(overrides)
    return kwargs


UNSUPPORTED = ProbePlan(status="unsupported_scope", reason="needs a real database")
NOT_FOUND = ProbePlan(status="target_not_found")

# id, decide kwargs, expected (rule, label, terminal reason, finding)
CASES = [
    ("no runtime", full(runtime=None, build=None, plan=None, validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.NO_RUNTIME, "none")),
    ("stopped no_runtime", full(stopped="no_runtime", validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.NO_RUNTIME, "none")),
    ("build failed", full(build=BUILD_FAILED, validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.BUILD_FAILED, "none")),
    ("plan unsupported", full(plan=UNSUPPORTED, build=None, validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.UNSUPPORTED_SCOPE, "none")),
    ("plan target not found", full(plan=NOT_FOUND, build=None, validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.TARGET_NOT_FOUND, "none")),
    ("plan unresolved", full(plan=ProbePlan(status="unresolved"), build=None, validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.PLAN_UNRESOLVED, "none")),
    ("stopped plan_unresolved", full(stopped="plan_unresolved", validity=(), runs=()),
     ("R0", Label.UNABLE_TO_RUN, T.PLAN_UNRESOLVED, "none")),
    ("provider error", full(stopped="provider_error", validity=(), runs=()),
     ("R1", Label.ERROR, T.PROVIDER_ERROR, "none")),
    ("infra error", full(stopped="infra_error"), ("R1", Label.ERROR, T.INFRA_ERROR, "none")),
    ("cleanup unconfirmed", full(stopped="cleanup_unconfirmed"), ("R1", Label.ERROR, T.CLEANUP_UNCONFIRMED, "none")),
    ("infra run", full(runs=runs(exploit="infra")), ("R1", Label.ERROR, T.INFRA_ERROR, "none")),
    ("infra control run", full(runs=runs(control="infra")), ("R1", Label.ERROR, T.INFRA_ERROR, "none")),
    ("budget exhausted", full(stopped="budget_exhausted", validity=(), runs=()),
     ("R7", Label.INCONCLUSIVE, T.BUDGET_EXHAUSTED, "inconclusive")),
    ("review missing", full(validity=()), ("R2", Label.INCONCLUSIVE, T.TEST_INVALID, "inconclusive")),
    ("control invalid", full(validity=(review(control=False),)),
     ("R2", Label.INCONCLUSIVE, T.TEST_INVALID, "inconclusive")),
    ("exploit invalid", full(validity=(review(exploit=False),)),
     ("R2", Label.INCONCLUSIVE, T.TEST_INVALID, "inconclusive")),
    ("review of another patch", full(validity=(review(patch=OTHER),)),
     ("R2", Label.INCONCLUSIVE, T.TEST_INVALID, "inconclusive")),
    ("only fixed review", full(validity=(review("fixed"),)),
     ("R2", Label.INCONCLUSIVE, T.TEST_INVALID, "inconclusive")),
    ("control assertion failed", full(runs=runs(control="assertion_failed")),
     ("R3", Label.INCONCLUSIVE, T.CONTROL_FAILED, "inconclusive")),
    ("control anomalous", full(runs=runs(control="anomalous")),
     ("R3", Label.INCONCLUSIVE, T.PROBE_ANOMALOUS, "inconclusive")),
    ("control not run", full(runs=runs(control="not_run")),
     ("R3", Label.INCONCLUSIVE, T.PROBE_NOT_RUN, "inconclusive")),
    ("control errored", full(runs=runs(control="errored")),
     ("R3", Label.INCONCLUSIVE, T.PROBE_ERRORED, "inconclusive")),
    ("control missing", full(runs=runs(control=None)),
     ("R3", Label.INCONCLUSIVE, T.PROBE_NOT_RUN, "inconclusive")),
    ("reproduced", full(), ("R4", Label.LIKELY_EXPLOITABLE, T.OK, "reproduced")),
    ("not reproduced", full(runs=runs(exploit="assertion_failed")),
     ("R5", Label.LIKELY_NOT_EXPLOITABLE, T.OK, "not_reproduced")),
    ("PoV passed on both revisions", full(runs=runs() + runs(control="passed", exploit="passed", revision="fixed")),
     ("R6", Label.INCONCLUSIVE, T.NOT_DIFFERENTIAL, "inconclusive")),
    ("PoV passed on the fix with a failing fixed control",
     full(runs=runs() + runs(control="assertion_failed", exploit="passed", revision="fixed")),
     ("R6", Label.INCONCLUSIVE, T.NOT_DIFFERENTIAL, "inconclusive")),
    ("fixed PoV errored keeps the label", full(runs=runs() + runs(exploit="errored", revision="fixed")),
     ("R4", Label.LIKELY_EXPLOITABLE, T.OK, "reproduced")),
    ("fixed PoV on another patch never reaches the label",
     full(runs=runs() + runs(exploit="passed", revision="fixed", patch=OTHER)),
     ("R4", Label.LIKELY_EXPLOITABLE, T.OK, "reproduced")),
    ("exploit anomalous", full(runs=runs(exploit="anomalous")),
     ("R6", Label.INCONCLUSIVE, T.PROBE_ANOMALOUS, "inconclusive")),
    ("exploit not run", full(runs=runs(exploit="not_run")),
     ("R6", Label.INCONCLUSIVE, T.PROBE_NOT_RUN, "inconclusive")),
    ("exploit errored", full(runs=runs(exploit="errored")),
     ("R6", Label.INCONCLUSIVE, T.PROBE_ERRORED, "inconclusive")),
    ("exploit missing", full(runs=runs(exploit=None)),
     ("R6", Label.INCONCLUSIVE, T.PROBE_NOT_RUN, "inconclusive")),
    ("exploit run on another patch", full(runs=(run("control", "passed"), run("exploit", "passed", patch=OTHER))),
     ("R6", Label.INCONCLUSIVE, T.PROBE_NOT_RUN, "inconclusive")),
    ("other stop falls through to evidence", full(stopped="probe_errored", runs=runs(exploit="errored")),
     ("R6", Label.INCONCLUSIVE, T.PROBE_ERRORED, "inconclusive")),
    ("R0 outranks R1", full(runtime=None, stopped="provider_error"),
     ("R0", Label.UNABLE_TO_RUN, T.NO_RUNTIME, "none")),
    ("R1 outranks a decisive run", full(stopped="infra_error"), ("R1", Label.ERROR, T.INFRA_ERROR, "none")),
    ("fix stop never reaches the label", full(fix_stopped="infra_error"),
     ("R4", Label.LIKELY_EXPLOITABLE, T.OK, "reproduced")),
    ("fixed infra run never reaches the label",
     full(runs=runs() + runs(control="infra", exploit="assertion_failed", revision="fixed")),
     ("R4", Label.LIKELY_EXPLOITABLE, T.OK, "reproduced")),
]


@pytest.mark.parametrize(("kwargs", "expected"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_rule_table(kwargs, expected):
    verdict = decide(CASE, **kwargs)
    assert (verdict.rule_id, verdict.label, verdict.terminal_reason, verdict.finding) == expected
    assert (verdict.fix, verdict.fix_reason) == ("not_applicable", None)
    assert verdict.case_id == "case-1"


def test_every_rule_is_covered_and_ids_are_unique():
    ids = [rule.id for rule in RULES]
    assert len(ids) == len(set(ids)) and ids[-1] == "R6"
    assert {c[2][0] for c in CASES} == set(ids)


def fixed(**changes):
    kwargs = full()
    kwargs["validity"] = (review(), review("fixed"))
    kwargs["runs"] = runs() + runs(exploit="assertion_failed", revision="fixed")
    kwargs.update(changes)
    return kwargs


FIX_CASES = [
    ("verified", fixed(), "verified", T.OK),
    ("no fixed review", fixed(validity=(review(),)), "not_verified", T.TEST_INVALID),
    ("fixed review negative", fixed(validity=(review(), review("fixed", exploit=False))), "not_verified",
     T.TEST_INVALID),
    ("fixed review other patch", fixed(validity=(review(), review("fixed", patch=OTHER))), "not_verified",
     T.TEST_INVALID),
    ("PoV still passes on the fix", fixed(runs=runs() + runs(exploit="passed", revision="fixed")), "not_verified",
     T.NOT_DIFFERENTIAL),
    ("fixed control errored", fixed(runs=runs() + runs(control="errored", exploit="assertion_failed",
                                                         revision="fixed")), "not_verified", T.PROBE_ERRORED),
    ("fixed control assertion failed", fixed(runs=runs() + runs(control="assertion_failed", exploit="assertion_failed",
                                                                revision="fixed")), "not_verified", T.CONTROL_FAILED),
    ("fixed exploit anomalous", fixed(runs=runs() + runs(exploit="anomalous", revision="fixed")), "not_verified",
     T.PROBE_ANOMALOUS),
    ("not_run outranks errored and anomalous", fixed(runs=runs() + runs(control="anomalous", exploit="not_run",
                                                                         revision="fixed")),
     "not_verified", T.PROBE_NOT_RUN),
    ("errored outranks anomalous", fixed(runs=runs() + runs(control="anomalous", exploit="errored",
                                                             revision="fixed")), "not_verified", T.PROBE_ERRORED),
    ("fixed runs missing", fixed(runs=runs()), "not_verified", T.PROBE_NOT_RUN),
    ("fixed runs other patch", fixed(runs=runs() + runs(exploit="assertion_failed", revision="fixed", patch=OTHER)),
     "not_verified", T.PROBE_NOT_RUN),
    ("fixed infra run", fixed(runs=runs() + runs(control="infra", exploit="assertion_failed", revision="fixed")),
     "not_verified", T.INFRA_ERROR),
    ("fixed revision stopped", fixed(runs=runs(), fix_stopped="provider_error"), "not_verified",
     T.PROVIDER_ERROR),
    ("fixed replay failed", fixed(runs=runs(), fix_stopped="build_failed"), "not_verified", T.BUILD_FAILED),
    ("not reproduced first", fixed(runs=runs(exploit="assertion_failed") + runs(exploit="assertion_failed",
                                                                                revision="fixed")),
     "not_verified", T.NO_VALID_OBSERVATION),
    ("vulnerable exploit errored", fixed(runs=runs(exploit="errored") + runs(exploit="assertion_failed",
                                                                            revision="fixed")),
     "not_verified", T.PROBE_ERRORED),
    ("fixed provider error with a decisive vulnerable PoV", fixed(runs=runs(), fix_stopped="provider_error"),
     "not_verified", T.PROVIDER_ERROR),
]


@pytest.mark.parametrize(("kwargs", "fix", "reason"), [c[1:] for c in FIX_CASES], ids=[c[0] for c in FIX_CASES])
def test_fix_verification(kwargs, fix, reason):
    verdict = decide(FIXED_CASE, **kwargs)
    assert (verdict.fix, verdict.fix_reason) == (fix, reason)


def test_fix_not_applicable_without_fixed_revision():
    verdict = decide(CASE, **fixed())
    assert (verdict.fix, verdict.fix_reason) == ("not_applicable", None)


def test_infra_on_the_fixed_revision_keeps_a_reproduced_finding():
    verdict = decide(FIXED_CASE, **fixed(runs=runs() + runs(exploit="infra", revision="fixed")))
    assert (verdict.rule_id, verdict.label, verdict.finding) == ("R4", Label.LIKELY_EXPLOITABLE, "reproduced")
    assert (verdict.fix, verdict.fix_reason) == ("not_verified", T.INFRA_ERROR)
    verdict = decide(FIXED_CASE, **fixed(runs=runs(), fix_stopped="infra_error"))
    assert (verdict.label, verdict.fix, verdict.fix_reason) == (Label.LIKELY_EXPLOITABLE, "not_verified",
                                                                T.INFRA_ERROR)


def test_a_run_on_another_tree_than_its_revision_counts_as_missing():
    # The exploit PoV passed, but on an environment built from another tree than the case's vulnerable revision.
    elsewhere = run("exploit", "passed").model_copy(update={"tree_sha256": "e" * 64})
    here = run("control", "passed").model_copy(update={"tree_sha256": REV.tree_sha256})
    verdict = decide(CASE, **full(runs=(here, elsewhere)))
    assert (verdict.rule_id, verdict.label, verdict.terminal_reason) == ("R6", Label.INCONCLUSIVE, T.PROBE_NOT_RUN)
    bound = decide(CASE, **full(runs=(here, elsewhere.model_copy(update={"tree_sha256": REV.tree_sha256}))))
    assert (bound.rule_id, bound.label) == ("R4", Label.LIKELY_EXPLOITABLE)


def test_duplicate_runs_and_reviews_are_refused():
    with pytest.raises(ValueError):
        decide(CASE, **full(runs=runs() + (run("exploit", "assertion_failed"),)))
    with pytest.raises(ValueError):
        decide(CASE, **full(validity=(review(), review())))
    with pytest.raises(ValueError):
        decide(CASE, **full(stopped="not_a_reason"))
    with pytest.raises(ValueError):
        decide(CASE, **full(fix_stopped="not_a_reason"))


def test_facts_origin_and_evidence_kept():
    verdict = decide(FIXED_CASE, **fixed())
    assert verdict.facts_origin["runtime"] is Origin.DECLARED
    assert verdict.facts_origin["build"] is Origin.PLATFORM_OBSERVED
    assert verdict.facts_origin["vulnerable.validity"] is Origin.MODEL_REVIEWED
    assert verdict.facts_origin["vulnerable.exploit.exit_class"] is Origin.NATIVE_TEST_REPORTED
    assert verdict.facts_origin["fixed.control.markers"] is Origin.PLATFORM_OBSERVED
    assert verdict.facts_origin["fixed.exploit.check"] is Origin.PLATFORM_OBSERVED
    assert len(verdict.runs) == 4 and len(verdict.validity) == 2


@pytest.mark.parametrize("role", ["control", "exploit"])
def test_a_vulnerable_harness_error_before_start_is_inconclusive_not_error(role):
    """A collection or import error of the probe file (pytest exits 2, which the row maps to harness_error) never
    started the body: it is the author's not_run, so the case is INCONCLUSIVE probe_not_run, never ERROR."""
    from corsair.v2.outcome import classify
    facts = ProbeFacts(exit_code=2, exit_class=ExitClass.HARNESS_ERROR, start_marker=False, end_marker=False,
                       token_in_output=False)
    broken = ProbeRun(role=role, revision="vulnerable", patch_sha256=PATCH, facts=facts, outcome=classify(facts))
    assert broken.outcome is Outcome.NOT_RUN
    other = run("exploit" if role == "control" else "control", "passed")
    verdict = decide(CASE, **full(runs=tuple(sorted((broken, other), key=lambda r: r.role))))
    assert (verdict.label, verdict.terminal_reason) == (Label.INCONCLUSIVE, T.PROBE_NOT_RUN)
    assert verdict.rule_id == ("R3" if role == "control" else "R6")
    # With the start marker the harness failed around a running body: still infrastructure, still ERROR.
    started = facts.model_copy(update={"start_marker": True})
    infra = broken.model_copy(update={"facts": started, "outcome": classify(started)})
    verdict = decide(CASE, **full(runs=tuple(sorted((infra, other), key=lambda r: r.role))))
    assert (verdict.label, verdict.rule_id, verdict.terminal_reason) == (Label.ERROR, "R1", T.INFRA_ERROR)
