import json
"""Chain routing with fake stages: order, early stops, A2/D3 correction bounds and review blindness."""
import asyncio

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

from chain_fakes import PLAN, RECIPE, Fakes, case, draft, models
from corsair.v2.chain import Budget, draft_digest, freeze, run_case
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
    assert [(a[3], kw["revision"]) for a, kw in fakes.of("execute")] == [
        ("control", "vulnerable"), ("exploit", "vulnerable"), ("control", "fixed"), ("exploit", "fixed")]
    # Review of both revisions comes before any execution.
    names = fakes.names()
    assert max(i for i, n in enumerate(names) if n == "review") < names.index("execute")


@pytest.mark.parametrize("setup, reason, last", [
    (dict(runtime=None), "no_runtime", "select"),
    (dict(plan=None), "plan_unresolved", "investigate"),
    (dict(plan=ProbePlan(status="target_not_found", reason="x")), "plan_unresolved", "investigate"),
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
def test_d3_gives_a_failed_author_one_revision_with_its_check_result(tmp_path, outcome):
    fakes = Fakes(diagnose_outcomes={"control": outcome})
    _, decided = go(fakes, tmp_path)
    controls, exploits = fakes.of("probe-control"), fakes.of("probe-exploit")
    assert len(controls) == 2 and len(exploits) == 1
    assert controls[0][1]["diagnostics"] is None
    assert controls[1][1]["diagnostics"] == f"check: {outcome}\nhint: control hint"
    assert controls[1][1]["previous"] == draft("control")
    assert len(fakes.of("diagnose")) == 2  # the revision is not diagnosed again
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


def test_d3_both_authors_revise_once_and_a_failed_revision_keeps_the_original(tmp_path):
    fakes = Fakes(diagnose_outcomes={"control": "errored", "exploit": "not_run"},
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
    assert [v.revision for v in decided["validity"]] == ["fixed"]
    fakes = Fakes(unbound={"fixed"})
    _, decided = go(fakes, tmp_path / "f", fixed=True)
    assert [kw["revision"] for _, kw in fakes.of("execute")] == ["vulnerable", "vulnerable"]
    assert decided["stopped"] is None and decided["fix_stopped"] is None
