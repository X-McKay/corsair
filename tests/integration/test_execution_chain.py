"""Genuine ADK/Docker/Temporal v3 chain and replay with synthetic source."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer, Worker

from corsair.adapters.inference.execution import run_execution_auditor, run_execution_producer
from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source
from corsair.contracts.execution import ExecutionRequest, PlanAudit
from corsair.contracts.execution import TestPlan as Plan
from corsair.contracts.intake import Issue
from corsair.entrypoints.api import start_execution
from corsair.settings import Settings
from corsair.steps.execution import ExecutionActivities
from corsair.workflows.execution import ExecutionWorkflow
from tests.unit.adk import ScriptedLlm, text_response
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.docker, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


@pytest.mark.parametrize("accepted", [True, False])
async def test_recipe_free_chain_records_evidence_and_replays(
    temporal_server, monkeypatch, accepted, capsys
):
    scratch = Path(__file__).resolve().parents[2] / ".work"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="execution-chain-", dir=scratch) as directory:
        workspace = Path(directory)
        source = workspace / "repository"
        source.mkdir()
        (source / "reader.py").write_text("def answer():\n    return 42\n")
        fixed = workspace / "fixed"
        fixed.mkdir()
        (fixed / "reader.py").write_text("def answer():\n    return 43\n")
        settings = Settings(
            source_root=str(workspace),
            artifact_root=str(workspace / "artifacts"),
            task_queue=temporal_id("v3"),
            temporal_address=temporal_server.client.service_client.config.target_host,
            temporal_namespace=temporal_server.client.namespace,
        )
        store = ArtifactStore(settings.artifact_root)
        image = next(i for i in discover_images(settings).images if i.language == "python")
        request = ExecutionRequest(
            case_id="synthetic",
            issue=Issue(title="Inspect answer", locations=[{"path": "reader.py"}]),
            source=Source(path=str(source)),
            fixed_source=Source(path=str(fixed)),
            image=image,
            budget={"max_rounds": 1},
        )
        plan = Plan(
            hypothesis="Exercise the actual target function",
            revision=1,
            files=[
                {
                    "path": "check.py",
                    "content": (
                        "import sys; sys.path.insert(0,'/source'); from reader import answer; "
                        "assert answer()==42; print('checked')"
                    ),
                }
            ],
            commands=[{"argv": ["python", "/work/check.py"]}],
            locations=[{"path": "reader.py"}],
        )
        audit = (
            PlanAudit(decision="accepted")
            if accepted
            else PlanAudit(decision="rejected", reasons=["UNRELATED_TEST"])
        )

        async def producer(item, configuration, reader):
            model = ScriptedLlm(
                model="v3-producer", responses=[text_response(plan.model_dump_json())]
            )
            return await run_execution_producer(item, configuration, reader, model)

        async def auditor(item, proposal, configuration, reader):
            model = ScriptedLlm(
                model="v3-auditor", responses=[text_response(audit.model_dump_json())]
            )
            return await run_execution_auditor(item, proposal, configuration, reader, model)

        monkeypatch.setattr("corsair.steps.execution.run_execution_producer", producer)
        monkeypatch.setattr("corsair.steps.execution.run_execution_auditor", auditor)
        activities = ExecutionActivities(settings, store)
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[ExecutionWorkflow],
            activities=activities.registered(),
        ):
            identity = temporal_id("exec")
            if accepted:
                import json

                from corsair.entrypoints.cli import execute, parser

                request_path = workspace / "request.json"
                settings_path = workspace / "settings.json"
                request_path.write_text(request.model_dump_json())
                settings_path.write_text(settings.model_dump_json())
                assert (
                    await execute(
                        parser().parse_args(
                            [
                                "investigate",
                                "--direct",
                                str(request_path),
                                "--settings",
                                str(settings_path),
                                "--run-id",
                                identity,
                                "--wait",
                                "--format",
                                "json",
                            ]
                        )
                    )
                    == 0
                )
                emitted = json.loads(capsys.readouterr().out)
                assert emitted["outcome"] == "SUCCEEDED"
                assert emitted["security_assessment"] == "UNRESOLVED"
                from corsair.contracts.execution import ExecutionResult

                handle = temporal_server.client.get_workflow_handle(
                    identity, result_type=ExecutionResult
                )
                assert (
                    await execute(
                        parser().parse_args(
                            [
                                "inspect",
                                identity,
                                "--settings",
                                str(settings_path),
                                "--format",
                                "json",
                            ]
                        )
                    )
                    == 0
                )
                assert (
                    json.loads(capsys.readouterr().out)["result_artifact"]
                    == emitted["result_artifact"]
                )
            else:
                handle = await start_execution(
                    temporal_server.client, request, settings, run_id=identity
                )
            result = await handle.result()
        assert result.result_artifact == store.reconcile(f"execution-result.{result.run_id}")
        assert result.security_assessment == "UNRESOLVED"
        assert result.rounds[0].audit == audit
        if accepted:
            assert result.outcome == "SUCCEEDED", result
            original = result.rounds[0].observation
            repaired = result.rounds[0].fixed_observation
            assert original is not None and repaired is not None
            assert original.cleanup_confirmed and repaired.cleanup_confirmed
            assert repaired.outcome == "FAILED"
            assert original.plan_digest == repaired.plan_digest
            assert original.container_id != repaired.container_id
            assert result.usage.llm_calls == 2
        else:
            assert result.outcome == "INCOMPLETE"
            assert result.rounds[0].observation is None
        await Replayer(
            workflows=[ExecutionWorkflow], data_converter=pydantic_data_converter
        ).replay_workflow(await handle.fetch_history())
