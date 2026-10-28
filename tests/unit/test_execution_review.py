"""Regression cases from independent review of v3 boundaries."""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from corsair.adapters.inference.execution import execution_resources_digest
from corsair.adapters.sandboxing.execution import DockerExecutor
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ArtifactRef, digest
from corsair.contracts.execution import ExecutionResult, ExecutionRound, PlanAudit
from corsair.settings import Settings
from corsair.steps.execution import ExecutionActivities
from tests.unit.execution import plan, round_input


def admitted(tmp_path):
    settings = Settings(artifact_root=str(tmp_path))
    store = ArtifactStore(tmp_path)
    prepared = round_input().prepared.model_copy(
        update={
            "config_digest": settings.identity,
            "resources_digest": execution_resources_digest(),
        }
    )
    artifact = store.put_json(prepared)
    return settings, store, prepared.model_copy(update={"artifact": artifact})


@pytest.mark.asyncio
async def test_uncertain_intent_is_recordable_without_claiming_execution(tmp_path):
    settings, store, prepared = admitted(tmp_path)
    executor = DockerExecutor(settings, store)
    proposal = plan()
    identity = "uncertain"
    intent = store.put_json(
        {
            "prepared": digest(prepared),
            "plan": digest(proposal),
            "fixed": False,
            "operation_id": identity,
        }
    )
    store.claim(f"execution-intent.{identity}", intent)
    observed = executor.execute(prepared, proposal, identity)
    assert observed.error == "OPERATION_UNCERTAIN"
    assert observed.artifact is not None and not observed.cleanup_confirmed
    result = ExecutionResult(
        run_id=prepared.run_id,
        case_id=prepared.request.case_id,
        prepared_artifact=prepared.artifact,
        identities={
            "request": prepared.request_digest,
            "source": prepared.source.sha256,
            "config": prepared.config_digest,
            "resources": prepared.resources_digest,
        },
        rounds=[
            ExecutionRound(
                plan=proposal, audit=PlanAudit(decision="accepted"), observation=observed
            )
        ],
    )
    saved = await ExecutionActivities(settings, store).record(result)
    assert saved.result_artifact is not None
    assert store.reconcile(f"execution.{identity}") is None


@pytest.mark.parametrize("existing", [True, False])
def test_unknown_container_identity_never_confirms_cleanup(tmp_path, monkeypatch, existing):
    settings, store, prepared = admitted(tmp_path)
    client = MagicMock()
    client.images.get.return_value.id = prepared.request.image.image_id
    client.containers.list.return_value = [MagicMock()] if existing else []
    client.containers.create.side_effect = TimeoutError("creation response lost")
    monkeypatch.setattr(
        "corsair.adapters.sandboxing.execution.docker.from_env", lambda **_kwargs: client
    )
    monkeypatch.setattr(
        "corsair.adapters.sandboxing.execution.iter_snapshot_files", lambda *_args: iter([])
    )
    observed = DockerExecutor(settings, store).execute(prepared, plan(), "unknown-create")
    assert observed.container_id is None
    assert not observed.cleanup_confirmed


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["source", "fixed_source"])
async def test_source_substitution_fails_before_adapters(tmp_path, monkeypatch, field):
    settings, store, prepared = admitted(tmp_path)
    changed = prepared.model_copy(update={field: ArtifactRef(sha256="9" * 64, size=0)})

    @asynccontextmanager
    async def forbidden():
        raise AssertionError("Docker/model boundary must not be reached")
        yield

    monkeypatch.setattr("corsair.steps.execution.docker_client", forbidden)
    item = round_input().model_copy(update={"prepared": changed})
    with pytest.raises(ValueError):
        await ExecutionActivities(settings, store).produce(item)


def test_aggregate_results_reject_temporal_oversize_envelopes():
    big = plan(files=[{"path": str(n), "content": "x" * 32768} for n in range(4)])
    with pytest.raises(ValidationError):
        ExecutionResult(
            run_id="oversize", case_id="case", rounds=[ExecutionRound(plan=big) for _ in range(16)]
        )


@pytest.mark.asyncio
async def test_image_drift_blocks_before_inspection_or_model(tmp_path, monkeypatch):
    settings, store, prepared = admitted(tmp_path)
    client = MagicMock()
    client.images.get.return_value.id = "sha256:" + "9" * 64

    @asynccontextmanager
    async def changed_client():
        yield client

    def forbidden(*_args):
        raise AssertionError("inspection/model must not be reached after image drift")

    monkeypatch.setattr("corsair.steps.execution.docker_client", changed_client)
    monkeypatch.setattr("corsair.steps.execution.DockerInspection", forbidden)
    with pytest.raises(ValueError):
        await ExecutionActivities(settings, store).produce(
            round_input().model_copy(update={"prepared": prepared})
        )


@pytest.mark.asyncio
async def test_auditor_can_read_more_than_four_grounded_files():
    from corsair.adapters.inference.execution import run_execution_auditor
    from tests.unit.adk import ScriptedLlm, text_response

    class Reader:
        def read(self, operation, relative=""):
            return (
                {"files": [f"f{n}.py" for n in range(5)]}
                if operation == "list"
                else {"content": f"# {relative}"}
            )

    proposal = plan(locations=[{"path": f"f{n}.py"} for n in range(5)])
    model = ScriptedLlm(
        model="audit-five", responses=[text_response('{"decision":"accepted","reasons":[]}')]
    )
    output = await run_execution_auditor(round_input(), proposal, Settings(), Reader(), model)
    assert output.audit == PlanAudit(decision="accepted")


@pytest.mark.asyncio
async def test_role_evaluation_writes_before_first_episode(tmp_path, monkeypatch):
    import asyncio
    import json
    from pathlib import Path

    from corsair.evaluation.execution import evaluate_roles

    async def interrupted(*_args):
        raise asyncio.CancelledError

    monkeypatch.setattr("corsair.evaluation.execution.run_execution_producer", interrupted)
    settings = tmp_path / "settings.json"
    settings.write_text(Settings(artifact_root=str(tmp_path / "artifacts")).model_dump_json())
    output = tmp_path / "report.json"
    with pytest.raises(asyncio.CancelledError):
        await evaluate_roles(Path("evals/datasets/execution-roles.json"), str(settings), output)
    assert output.exists()
    report = json.loads(output.read_bytes())
    assert report["complete"] is False and report["planned_attempts"] == 4
    assert report["completed_attempts"] == 0


@pytest.mark.asyncio
async def test_admitted_result_fits_actual_temporal_converter():
    from temporalio.contrib.pydantic import pydantic_data_converter

    from corsair.policies.execution import plan_fits_result

    big = plan(files=[{"path": str(n), "content": "x" * 32768} for n in range(4)])
    result = ExecutionResult(run_id="bounded", case_id="case")
    for _ in range(5):
        assert plan_fits_result(result, big)
        result = result.model_copy(update={"rounds": [*result.rounds, ExecutionRound(plan=big)]})
    assert not plan_fits_result(result, big)
    payloads = await pydantic_data_converter.encode([result])
    assert len(payloads[0].data) < 1_000_000
