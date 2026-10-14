"""Chain routing with fake stages: order, early stops, A2/D3 correction bounds and review blindness."""
import asyncio
import json

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

from chain_fakes import PLAN, RECIPE, Fakes, case, draft, models
from corsair.v2.chain import MAX_REVIEWS, Budget, draft_digest, freeze, review_feedback, run_case
from corsair.v2.contracts import FrozenPatch, ProbePlan, ProbeRun
from corsair.v2.record import RunRecorder


def go(fakes: Fakes, tmp_path, *, fixed=False, budget=Budget()):
    record = RunRecorder.create(tmp_path / "runs", "run")
    verdict = asyncio.run(run_case(case(tmp_path, fixed), stages=fakes.stages(), models=models(),
                                   matrix_path=tmp_path / "matrix.yaml", record=record, budget=budget))
    return verdict, fakes.of("decide")[0][1]


def test_full_chain_runs_stages_in_order(tmp_path):
    fakes = Fakes()
    verdict, decided = go(fakes, tmp_path)
    assert fakes.names() == ["select", "investigate", "workspace-open", "build", "workspace-close", "replay",
                             "probe-control", "probe-exploit", "diagnose", "diagnose", "review", "execute",
                             "execute", "decide"]
    assert decided["stopped"] is None
    assert [(r.role, r.revision) for r in decided["runs"]] == [("control", "vulnerable"), ("exploit", "vulnerable")]
    assert verdict.rule_id == "R4"


def test_fixed_revision_is_reviewed_replayed_and_executed(tmp_path):
    fakes = Fakes()
    go(fakes, tmp_path, fixed=True)
    assert [kw["revision"] for _, kw in fakes.of("review")] == ["vulnerable", "fixed"]
    assert [kw["revision"] for _, kw in fakes.of("replay")] == ["vulnerable", "fixed"]
    # The Reviewer gets the run's runtime (its framework skill) on both revisions, as the Probers do.
    probe_runtime = fakes.of("probe-control")[0][0][1]
    assert [kw["runtime"] for _, kw in fakes.of("review")] == [probe_runtime, probe_runtime]
    assert [(a[3], kw["revision"]) for a, kw in fakes.of("execute")] == [
        ("control", "vulnerable"), ("exploit", "vulnerable"), ("control", "fixed"), ("exploit", "fixed")]
    # Review of both revisions comes before any execution.
    names = fakes.names()
    assert max(i for i, n in enumerate(names) if n == "review") < names.index("execute")


@pytest.mark.parametrize("setup, reason, last", [
    (dict(runtime=None), "no_runtime", "select"),
    (dict(plan=None), "plan_unresolved", "investigate"),
    (dict(plan=ProbePlan(status="target_not_found", reason="x")), "target_not_found", "investigate"),
    (dict(plan=ProbePlan(status="unresolved", reason="x")), "plan_unresolved", "investigate"),
    (dict(plan=ProbePlan(status="unsupported_scope", reason="x")), "unsupported_scope", "investigate"),
    (dict(plan=PLAN.model_copy(update={"exploit": None})), "plan_unresolved", "investigate"),
    (dict(raises={"investigate": ModelHTTPError(503, "m")}), "provider_error", "investigate"),
    (dict(raises={"investigate": UsageLimitExceeded("limit")}), "budget_exhausted", "investigate"),
    (dict(raises={"build": RuntimeError("docker gone")}), "infra_error", "build"),
    (dict(raises={"replay": OSError("daemon")}), "infra_error", "replay"),
    (dict(raises={"select": ValueError("bad matrix")}), "infra_error", "select"),
    (dict(raises={"probe-exploit": ModelHTTPError(500, "m")}), "provider_error", "probe-exploit"),
    (dict(raises={"diagnose": OSError("x")}), "infra_error", "diagnose"),
    (dict(raises={"review": ModelHTTPError(500, "m")}), "provider_error", "review"),
    (dict(raises={"execute": OSError("x")}), "infra_error", "execute"),
])
def test_early_stops_pass_their_terminal_reason_to_decide(tmp_path, setup, reason, last):
    fakes = Fakes(**setup)
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] == reason
    names = [n for n in fakes.names() if not n.startswith("workspace")]
    assert names[-2:] == [last, "decide"]


def test_agent_reporting_provider_error_without_output_stops(tmp_path):
    from chain_fakes import usage
    fakes = Fakes(plan=None, usages={"investigator": usage("investigator", status="provider_error")})
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] == "provider_error"


def test_one_more_builder_episode_with_the_failure_tail(tmp_path):
    fakes = Fakes(recipes=[RECIPE, RECIPE], replays=[False, True])
    _, decided = go(fakes, tmp_path)
    builds = fakes.of("build")
    assert len(builds) == 2
    assert builds[0][1]["feedback"] is None
    assert "baseline test failed: missing module" in builds[1][1]["feedback"]
    assert decided["stopped"] is None


def test_build_fails_after_at_most_two_episodes(tmp_path):
    fakes = Fakes(recipes=[RECIPE, RECIPE, RECIPE], replays=[False, False, False])
    _, decided = go(fakes, tmp_path)
    assert len(fakes.of("build")) == 2 and len(fakes.of("replay")) == 2
    assert decided["stopped"] == "build_failed"
    assert decided["build"].replayed is False


def test_no_recipe_twice_is_build_failed_without_replay(tmp_path):
    fakes = Fakes(recipes=[None, None])
    _, decided = go(fakes, tmp_path)
    assert len(fakes.of("build")) == 2 and fakes.of("replay") == []
    assert decided["stopped"] == "build_failed"


def test_one_budget_across_corrections(tmp_path):
    # Calls: investigate, build, build-retry; the budget of 3 stops before the first probe.
    fakes = Fakes(recipes=[RECIPE, RECIPE], replays=[False, True])
    _, decided = go(fakes, tmp_path, budget=Budget(max_agent_calls=3))
    assert decided["stopped"] == "budget_exhausted"
    assert fakes.of("probe-control") == []
    # Requests are summed across stages: 2 known requests exhaust a request budget of 2 before the build retry.
    fakes = Fakes(recipes=[RECIPE, RECIPE], replays=[False, True])
    _, decided = go(fakes, tmp_path / "b", budget=Budget(max_requests=2))
    assert decided["stopped"] == "budget_exhausted" and len(fakes.of("build")) == 1


@pytest.mark.parametrize("outcome", ["not_run", "errored"])
def test_d3_gives_a_failed_author_a_correction_with_its_check_result(tmp_path, outcome):
    fakes = Fakes(diagnose_outcomes={"control": [outcome]})
    _, decided = go(fakes, tmp_path)
    controls, exploits = fakes.of("probe-control"), fakes.of("probe-exploit")
    assert len(controls) == 2 and len(exploits) == 1
    assert controls[0][1]["diagnostics"] is None
    assert controls[1][1]["diagnostics"] == f"check: {outcome}\nhint: control hint"
    assert controls[1][1]["previous"] == draft("control")
    assert len(fakes.of("diagnose")) == 3  # the correction is checked again, and reads ok
    reviewed: FrozenPatch = fakes.of("review")[0][0][2]
    assert "revised" in reviewed.control.source
    assert reviewed.control.revision_of == draft_digest(draft("control"))
    assert reviewed == freeze(reviewed.control, draft("exploit"))
    assert all(a[2].sha256 == reviewed.sha256 for a, _ in fakes.of("execute"))
    # The check run precedes review, and review precedes the counted execution.
    names = fakes.names()
    assert names.index("probe-control", names.index("diagnose")) < names.index("review") < names.index("execute")


def test_d3_ok_gets_no_revision_and_the_frozen_patch_is_reviewed_and_executed(tmp_path):
    fakes = Fakes(diagnose_outcomes={"control": "ok", "exploit": "ok"})
    go(fakes, tmp_path)
    assert len(fakes.of("probe-control")) == 1 and len(fakes.of("probe-exploit")) == 1
    patch = freeze(draft("control"), draft("exploit"))
    assert [a[2] for a, _ in fakes.of("diagnose")] == [patch.control, patch.exploit]
    assert fakes.of("review")[0][0][2] == patch
    assert all(a[2] == patch for a, _ in fakes.of("execute"))


def test_d3_both_authors_correct_and_a_failed_correction_keeps_the_original(tmp_path):
    fakes = Fakes(diagnose_outcomes={"control": "errored", "exploit": ["not_run"]},
                  revised={"control": None})
    go(fakes, tmp_path)
    assert len(fakes.of("probe-control")) == 2 and len(fakes.of("probe-exploit")) == 2
    reviewed = fakes.of("review")[0][0][2]
    assert reviewed.control == draft("control") and "revised" in reviewed.exploit.source


def test_missing_initial_draft_stops_as_probe_not_run(tmp_path):
    fakes = Fakes()
    original = fakes.exploit_probe

    async def none(*args, **kwargs):
        _, usage = await original(*args, **kwargs)
        return None, usage
    fakes.exploit_probe = none
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] == "probe_not_run"


def _contains_run(value) -> bool:
    if isinstance(value, ProbeRun):
        return True
    if isinstance(value, (list, tuple)):
        return any(_contains_run(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_run(v) for v in value.values())
    if hasattr(value, "model_dump"):
        return any(_contains_run(getattr(value, f)) for f in type(value).model_fields)
    return False


def test_reviewer_and_probers_never_see_runs_or_each_other(tmp_path):
    fakes = Fakes(diagnose_outcomes={"exploit": "errored"})
    go(fakes, tmp_path, fixed=True)
    for name in ("review", "probe-control", "probe-exploit"):
        for args, kwargs in fakes.of(name):
            assert not _contains_run(args) and not _contains_run(kwargs)
    assert all(a[0].role == "control" for a, _ in fakes.of("probe-control"))
    assert all(a[0].role == "exploit" for a, _ in fakes.of("probe-exploit"))
    assert all(kw["previous"] is None or kw["previous"].role == "exploit" for _, kw in fakes.of("probe-exploit"))


def test_grounding_runs_first_only_when_configured_and_is_never_passed_on(tmp_path):
    fakes = Fakes()
    go(fakes, tmp_path)
    assert "ground" not in fakes.names()
    fakes = Fakes(grounding=True)
    go(fakes, tmp_path / "g")
    assert fakes.names()[0] == "ground"
    assert (tmp_path / "g" / "runs" / "run" / "grounding.json").exists()
    # A failed grounding call is advisory: the run continues.
    fakes = Fakes(grounding=True, raises={"ground": ModelHTTPError(500, "m")})
    _, decided = go(fakes, tmp_path / "h")
    assert decided["stopped"] is None
    # ...and it still says why there is no brief, so a failure never reads as "no precedent".
    recorded = json.loads((tmp_path / "h" / "runs" / "run" / "grounding.json").read_text())
    assert recorded["brief"] is None and recorded["status"] == "provider_error"


def test_missing_model_is_an_explicit_error(tmp_path):
    record = RunRecorder.create(tmp_path, "r")
    with pytest.raises(ValueError, match="reviewer"):
        asyncio.run(run_case(case(tmp_path), stages=Fakes().stages(),
                             models={k: v for k, v in models().items() if k != "reviewer"},
                             matrix_path=tmp_path, record=record))


@pytest.mark.parametrize("setup, reason", [
    (dict(fixed_raises={"review": ModelHTTPError(500, "m")}), "provider_error"),
    (dict(fixed_raises={"execute": OSError("daemon")}), "infra_error"),
    (dict(raises={"replay-fixed": OSError("daemon")}), "infra_error"),
    (dict(fixed_replays=False), "build_failed"),
])
def test_fixed_revision_failures_never_stop_the_run(tmp_path, setup, reason):
    fakes = Fakes(**setup)
    _, decided = go(fakes, tmp_path, fixed=True)
    assert decided["stopped"] is None and decided["fix_stopped"] == reason
    assert [(r.role, r.revision) for r in decided["runs"]][:2] == [("control", "vulnerable"),
                                                                   ("exploit", "vulnerable")]


def test_budget_exhausted_at_the_fixed_review_still_executes_the_vulnerable_revision(tmp_path):
    # Calls: investigate, build, two probes, the vulnerable review; the fixed review is over budget.
    fakes = Fakes()
    _, decided = go(fakes, tmp_path, fixed=True, budget=Budget(max_agent_calls=5))
    assert decided["stopped"] is None and decided["fix_stopped"] == "budget_exhausted"
    assert [(r.role, r.revision) for r in decided["runs"]] == [("control", "vulnerable"), ("exploit", "vulnerable")]


def test_unreviewed_bytes_are_never_executed(tmp_path):
    fakes = Fakes(unbound={"vulnerable"})
    _, decided = go(fakes, tmp_path, fixed=True)
    assert fakes.of("execute") == [] and decided["runs"] == ()
    # Nothing on the vulnerable revision bound, so the fixed revision is not reviewed either.
    assert decided["validity"] == () and [kw["revision"] for _, kw in fakes.of("review")] == ["vulnerable"]
    fakes = Fakes(unbound={"fixed"})
    _, decided = go(fakes, tmp_path / "f", fixed=True)
    assert [kw["revision"] for _, kw in fakes.of("execute")] == ["vulnerable", "vulnerable"]
    assert decided["stopped"] is None and decided["fix_stopped"] is None


# --- Review loop (SPEC-0082): feedback from the Reviewer, at most MAX_REVIEWS reviews ----------------------------

def _steps(tmp_path, run="run"):
    return [t["step"] for t in json.loads((tmp_path / "runs" / run / "timings.json").read_text())]


def test_a_rejected_exploit_gets_only_its_own_review_and_the_control_is_untouched(tmp_path):
    fakes = Fakes(rejections={"exploit": 1})
    verdict, decided = go(fakes, tmp_path)
    controls, exploits = fakes.of("probe-control"), fakes.of("probe-exploit")
    assert len(controls) == 1 and controls[0][1]["review_feedback"] is None
    assert len(exploits) == 2
    feedback = exploits[1][1]["review_feedback"]
    assert exploits[1][1]["previous"] == draft("exploit") and exploits[1][1]["diagnostics"] is None
    assert feedback.startswith("Failed checks: calls_real_target, assertion_relevant")
    assert [line for line in feedback.splitlines() if line.startswith("- exploit defect")] == [
        f"- exploit defect {i}" for i in range(4)]  # at most four defects
    assert "tests/test_exploit.x:1-1" in feedback and "exploit own line" in feedback
    assert "src/a.x:1-2" in feedback and "return x" in feedback
    # Nothing of the other probe, and nothing from any run.
    assert "control" not in feedback and "secret" not in feedback
    for word in ("outcome", "passed", "assertion_failed", "exit_code", "marker", "token", "patch_sha256"):
        assert word not in feedback
    # The revised exploit replaces the old bytes; the control keeps its own.
    final = fakes.of("review")[1][0][2]
    assert final.control == draft("control") and "review-revised" in final.exploit.source
    assert final.exploit.revision_of == draft_digest(draft("exploit"))
    assert (verdict.review_rounds, verdict.revisions, verdict.first_review_valid) == (
        2, {"exploit": 1}, {"control": True, "exploit": False})
    assert _steps(tmp_path) == ["select", "investigate", "build", "replay-build", "probe-control", "probe-exploit",
                                "diagnose-control", "diagnose-exploit", "review.1", "probe.exploit.r1",
                                "diagnose.exploit.r1", "review.2", "execute-control-vulnerable",
                                "execute-exploit-vulnerable", "decide"]


def test_execution_runs_only_the_last_reviewed_digest(tmp_path):
    fakes = Fakes(rejections={"control": 1, "exploit": 2})
    _, decided = go(fakes, tmp_path, fixed=True)
    reviews = [(a[2].sha256, kw["revision"]) for a, kw in fakes.of("review")]
    assert [r for _, r in reviews] == ["vulnerable", "vulnerable", "vulnerable", "fixed"]
    final = reviews[2][0]
    assert len({sha for sha, _ in reviews[:3]}) == 3 and reviews[3][0] == final
    assert {a[2].sha256 for a, _ in fakes.of("execute")} == {final}
    assert [v.patch_sha256 for v in decided["validity"]] == [final, final]
    assert all(v.control.valid and v.exploit.valid for v in decided["validity"])
    # The control was rejected once only, so it revised once; the exploit twice.
    assert len(fakes.of("probe-control")) == 2 and len(fakes.of("probe-exploit")) == 3
    steps = _steps(tmp_path)
    assert steps.index("review.3") < steps.index("review-fixed") < steps.index("execute-control-vulnerable")
    assert {"probe.control.r1", "probe.exploit.r1", "probe.exploit.r2", "review.2"} <= set(steps)
    assert "probe.control.r2" not in steps


def test_at_most_three_reviews_and_then_nothing_executes(tmp_path):
    fakes = Fakes(rejections={"exploit": 99})
    verdict, decided = go(fakes, tmp_path, fixed=True)
    assert [kw["revision"] for _, kw in fakes.of("review")] == ["vulnerable"] * MAX_REVIEWS == ["vulnerable"] * 3
    assert len(fakes.of("probe-exploit")) == 1 + (MAX_REVIEWS - 1)
    assert fakes.of("execute") == [] and decided["runs"] == () and decided["stopped"] is None
    # Decide sees only the last review, bound to the last digest, negative for the exploit (R2).
    (last,) = decided["validity"]
    assert last.patch_sha256 == fakes.of("review")[-1][0][2].sha256 and not last.exploit.valid
    assert verdict.review_rounds == 3 and verdict.revisions == {"exploit": 2}


def test_real_rules_read_a_still_invalid_pair_as_test_invalid(tmp_path):
    from corsair.v2.rules import decide
    fakes = Fakes(rejections={"control": 99})
    fakes.decide = lambda case, **kw: (fakes._log("decide", case, **kw), decide(case, **kw))[1]
    verdict, _ = go(fakes, tmp_path)
    assert (verdict.label.value, verdict.rule_id, verdict.terminal_reason.value) == ("INCONCLUSIVE", "R2",
                                                                                     "test_invalid")
    summary = json.loads((tmp_path / "runs" / "run" / "summary.json").read_text())
    assert summary["review"]["authors"]["control"] == {"first_review_valid": False, "revisions_used": 2,
                                                       "mechanical_fixes": 0, "final_valid": False,
                                                       "recovered": False}
    fakes = Fakes(rejections={"control": 1})
    fakes.decide = lambda case, **kw: (fakes._log("decide", case, **kw), decide(case, **kw))[1]
    verdict, _ = go(fakes, tmp_path / "b")
    assert verdict.rule_id == "R4"  # the fake runs pass (a PoV pass): executed, so no longer R2
    summary = json.loads((tmp_path / "b" / "runs" / "run" / "summary.json").read_text())
    assert summary["review"]["authors"]["control"]["recovered"] is True


@pytest.mark.parametrize("calls, reviews, stale", [(5, 1, False), (6, 1, True)])
def test_budget_exhaustion_ends_the_loop_and_nothing_executes(tmp_path, calls, reviews, stale):
    # Calls: investigate, build, two probes, review.1 (= 5), then probe.exploit.r1 (= 6), then review.2.
    fakes = Fakes(rejections={"exploit": 99})
    _, decided = go(fakes, tmp_path, budget=Budget(max_agent_calls=calls))
    assert len(fakes.of("review")) == reviews and fakes.of("execute") == []
    assert decided["stopped"] is None and decided["runs"] == ()
    # A revision that was never reviewed leaves no validity: the earlier digest's review never counts.
    assert decided["validity"] == () if stale else not decided["validity"][0].exploit.valid


def test_budget_exhausted_at_the_first_review_stays_a_budget_stop(tmp_path):
    fakes = Fakes(rejections={"exploit": 99})
    _, decided = go(fakes, tmp_path, budget=Budget(max_agent_calls=4))
    assert decided["stopped"] == "budget_exhausted" and fakes.of("review") == []


def test_a_failed_review_revision_keeps_the_previous_draft_and_ends_that_author(tmp_path):
    fakes = Fakes(rejections={"control": 99, "exploit": 99}, review_revised={"control": None})
    verdict, decided = go(fakes, tmp_path)
    assert len(fakes.of("probe-control")) == 2  # one failed revision, never asked again
    assert len(fakes.of("probe-exploit")) == 3
    reviewed = [a[2] for a, _ in fakes.of("review")]
    assert all(p.control == draft("control") for p in reviewed)
    assert verdict.revisions == {"control": 1, "exploit": 2} and fakes.of("execute") == []
    # When no author can revise, no further review is spent.
    fakes = Fakes(rejections={"exploit": 99}, review_revised={"exploit": None})
    go(fakes, tmp_path / "b")
    assert len(fakes.of("review")) == 1


def test_a_revision_over_its_own_usage_limit_keeps_the_previous_draft(tmp_path):
    fakes = Fakes(rejections={"exploit": 99})
    original = fakes.exploit_probe

    async def limited(*args, **kwargs):
        if kwargs.get("review_feedback") is not None:
            fakes._log("probe-exploit", *args, **kwargs)
            raise UsageLimitExceeded("request_limit")
        return await original(*args, **kwargs)
    fakes.exploit_probe = limited
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] is None and len(fakes.of("review")) == 1 and fakes.of("execute") == []


def test_a_provider_error_in_a_review_revision_stops_the_run(tmp_path):
    fakes = Fakes(rejections={"exploit": 99})
    original = fakes.exploit_probe

    async def failing(*args, **kwargs):
        if kwargs.get("review_feedback") is not None:
            raise ModelHTTPError(503, "m")
        return await original(*args, **kwargs)
    fakes.exploit_probe = failing
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] == "provider_error"


def test_the_mechanical_check_reruns_on_a_review_revision_with_its_own_correction(tmp_path):
    fakes = Fakes(rejections={"exploit": 1}, diagnose_outcomes={"exploit": ["ok", "errored"]})
    verdict, _ = go(fakes, tmp_path)
    steps = _steps(tmp_path)
    assert steps[steps.index("review.1"):steps.index("review.2") + 1] == [
        "review.1", "probe.exploit.r1", "diagnose.exploit.r1", "probe.exploit.r1.revision",
        "diagnose.exploit.r1.1", "review.2"]
    assert verdict.mechanical_fixes == {"exploit": 1}
    corrected = fakes.of("probe-exploit")[-1][1]
    assert corrected["review_feedback"] is None and "check: errored" in corrected["diagnostics"]
    assert "review-revised" in corrected["previous"].source
    assert len(fakes.of("diagnose")) == 4  # both first drafts, then only the revised exploit and its correction


def test_an_incomplete_review_gives_no_feedback(tmp_path):
    from chain_fakes import usage
    fakes = Fakes(rejections={"exploit": 99}, usages={"reviewer": usage("reviewer", status="output_invalid")})
    verdict, decided = go(fakes, tmp_path)
    assert len(fakes.of("probe-exploit")) == 1 and len(fakes.of("review")) == 1 and fakes.of("execute") == []
    assert verdict.first_review_valid == {} and verdict.review_rounds == 1


def test_review_feedback_is_built_from_one_probe_validity_only():
    from chain_fakes import rejected
    text = review_feedback(rejected("control"), "tests/test_exploit.x")
    assert "control own line" in text and "exploit" not in text
    assert max(len(line) for line in text.splitlines()) <= 1_024 + 2


def test_a_builder_refusal_stops_at_build_failed_with_its_reason_and_no_second_episode(tmp_path):
    from corsair.v2.contracts import Recipe
    fakes = Fakes(recipes=[Recipe(blocked="no compiler in this image")])
    _, decided = go(fakes, tmp_path)
    assert decided["stopped"] == "build_failed" and "replay" not in fakes.names()
    assert fakes.names().count("build") == 1 and "no compiler" in decided["build"].reason


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_d3_corrects_until_the_check_reads_ok(tmp_path, failures):
    from corsair.v2.chain import MAX_MECHANICAL_FIXES
    # The first draft and the first failures - 1 corrections fail; correction number ``failures`` reads ok.
    fakes = Fakes(diagnose_outcomes={"control": ["errored"] * failures})
    verdict, _ = go(fakes, tmp_path)
    controls = fakes.of("probe-control")
    assert len(controls) == 1 + failures <= 1 + MAX_MECHANICAL_FIXES
    assert all("check: errored" in kw["diagnostics"] for _, kw in controls[1:])
    assert all(kw["previous"] is not None for _, kw in controls[1:])
    assert len(fakes.of("diagnose")) == 2 + failures  # both first drafts, then every correction
    corrections = ["probe-control-revision"] + [f"probe-control-revision.{k}" for k in range(2, failures + 1)]
    checks = [f"diagnose-control.{k}" for k in range(1, failures + 1)]
    steps = _steps(tmp_path)
    assert [s for s in steps if s.startswith("probe-control-revision")] == corrections
    assert [s for s in steps if s.startswith("diagnose-control.")] == checks
    assert verdict.mechanical_fixes == {"control": failures}
    summary = json.loads((tmp_path / "runs" / "run" / "summary.json").read_text())
    assert summary["review"]["authors"]["control"]["mechanical_fixes"] == failures
    assert summary["review"]["authors"]["exploit"]["mechanical_fixes"] == 0
    assert fakes.names()[-1] == "decide" and len(fakes.of("execute")) == 2


def test_d3_stops_after_the_last_correction_and_reviews_the_last_draft(tmp_path):
    from corsair.v2.chain import MAX_MECHANICAL_FIXES
    fakes = Fakes(diagnose_outcomes={"exploit": "not_run"})  # every check of the exploit fails
    verdict, _ = go(fakes, tmp_path)
    assert len(fakes.of("probe-exploit")) == 1 + MAX_MECHANICAL_FIXES
    assert len(fakes.of("diagnose")) == 2 + MAX_MECHANICAL_FIXES
    assert verdict.mechanical_fixes == {"exploit": MAX_MECHANICAL_FIXES}
    reviewed = fakes.of("review")[0][0][2]
    assert reviewed.exploit == fakes.of("diagnose")[-1][0][2]  # the last checked correction goes on as is


def test_d3_budget_exhaustion_mid_corrections_stops_the_run(tmp_path):
    # Calls: investigate, build, two probes (= 4), then corrections 1 and 2 (= 6); the third is over budget.
    fakes = Fakes(diagnose_outcomes={"control": "errored"})
    verdict, decided = go(fakes, tmp_path, budget=Budget(max_agent_calls=6))
    assert decided["stopped"] == "budget_exhausted"
    assert len(fakes.of("probe-control")) == 3 and fakes.of("review") == []
    assert verdict.mechanical_fixes == {"control": 2}


def test_d3_corrections_after_a_review_revision_are_bounded_per_draft_version(tmp_path):
    from corsair.v2.chain import MAX_MECHANICAL_FIXES
    # The first draft fails twice then reads ok; the review revision fails every check.
    outcomes = ["errored", "errored", "ok"] + ["not_run"] * 4
    fakes = Fakes(rejections={"exploit": 1}, diagnose_outcomes={"exploit": outcomes})
    verdict, _ = go(fakes, tmp_path)
    steps = _steps(tmp_path)
    assert [s for s in steps if s.startswith("probe.exploit.r1.revision")] == [
        "probe.exploit.r1.revision", "probe.exploit.r1.revision.2", "probe.exploit.r1.revision.3"]
    assert [s for s in steps if s.startswith("diagnose.exploit.r1")] == [
        "diagnose.exploit.r1", "diagnose.exploit.r1.1", "diagnose.exploit.r1.2", "diagnose.exploit.r1.3"]
    assert verdict.mechanical_fixes == {"exploit": 2 + MAX_MECHANICAL_FIXES}
