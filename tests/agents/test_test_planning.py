"""Exercise the read-only planner's contract, provenance and authority refusals through native SDK calls."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis.tools import source_tools
from corsair.agents.issue_analysis.tools.identification import identification_tools
from corsair.agents.test_planning import (
    PlanningDependencies, ReadyTestPlan, ReadyTestPlanDraft, TestPlanningInput, UnsupportedTestPlan,
    UnsupportedTestPlanDraft, create_test_planning_agent, planning_prompt,
)
from corsair.agents.test_planning.skills import SKILL_TEXT
from evals.test_planning.evaluate import (
    DATASETS, MANIFESTS, RETIRED, EvaluationBudget, dataset, evaluate, passed, plan_checks,
)


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def case(name="path_traversal_unguarded"):
    return next(c for c in dataset().cases if c.name == name)


def run(agent, inputs, **kwargs):
    return agent.run_sync(planning_prompt(inputs), deps=PlanningDependencies(inputs),
                          usage_limits=UsageLimits(request_limit=5, tool_calls_limit=4), **kwargs)


def responding(plan, *, reads=("documents.py", "test_existing.py"), offered=None):
    calls, offered = [], [] if offered is None else offered
    async def respond(messages, info):
        calls.append(1)
        assert "Plan exactly one benign control" in info.instructions and SKILL_TEXT.strip() in info.instructions
        offered.append([t.name for t in info.function_tools])
        if len(calls) <= len(reads):
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": reads[len(calls) - 1]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"plan": plan})])
    return FunctionModel(respond)


def reference():
    return json.loads(json.dumps(case().metadata.reference_plan))


def test_reference_plan_is_admitted_with_trusted_quotations_and_no_labels_in_prompt():
    c = case()
    result = run(create_test_planning_agent(responding(reference())), c.inputs)
    plan = result.output
    assert isinstance(plan, ReadyTestPlan) and all(plan_checks(c.inputs, plan, c.metadata).values())
    assert plan.security.source_references[0].quote.startswith("def read_document")
    assert (plan.security_expectation.failure_type, plan.security_expectation.safe_behavior) == ("AssertionError", "ValueError")
    prompt = planning_prompt(c.inputs)
    # Identification is sent without its quotation; contents arrive only through reads; oracle never sent.
    assert c.inputs.identification.target.source.quote not in prompt
    assert c.inputs.source_files[0].content not in prompt
    for label in ("path_traversal_unguarded", "reference_plan", "adversarial_markers", "test_security_rejects_outside_read"):
        assert label not in prompt


def test_reader_is_withdrawn_only_after_every_inventory_line_was_returned_in_this_run():
    c = case()
    offered = []
    run(create_test_planning_agent(responding(reference(), offered=offered)), c.inputs)
    # Two reads cover the two-file inventory, so a third request can only plan.
    assert offered == [["read_source"], ["read_source"], []]
    offered.clear()
    partial = reference() | {"citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}]}
    run(create_test_planning_agent(responding(partial, reads=("documents.py",), offered=offered)), c.inputs)
    assert offered == [["read_source"], ["read_source"]]


def test_unsupported_plan_needs_no_test_details_but_cannot_carry_them():
    c = case("no_baseline_test")
    draft = dict(c.metadata.reference_plan)
    result = run(create_test_planning_agent(responding(draft, reads=("documents.py",))), c.inputs)
    assert isinstance(result.output, UnsupportedTestPlan) and result.output.citations[0].quote
    with pytest.raises(ValidationError):
        UnsupportedTestPlanDraft.model_validate(draft | {"control": reference()["control"]})


def test_unsupported_plan_must_cite_listed_source():
    c = case("no_baseline_test")
    draft = dict(c.metadata.reference_plan) | {"citations": []}
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_planning_agent(responding(draft, reads=("documents.py",)), output_retries=0), c.inputs)


def test_prompt_keeps_structured_input_for_empty_inventory():
    data = case("implementation_absent").inputs.model_dump()
    data["source_files"] = []
    data["environment"]["baseline_test"] = None
    prompt = planning_prompt(TestPlanningInput.model_validate(data))
    assert "Saved source inventory (the only readable paths): (empty)" in prompt and '"scope":"component"' in prompt
    assert '"environment"' in prompt and '"identification"' in prompt


def test_unsupported_plan_may_be_uncited_when_no_listed_file_has_lines():
    data = case("implementation_absent").inputs.model_dump()
    data["source_files"] = [{"path": "test_existing.py", "content": ""}]
    inputs = TestPlanningInput.model_validate(data)
    draft = dict(case("implementation_absent").metadata.reference_plan) | {"citations": []}
    result = run(create_test_planning_agent(responding(draft, reads=()), output_retries=0), inputs)
    assert isinstance(result.output, UnsupportedTestPlan) and result.output.citations == ()


@pytest.mark.parametrize("change", [
    {"status": "missing_information", "target": None, "reason": "The report names no input."},
    {"scope": "application_path"},
])
def test_input_refuses_non_ready_or_rescoped_identification(change):
    data = case().inputs.model_dump()
    data["identification"] = data["identification"] | change
    with pytest.raises(ValidationError):
        TestPlanningInput.model_validate(data)


def test_input_refuses_baseline_test_absent_from_inventory():
    data = case().inputs.model_dump()
    data["source_files"] = data["source_files"][:1]
    with pytest.raises(ValidationError):
        TestPlanningInput.model_validate(data)


def test_input_refuses_approved_test_path_over_saved_source():
    data = case().inputs.model_dump()
    data["environment"]["approved_test_paths"] = ["documents.py"]
    with pytest.raises(ValidationError):
        TestPlanningInput.model_validate(data)


def edit(path, value):
    plan = reference()
    target = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return plan


@pytest.mark.parametrize("plan", [
    reference() | {"regression": reference()["control"]},                                      # third test
    edit(("security", "test_id"), "test_documents.py::test_benign_control"),                    # duplicate ids
    edit(("security", "test_path"), "tests/test_elsewhere.py"),                                  # unapproved path
    edit(("discovery_command",), ["python", "-m", "pytest", "--collect-only", "-q", "-k", "control"]),  # altered tokens
    edit(("citations",), []),                                                                    # uncited
    edit(("citations",), [{"path": "documents.py", "start_line": 1, "end_line": 9}]),            # unread range
    edit(("security", "source_references"), [{"path": "other.py", "start_line": 1, "end_line": 1}]),
    edit(("scope",), "application_path"),                                                        # scope expansion
    reference() | {"verdict": "fixed"},                                                          # verdict field
    edit(("security", "implementation_call"), "open(tmp_path / 'outside.txt')"),                 # not the target
    edit(("security_expectation", "safe_behavior"), "raises some error"),                        # untyped expectation
    {k: v for k, v in reference().items() if k != "security_expectation"},                       # missing expectation
    # SPEC-0040 typed witness admission
    edit(("security", "witness", "facility"), "audit_socket"),                                   # unlisted facility
    edit(("security", "witness", "effect"), "process_start"),                                    # effect not the facility kind
    edit(("security", "witness", "expectation"), "occurs"),                                      # security must expect absence
    edit(("control", "witness", "expectation"), "absent"),                                       # control must expect occurrence
    edit(("security", "witness", "subject"), "/tmp/outside.txt"),                                # absolute subject
    edit(("security", "witness", "subject"), "../outside.txt"),                                  # escapes scratch
    edit(("security", "witness", "subject"), "allowed/document.txt"),                            # same subject as control
    edit(("security", "witness", "subject"), "sentinel.txt"),                                    # input never aims at it
    edit(("security_expectation", "safe_behavior"), "no_outside_open"),                          # neither no_<effect> nor named
    {k: v for k, v in reference().items() if k != "control"} | {"control": {
        k: v for k, v in reference()["control"].items() if k != "witness"}},                     # missing witness
])
def test_finalizer_and_contract_refuse_invalid_plans(plan):
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_planning_agent(responding(plan), output_retries=0), case().inputs)


def test_contract_checks_environment_only_with_run_context_and_always_checks_ids():
    plan = edit(("security", "test_path"), "tests/test_elsewhere.py")
    ReadyTestPlanDraft.model_validate(plan)  # structure alone
    with pytest.raises(ValidationError):
        ReadyTestPlanDraft.model_validate(plan, context=case().inputs)
    with pytest.raises(ValidationError):
        ReadyTestPlanDraft.model_validate(edit(("security", "test_id"), "test_documents.py::test_benign_control"))


def test_previous_run_reads_do_not_authorize_citations():
    c = case()
    prior = run(create_test_planning_agent(responding(reference())), c.inputs)
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_planning_agent(responding(reference(), reads=()), output_retries=0), c.inputs,
            message_history=prior.all_messages())


def test_unknown_tool_refused_even_with_output_correction_budget():
    calls = []
    async def respond(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart("run_tests", {"command": "pytest"})])
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_planning_agent(FunctionModel(respond), output_retries=1), case().inputs)
    assert len(calls) == 1


def test_shared_source_move_keeps_names_and_durable_tool_identity():
    from corsair.agents import provider, source
    from corsair.agents.issue_analysis import contracts, provider as legacy_provider
    assert contracts.SourceRead is source.SourceRead and contracts.Contract is source.Contract
    assert legacy_provider.LocalModelConfig is provider.LocalModelConfig
    assert source_tools().id == "issue_analysis_source" and identification_tools().id == "issue_identification_source"


def test_curated_checks_reject_structurally_valid_wrong_plans():
    c = case()
    plan = run(create_test_planning_agent(responding(reference())), c.inputs).output
    swapped = plan.model_copy(update={"control": plan.security, "security": plan.control})
    assert not plan_checks(c.inputs, swapped, c.metadata)["adversarial_input"]
    unobserved = plan.model_copy(update={"security": plan.security.model_copy(update={"observable_witness": "The test fails"})})
    assert not plan_checks(c.inputs, unobserved, c.metadata)["witness"]
    assert not plan_checks(c.inputs, plan, c.metadata.model_copy(update={"status": "unsupported"}))["status"]


def test_native_evals_repeat_and_preserve_receipts(tmp_path):
    evidence = tmp_path / "attempt"
    report = asyncio.run(evaluate(evidence, EvaluationBudget()))
    assert passed(report) and len(report.cases) == 12 and len(report.case_groups()) == 6
    assert len(list(evidence.glob("attempt-*.json"))) == 12
    assert all(c.attributes["input_digest"] == c.inputs.input_digest for c in report.cases)
    assert all(c.metrics["requests"] == c.attributes["observed_requests"] for c in report.cases)
    assert report.experiment_metadata["weights_identity"] == "not_applicable"
    with pytest.raises(FileExistsError):
        asyncio.run(evaluate(evidence, EvaluationBudget()))


def test_native_task_failure_remains_in_denominator_and_receipt(tmp_path):
    async def unavailable(messages, info):
        raise RuntimeError("scripted provider failure")
    report = asyncio.run(evaluate(tmp_path / "failure", EvaluationBudget(repeat=1), model=FunctionModel(unavailable)))
    assert not passed(report) and len(report.failures) == 6
    assert len(list((tmp_path / "failure").glob("attempt-*.json"))) == 6


def test_native_provider_wire_carries_skill_schema_and_only_reader():
    import httpx2
    from corsair.agents.provider import LocalModelConfig, local_model
    c = case()
    bodies = []
    async def respond(request):
        body = json.loads(request.content); bodies.append(body)
        system = body["messages"][0]["content"]
        assert SKILL_TEXT.strip() in system and '"missing_capability"' in system and '"observable_witness"' in system
        assert '"quote"' not in system and '"verdict"' not in system
        reads = ("documents.py", "test_existing.py")
        offered = [t["function"]["name"] for t in body.get("tools", ())]
        assert offered == ["read_source"] if len(bodies) <= len(reads) else "read_source" not in offered
        if len(bodies) <= len(reads):
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"read{len(bodies)}", "type": "function",
                "function": {"name": "read_source", "arguments": json.dumps({"path": reads[len(bodies) - 1]})}}]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": json.dumps({"plan": reference()})}; finish = "stop"
        return httpx2.Response(200, json={"id": f"wire-{len(bodies)}", "object": "chat.completion", "created": 1, "model": "test-model",
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    async def exercise():
        async with local_model(LocalModelConfig(server="vllm", base_url="https://llm.example/v1", model_name="test-model"),
                               http_client=client) as model:
            with models.override_allow_model_requests(True):
                result = await create_test_planning_agent(model).run(planning_prompt(c.inputs), deps=PlanningDependencies(c.inputs))
            assert all(plan_checks(c.inputs, result.output, c.metadata).values())
    asyncio.run(exercise())
    assert client.is_closed and len(bodies) == 3


def test_scratch_check_rejects_fixtures_outside_the_scratch_location():
    c = case()
    plan = run(create_test_planning_agent(responding(reference())), c.inputs).output
    assert plan_checks(c.inputs, plan, c.metadata)["scratch"]
    for escape in ("Create tmp_path.parent / 'outside.txt' with a sentinel", "Write /tmp/outside.txt",
                   "Create ~/outside.txt", "Use the parent directory: Path(tmp_path).parent / 'x'"):
        security = plan.security.model_copy(update={"fixture_setup": (*plan.security.fixture_setup, escape)})
        assert not plan_checks(c.inputs, plan.model_copy(update={"security": security}), c.metadata)["scratch"], escape
    # The adversarial input itself may name a parent path; only fixture setup is confined.
    assert "../" in plan.security.input


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_heldout_cases_stay_disjoint_and_retired_sets_cannot_run_again(tmp_path, name):
    heldout = dataset(name)
    assert len(heldout.cases) == 6 and {c.metadata.status for c in heldout.cases} == {"ready", "unsupported"}
    for other in (dataset(n) for n in DATASETS if n != name):
        shown = {source.content for c in other.cases for source in c.inputs.source_files}
        assert not shown & {source.content for c in heldout.cases for source in c.inputs.source_files}
        assert not {c.inputs.identification.target.symbol for c in other.cases} & {
            c.inputs.identification.target.symbol for c in heldout.cases}
    if name not in RETIRED:
        assert all(c.inputs.environment.witness_facilities for c in heldout.cases)
        return
    with pytest.raises(ValueError, match="retired"):
        asyncio.run(evaluate(tmp_path / name, EvaluationBudget(), cases=name))
    assert not (tmp_path / name).exists()


def test_heldout_evaluation_refuses_a_changed_case(tmp_path, monkeypatch):
    import evals.test_planning.evaluate as module
    changed = tmp_path / "cases-heldout.yaml"
    changed.write_text((module.ROOT / module.DATASETS["heldout"]).read_text().replace("touch pwned", "touch owned", 1))
    monkeypatch.setitem(module.DATASETS, "heldout", str(changed))
    with pytest.raises(ValueError, match="frozen manifest"):
        module.check_manifest("heldout")


def test_typed_witness_admits_absence_identifier_and_refuses_without_listed_facilities():
    c = case()
    plan = edit(("security_expectation", "safe_behavior"), "no_file_open")
    assert isinstance(run(create_test_planning_agent(responding(plan)), c.inputs).output, ReadyTestPlan)
    data = c.inputs.model_dump()
    data["environment"]["witness_facilities"] = []
    with pytest.raises(UnexpectedModelBehavior):
        run(create_test_planning_agent(responding(reference()), output_retries=0), TestPlanningInput.model_validate(data))
