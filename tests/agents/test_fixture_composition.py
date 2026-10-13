"""E2E-0 direct composition over the SPEC-0018 pair with scripted stage models and real reviewed pytest runs."""
import asyncio
import base64
import hashlib
import json
from uuid import uuid4, uuid5
from dataclasses import replace

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.test_authoring.contracts import BlockedAuthoring, TestPatch
from corsair.composition.direct import (
    UNOBSERVED, UNSELECTED, BudgetExhausted, CompositionBudget, RecordedFailure, StageModels, exhaustion, run_direct,
)
from corsair.composition.evidence import freeze, observation_plan, run_evidence
from corsair.core.disposition import AssessmentEvidence, Disposition, Witness, assess
from corsair.ports.test_runner import WitnessRequest
from evals.fixture_e2e.case import (
    SECURITY_ASSERTION_LINES, fixture_case, reviewed_runners, scripted_assessment, scripted_authoring,
    scripted_identification, scripted_planning,
)

CONTROL = "test_documents.py::test_benign_control"
SECURITY = "test_documents.py::test_security_rejects_outside_read"


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


@pytest.fixture
def store(tmp_path):
    (tmp_path / "artifacts").mkdir(mode=0o700)
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as artifacts:
        yield artifacts


def stages(**overrides):
    values = dict(identification=scripted_identification(), planning=scripted_planning(),
                  authoring=scripted_authoring(), assessment=scripted_assessment())
    return StageModels(**(values | overrides))


class WithoutWitness:
    """An execution node that captures no witness: the probe request is dropped before the runner."""
    def __init__(self, runner):
        self.runner = runner

    def run(self, patch, *, witness=None, **values):
        return self.runner.run(patch, **values)


def compose(store, root, witnessed=True, **overrides):
    (root / "work").mkdir()
    runners = reviewed_runners(store, root / "work")
    factory = runners if witnessed else (lambda purpose: WithoutWitness(runners(purpose)))
    return asyncio.run(run_direct(fixture_case(), stages(**overrides), factory))


def prompts(run):
    return [part.content for attempt in run.attempts for message in attempt.messages for part in message.parts
            if part.part_kind == "user-prompt"]


def test_stages_compose_to_a_gate_verdict_that_stays_inconclusive_without_a_witness(store, tmp_path):
    run = compose(store, tmp_path, witnessed=False)
    assert (run.stopped_at, run.reason) == (None, "complete")
    assert [a.stage for a in run.attempts] == ["identification", "planning", "authoring", "assessment"]
    assert all(a.failure is None for a in run.attempts)

    expected = run.observation_plan
    assert (expected.control_test_id, expected.security_test_id) == (CONTROL, SECURITY)
    assert expected.expected_failure.model_dump() == {"exception_type": "AssertionError", "path": "test_documents.py",
                                                      "function": "test_security_rejects_outside_read",
                                                      "assertion_lines": tuple(SECURITY_ASSERTION_LINES)}
    assert expected.expected_safe_behavior == "ValueError"
    assert expected.frozen_patch_sha256 == run.patch.patch_sha256

    # Both frozen runs executed the authored digest in fresh workspaces with confirmed cleanup.
    baseline, candidate = (e.observed for e in run.executions)
    assert {e.revision for e in run.executions} == {"baseline", "candidate"}
    for observed in (baseline, candidate):
        assert (observed.failure_layer, observed.cleanup) == (None, "confirmed")
        assert observed.patch_sha256 == run.patch.patch_sha256
    base_security, cand_security = baseline.execution.cases[1], candidate.execution.cases[1]
    assert (base_security.outcome, cand_security.outcome) == ("failed", "passed")
    failure = base_security.failure
    assert (failure.type, failure.path, failure.function) == ("AssertionError", "test_documents.py",
                                                              "test_security_rejects_outside_read")
    assert failure.line in SECURITY_ASSERTION_LINES

    # The only reason neither revision is usable is the missing witness, by design.
    gate = run.gate
    assert gate.permitted == Disposition(execution="completed", finding="inconclusive", fix="not_verified")
    assert {(r.revision, r.classification) for r in gate.runs} == {("baseline", "unusable"), ("candidate", "unusable")}
    assert {(l.code, l.revision) for l in gate.limitations} == {
        ("witness_missing", "baseline"), ("witness_missing", "candidate"), ("no_valid_run", "baseline"),
        ("baseline_not_reproduced", "candidate")}
    assert run.assessment.admission.admitted and run.assessment.disposition == gate.permitted
    assert run.limitations == UNOBSERVED + (UNSELECTED,) + tuple(f"{revision} witness not admitted: no witness was requested or "
                                                 "captured for this run" for revision in ("baseline", "candidate"))

    # Agents never see which variant is which.
    assert not any(label in prompt for prompt in prompts(run) for label in ("vulnerable", "fixed"))


def test_an_over_claim_without_a_witness_item_is_refused_and_the_gate_verdict_stands(store, tmp_path):
    run = compose(store, tmp_path, witnessed=False,
                  assessment=scripted_assessment(finding="reproduced", fix="verified"))
    assert (run.stopped_at, run.assessment) == ("assessment", None)
    assert run.gate.permitted == Disposition(execution="completed", finding="inconclusive", fix="not_verified")
    retries = [part.content for message in run.attempts[-1].messages for part in message.parts
               if part.part_kind == "retry-prompt"]
    assert retries and all("no witness item for the baseline revision" in retry for retry in retries)


def test_the_probe_witness_lets_the_gate_reach_reproduced_and_verified(store, tmp_path):
    """The real operator probe runs in both revisions' interpreters; its records are the only new gate input."""
    run = compose(store, tmp_path, assessment=scripted_assessment(finding="reproduced", fix="verified"))
    baseline, candidate = (w.witness for w in run.witnesses)
    assert (baseline.path_reached, baseline.effect, baseline.safe_behavior) == (True, "observed", None)
    assert (candidate.path_reached, candidate.effect, candidate.safe_behavior) == (True, "absent", "ValueError")
    for execution, found in zip(run.executions, run.witnesses):
        captured = execution.observed.witness
        assert found.sandbox_events == () and captured.status == "captured"
        assert baseline is not None and store.get(captured.artifact) == captured.record
        assert captured.receipt.operation == str(uuid5(execution.operation, "witness"))
    gate = run.gate
    assert gate.permitted == Disposition(execution="completed", finding="reproduced", fix="verified")
    assert {(r.revision, r.classification) for r in gate.runs} == {("baseline", "reproduces"), ("candidate", "safe")}
    assert gate.limitations == () and run.limitations == UNOBSERVED + (UNSELECTED,)
    assert run.assessment.admission.admitted and run.assessment.disposition == gate.permitted
    # The assessor may read each record as its own item; the variant names never reach it.
    assert any("baseline-0-witness (kind witness" in prompt for prompt in prompts(run))
    assert not any(label in prompt for prompt in prompts(run) for label in ("vulnerable", "fixed"))


def test_handoff_builders_refuse_a_patch_that_is_not_this_plan(store, tmp_path):
    run = compose(store, tmp_path)
    with pytest.raises(ValueError, match="test ids"):
        observation_plan(run.plan, run.patch.model_copy(update={"security_test_id": "test_documents.py::test_other"}))
    with pytest.raises(ValueError, match="sandbox events"):
        run_evidence(run.executions[0].observed, environment=fixture_case().environment_identity,
                     witness=Witness(artifact_sha256="0" * 64, path_reached=True, effect="observed"))
    with pytest.raises(ValueError, match="digest"):
        freeze(run.patch.model_copy(update={"patch_sha256": "0" * 64}), ("test_documents.py",))


def test_identification_abstention_ends_the_run_before_planning(store, tmp_path):
    async def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "status": "missing_information", "scope": "component", "target": None,
            "reason": "The configured documents directory is not in the saved source"})])
    run = compose(store, tmp_path, identification=FunctionModel(respond))
    assert run.stopped_at == "identification" and "missing_information" in run.reason
    assert [a.stage for a in run.attempts] == ["identification"] and run.gate is None
    assert not (tmp_path / "work" / "development").exists()


def test_planning_unsupported_ends_the_run_before_authoring(store, tmp_path):
    async def respond(messages, info):
        if not any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": "documents.py"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"plan": {
            "status": "unsupported", "scope": "component", "missing_capability": "No observation of file opens",
            "limitations": ["Scripted"], "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}]}})])
    run = compose(store, tmp_path, planning=FunctionModel(respond))
    assert run.stopped_at == "planning" and run.reason == "plan unsupported: No observation of file opens"
    assert run.patch is None and not (tmp_path / "work" / "development").exists()


def test_unreviewed_test_bytes_never_execute_on_the_host(store, tmp_path):
    """A live author's test reaches no interpreter here: the reviewed workspace refuses it before execution."""
    script = [ToolCallPart("write_test_file", {"path": "test_documents.py", "content": "def test_x():\n    assert True\n"}),
              ToolCallPart("run_tests", {})]

    async def respond(messages, info):
        done = sum(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        if done < len(script):
            return ModelResponse(parts=[replace(script[done], tool_call_id=f"call-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": {
            "status": "blocked", "layer": "sandbox", "reason": "The development workspace refused the patch"}})])
    run = compose(store, tmp_path, authoring=FunctionModel(respond))
    assert run.stopped_at == "authoring" and run.reason.startswith("authoring blocked at sandbox")
    authored = run.attempts[-1].output
    assert isinstance(authored, BlockedAuthoring) and not isinstance(authored, TestPatch)
    (dev_run,) = authored.dev_runs
    assert dev_run.status == "workspace_failure" and "reviewed SPEC-0018" in dev_run.errors
    assert not (tmp_path / "work" / "development").exists() and run.executions == ()


def test_a_run_from_the_wrong_revision_is_never_labelled_as_the_requested_one(store, tmp_path):
    """A runner factory that hands the candidate the baseline source is refused before any gate evidence."""
    (tmp_path / "work").mkdir()
    runners = reviewed_runners(store, tmp_path / "work")
    runner = lambda purpose: runners("baseline" if purpose == "candidate" else purpose)
    run = asyncio.run(run_direct(fixture_case(), stages(), runner))
    assert run.stopped_at == "execution" and run.gate is None
    assert run.reason == "candidate workspace source is not the candidate revision"


def test_cli_keeps_every_native_run_with_its_bindings_and_failures(tmp_path):
    """Saved evidence keeps receipts, artifact references and failures without any assessment read."""
    from evals.fixture_e2e import run as cli
    evidence = tmp_path / "evidence"
    result = asyncio.run(cli.main_async(evidence, (), None))
    entries = json.loads((evidence / "native-runs.json").read_text())
    assert [e["purpose"] for e in entries] == ["development", "baseline", "candidate"]
    sources = fixture_case().revision_sources
    for entry, execution in zip(entries[1:], result.executions):
        observed = entry["observed"]
        assert entry["operation"] == observed["operation"] == str(execution.operation)
        assert observed["workspace"]["source"]["sha256"] == sources[execution.revision]
        receipt = observed["execution"]["receipt"]
        assert (receipt["delivery"], receipt["completion"], receipt["operation"]) == (
            "acknowledged", "terminal_observed", str(uuid5(execution.operation, "execution")))
        junit = base64.b64decode(receipt["stdout"]["base64"])
        assert observed["execution"]["junit"]["sha256"] == receipt["stdout"]["sha256"] == hashlib.sha256(junit).hexdigest()
        assert observed["discovery"]["command"] and observed["execution"]["command"]


def test_journal_keeps_a_refused_development_run(store, tmp_path):
    from evals.fixture_e2e.run import Journal
    from corsair.ports.test_runner import ApprovedPatch, PatchFile
    (tmp_path / "work").mkdir()
    journal = Journal(reviewed_runners(store, tmp_path / "work"))
    patch = ApprovedPatch((PatchFile("test_documents.py", b"def test_x():\n    assert True\n"),), ("test_documents.py",))
    journal("development").run(patch, control_test_id=CONTROL, security_test_id=SECURITY,
                                discovery_command=("python",), operation=uuid4())
    (entry,) = journal.entries
    observed = entry["observed"]
    assert observed["failure_layer"] == "workspace" and observed["cleanup"] == "unconfirmed"
    assert "reviewed SPEC-0018" in observed["detail"]


def test_checked_in_stage_profiles_admit_per_stage_reasoning_budgets():
    """The operator profile is admitted by LocalModelConfig and only changes the named request controls."""
    from pathlib import Path
    from evals.fixture_e2e import run as cli
    from corsair.agents.provider import LocalModelConfig, model_settings
    base = LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="explicit-model",
                            timeout_seconds=180, response_token_limit=16384)
    profiles = json.loads((Path(cli.__file__).parent / "stage-profiles.json").read_text())
    configs = cli.stage_configs(base, profiles)
    assert {stage: (c.response_token_limit, c.thinking_token_budget) for stage, c in configs.items()} == {
        "identification": (8192, None), "planning": (8192, 2048), "authoring": (8192, 2048),
        "assessment": (16384, 2048)}
    assert all(c.model_dump(exclude=cli.PROFILE_FIELDS) == base.model_dump(exclude=cli.PROFILE_FIELDS)
               for c in configs.values())
    assert model_settings(configs["planning"])["extra_body"] == {"thinking_token_budget": 2048}
    for bad in ({"planning": {"base_url": "https://other.example/v1"}}, {"review": {}},
                {"planning": {"thinking_token_budget": 4096}}):
        with pytest.raises(ValueError):
            cli.stage_configs(base, bad)


@pytest.mark.parametrize("envelope, reason", [
    (None, "the operator approved no witness envelope for this case"),
    (WitnessRequest("documents.py", "other_function", "outside.txt"),
     "the identified target is outside the operator witness envelope")])
def test_a_target_outside_the_operator_envelope_runs_without_a_witness(store, tmp_path, envelope, reason):
    """No conclusive witness outside an operator-approved target and effect; the chain still completes."""
    (tmp_path / "work").mkdir()
    case = replace(fixture_case(), witness_envelope=envelope)
    run = asyncio.run(run_direct(case, stages(), reviewed_runners(store, tmp_path / "work")))
    assert run.stopped_at is None and all(e.observed.witness is None for e in run.executions)
    assert run.gate.permitted == Disposition(execution="completed", finding="inconclusive", fix="not_verified")
    assert f"no witness requested: {reason}" in run.limitations
    assert not any("witness (kind witness" in prompt for prompt in prompts(run))


def _process_start_planning():
    """The reference plan with both witnesses moved to a listed process_start facility the probe does not record."""
    from evals.fixture_e2e.case import DISCOVER, _reads_then, reference_plan
    plan = reference_plan(DISCOVER)
    for name in ("control", "security"):
        plan[name] = plan[name] | {"witness": plan[name]["witness"] | {"facility": "audit_exec", "effect": "process_start"}}
    return _reads_then(["documents.py", "test_existing.py"], lambda info: {"plan": plan})


def _security_subject_planning(subject):
    from evals.fixture_e2e.case import DISCOVER, _reads_then, reference_plan
    plan = reference_plan(DISCOVER)
    plan["security"] = plan["security"] | {"witness": plan["security"]["witness"] | {"subject": subject}}
    return _reads_then(["documents.py", "test_existing.py"], lambda info: {"plan": plan})


def test_a_planned_witness_the_envelope_does_not_record_runs_without_a_witness(store, tmp_path):
    """SPEC-0040 kinds without a recorder, or another subject, never borrow the envelope's file-open evidence."""
    from corsair.agents.test_planning.contracts import WitnessFacility
    base = fixture_case()
    process = WitnessFacility(id="audit_exec", kind="process_start", description="Process start audit events")
    environment = base.environment.model_copy(update={
        "witness_facilities": base.environment.witness_facilities + (process,)})
    unbound = "the planned process_start witness is not recorded by the operator probe"
    other = "the planned witness subject is not the operator witness envelope effect"
    cases = [
        (unbound, replace(base, environment=environment), stages(planning=_process_start_planning())),
        (other, replace(base, witness_envelope=WitnessRequest("documents.py", "read_document", "other.txt")), stages()),
        # A directory-prefixed subject with the envelope's file name is another path, not the envelope's effect.
        (other, base, stages(planning=_security_subject_planning("different/outside.txt"))),
    ]
    for index, (reason, case, models_) in enumerate(cases):
        (tmp_path / f"work{index}").mkdir()
        run = asyncio.run(run_direct(case, models_, reviewed_runners(store, tmp_path / f"work{index}")))
        assert run.stopped_at is None and all(e.observed.witness is None for e in run.executions)
        assert run.gate.permitted == Disposition(execution="completed", finding="inconclusive", fix="not_verified")
        assert f"no witness requested: {reason}" in run.limitations


def test_a_planned_absence_is_verified_when_the_fix_never_opens_the_sentinel(store, tmp_path):
    """SPEC-0040 `no_file_open` safe behavior: the fixed revision's rejection without the open is safe."""
    from evals.fixture_e2e.case import DISCOVER, _reads_then, reference_plan
    plan = reference_plan(DISCOVER)
    plan["security_expectation"] = plan["security_expectation"] | {"safe_behavior": "no_file_open"}
    planning = _reads_then(["documents.py", "test_existing.py"], lambda info: {"plan": plan})
    (tmp_path / "work").mkdir()
    run = asyncio.run(run_direct(fixture_case(), stages(planning=planning), reviewed_runners(store, tmp_path / "work")))
    assert run.observation_plan.expected_safe_behavior == "no_file_open"
    assert run.gate.permitted == Disposition(execution="completed", finding="reproduced", fix="verified")


def test_stage_limits_are_derived_from_each_stage_input_and_recorded(store, tmp_path):
    run = compose(store, tmp_path)
    limits = {a.stage: a.limits for a in run.attempts}
    # Two saved files of one window each; authoring adds three runs of (two writes and one run) on one test path
    # and one admission refusal; assessment reads every frozen evidence item once.
    assert (limits["identification"].read_windows, limits["identification"].tool_calls_limit) == (2, 4)
    assert (limits["planning"].read_windows, limits["planning"].tool_calls_limit) == (2, 4)
    assert (limits["authoring"].work_tool_calls, limits["authoring"].tool_calls_limit) == (10, 14)
    assert limits["assessment"].read_windows == 9 and limits["assessment"].tool_calls_limit == \
        limits["assessment"].read_windows + 3
    for attempt in run.attempts:
        assert attempt.exhausted is None and attempt.usage.tool_calls <= attempt.limits.tool_calls_limit
        assert attempt.limits.request_limit == attempt.limits.tool_calls_limit + 3


def test_a_stage_that_cannot_finish_without_its_withdrawn_tools_is_tool_budget_exhausted(store, tmp_path):
    """The scripted assessor insists on reading every item; at the cap its tools are withdrawn and it cannot answer."""
    budget = CompositionBudget(assessment=CompositionBudget().assessment.model_copy(update={"tool_calls_limit": 3}))
    (tmp_path / "work").mkdir()
    run = asyncio.run(run_direct(fixture_case(), stages(), reviewed_runners(store, tmp_path / "work"), budget))
    assessment = run.attempts[-1]
    assert assessment.stage == "assessment" and assessment.usage.tool_calls == 3 and assessment.output is None
    assert (assessment.exhausted.limit, assessment.exhausted.cap) == ("tool_calls_limit", 3)
    assert run.stopped_at == "assessment" and run.reason.startswith("assessment budget exhausted: tool_calls_limit 3")
    # The gate verdict over the frozen evidence does not depend on the assessor.
    assert run.gate is not None


def test_a_stage_ending_on_its_cap_is_a_typed_budget_exhaustion(store, tmp_path):
    budget = CompositionBudget(authoring=CompositionBudget().authoring.model_copy(update={"request_limit": 2}))
    (tmp_path / "work").mkdir()
    run = asyncio.run(run_direct(fixture_case(), stages(), reviewed_runners(store, tmp_path / "work"), budget))
    authoring = run.attempts[-1]
    assert run.stopped_at == "authoring" and authoring.output is None
    assert isinstance(authoring.exhausted, BudgetExhausted)
    assert (authoring.exhausted.limit, authoring.exhausted.cap) == ("request_limit", 2)
    assert run.reason.startswith("authoring budget exhausted: request_limit 2 (derived from 2 read windows")
    assert exhaustion("planning", authoring.limits, ValueError("x")) is None
    # Codex review on 78f1690: only the stage's own deadline is its timeout budget; a provider, tool or activity
    # timeout inside the stage keeps its own classification.
    assert exhaustion("planning", authoring.limits, RecordedFailure("TimeoutError", "late")) is None
    assert exhaustion("planning", authoring.limits, RecordedFailure("TimeoutError", "late"), deadline=True).limit == \
        "timeout_seconds"


def test_an_unrelated_failure_after_the_tool_cap_keeps_its_own_classification(store, tmp_path):
    """Review on #49: reaching the cap is recorded, but only a native limit error is exhaustion.

    A call to a tool withdrawn at the cap is refused natively as UsageLimitExceeded; UnexpectedModelBehavior is
    also what providers raise for malformed responses, so it never establishes the cap, at or past it.
    """
    from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
    limits = CompositionBudget().planning.limits(2, 0, 1)
    for failure in (ValueError("provider response was invalid"), RecordedFailure("ModelAPIError", "500"),
                    UnexpectedModelBehavior("Exceeded maximum output retries (1)"),
                    UnexpectedModelBehavior("Received empty model response"),
                    RecordedFailure("UnexpectedModelBehavior", "Invalid response from provider")):
        assert exhaustion("planning", limits, failure) is None
    for failure in (UsageLimitExceeded("The next tool call(s) would exceed the tool_calls_limit of 4 (tool_calls=5)"),
                    RecordedFailure("UsageLimitExceeded", "would exceed the tool_calls_limit of 4")):
        assert exhaustion("planning", limits, failure).limit == "tool_calls_limit"


def test_a_call_to_a_withdrawn_tool_is_refused_natively_as_the_tool_call_limit():
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import UsageLimitExceeded
    from pydantic_ai.usage import UsageLimits
    from corsair.agents.budget import tool_budget

    async def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart("probe", {})])
    agent = Agent(FunctionModel(respond), output_type=int, capabilities=[tool_budget()],
                  retries={"tools": 0, "output": 1})

    @agent.tool_plain
    def probe() -> int:
        return 1
    limits = CompositionBudget().planning.limits(0, 0, 1)
    with pytest.raises(UsageLimitExceeded) as failed:
        agent.run_sync("x", usage_limits=UsageLimits(tool_calls_limit=1, request_limit=10))
    assert exhaustion("planning", limits, failed.value).limit == "tool_calls_limit"


def test_an_attempt_records_reaching_its_tool_cap_whatever_ended_it(store, tmp_path):
    budget = CompositionBudget(assessment=CompositionBudget().assessment.model_copy(update={"tool_calls_limit": 3}))
    (tmp_path / "work").mkdir()
    run = asyncio.run(run_direct(fixture_case(), stages(), reviewed_runners(store, tmp_path / "work"), budget))
    assert run.attempts[-1].tool_cap_reached and not run.attempts[0].tool_cap_reached
