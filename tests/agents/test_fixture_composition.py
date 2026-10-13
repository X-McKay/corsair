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
from corsair.composition.direct import UNOBSERVED, StageModels, run_direct
from corsair.composition.evidence import freeze, observation_plan, run_evidence
from corsair.core.disposition import AssessmentEvidence, Disposition, Witness, assess
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
    assert run.limitations == UNOBSERVED + tuple(f"{revision} witness not admitted: no witness was requested or "
                                                 "captured for this run" for revision in ("baseline", "candidate"))

    # Agents never see which variant is which.
    assert not any(label in prompt for prompt in prompts(run) for label in ("vulnerable", "fixed"))


def test_an_over_claim_is_rejected_and_the_gate_verdict_stands(store, tmp_path):
    run = compose(store, tmp_path, witnessed=False,
                  assessment=scripted_assessment(finding="reproduced", fix="verified"))
    admission = run.assessment.admission
    assert not admission.admitted and admission.disposition == run.gate.permitted
    assert admission.rejections == ("finding reproduced exceeds permitted inconclusive",
                                    "fix verified exceeds permitted not_verified")


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
    assert gate.limitations == () and run.limitations == UNOBSERVED
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


def test_a_target_the_probe_cannot_address_runs_without_a_witness(store, tmp_path, monkeypatch):
    """An identified symbol the probe refuses never crashes the chain; the runs proceed unwitnessed and say why."""
    from corsair.composition import direct

    def refused(identification):
        raise ValueError("Witness target needs a plain qualified symbol")
    monkeypatch.setattr(direct, "witness_request", refused)
    run = compose(store, tmp_path)
    assert run.stopped_at is None and all(e.observed.witness is None for e in run.executions)
    assert run.gate.permitted == Disposition(execution="completed", finding="inconclusive", fix="not_verified")
    assert "no witness requested: Witness target needs a plain qualified symbol" in run.limitations
    assert not any("witness (kind witness" in prompt for prompt in prompts(run))
