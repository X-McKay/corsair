"""Real ADK, Temporal and Docker intake-to-execution wiring; synthetic cases only."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer, Worker

from corsair.adapters.inference.adk import run_intake
from corsair.adapters.inference.execution import run_execution_auditor, run_execution_producer
from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source
from corsair.contracts.execution import ExecutionResult, PlanAudit
from corsair.contracts.execution import TestPlan as Plan
from corsair.contracts.intake import IntakeProposal, IntakeRequest, IntakeResult, JsonIssueInput
from corsair.contracts.pipeline import IssueInvestigationRequest, IssueInvestigationResult
from corsair.entrypoints.api import start_issue_investigation
from corsair.entrypoints.cli import execute, parser
from corsair.settings import Settings, load_settings
from corsair.steps.execution import ExecutionActivities
from corsair.steps.intake import IntakeActivities
from corsair.steps.pipeline import PipelineActivities
from corsair.workflows.execution import ExecutionWorkflow
from corsair.workflows.intake import IntakeWorkflow
from corsair.workflows.pipeline import IssueInvestigationWorkflow
from tests.unit.adk import ScriptedLlm, text_response, tool_response
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.docker, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


@pytest.mark.parametrize(
    "case", ["supported", "unsupported", "outside", "source_changed", "image_missing"]
)
async def test_intake_gate_and_selected_nondefault_image(
    temporal_server, monkeypatch, capsys, case
):
    root = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix="pipeline-", dir=root / ".work") as directory:
        workspace = Path(directory)
        source = workspace / "repository"
        source.mkdir()
        target = source / "math.mjs"
        target.write_text("export function increment(x) { return x + 1; }\n")
        settings = Settings(
            source_root=directory,
            artifact_root=str(workspace / "artifacts"),
            node_image=os.environ.get("CORSAIR_TEST_NODE_IMAGE", "corsair-node:0.1"),
            task_queue=temporal_id("pipeline-chain"),
            temporal_address=temporal_server.client.service_client.config.target_host,
            temporal_namespace=temporal_server.client.namespace,
        )
        images = discover_images(settings).images
        image = next(i for i in images if i.language == "javascript")
        assert image.image_id != next(i.image_id for i in images if i.language == "python")
        store = ArtifactStore(settings.artifact_root)
        issue = {
            "title": "Check increment",
            "description": "Inspect increment behavior",
            "locations": [{"path": "math.mjs"}],
        }
        proposal = IntakeProposal(
            issue=issue,
            scope="out_of_scope" if case == "outside" else "in_scope",
            surface="function",
            language="javascript",
            execution_mode="callable",
            reason_codes=[],
            requirements=["network_access"] if case == "unsupported" else [],
            suggested_image=image.reference,
            locations=[{"path": "math.mjs"}],
        )
        request = IssueInvestigationRequest(
            case_id="synthetic",
            intake=IntakeRequest(
                input=JsonIssueInput(payload=issue),
                source=Source(path=str(source)),
                budget={"max_rounds": 1},
            ),
        )
        producers = []

        async def intake(prepared, configuration, reader):
            model = ScriptedLlm(
                model="pipeline-intake",
                responses=[
                    tool_response(
                        "compare_images",
                        {
                            "language": "javascript",
                            "execution_mode": "callable",
                            "requirements": [],
                        },
                    ),
                    text_response(proposal.model_dump_json()),
                ],
            )
            return await run_intake(prepared, configuration, reader, model)

        async def producer(item, configuration, reader):
            producers.append(item)
            assert item.prepared.request.image == image
            plan = Plan(
                hypothesis="Exercise increment",
                revision=1,
                files=[
                    {
                        "path": "test.mjs",
                        "content": (
                            "import {increment} from '/source/math.mjs'; "
                            "if(increment(1)!==2) throw Error('failed');"
                        ),
                    }
                ],
                commands=[{"argv": ["node", "/work/test.mjs"]}],
                locations=[{"path": "math.mjs"}],
            )
            return await run_execution_producer(
                item,
                configuration,
                reader,
                ScriptedLlm(
                    model="pipeline-producer", responses=[text_response(plan.model_dump_json())]
                ),
            )

        async def auditor(item, plan, configuration, reader):
            return await run_execution_auditor(
                item,
                plan,
                configuration,
                reader,
                ScriptedLlm(
                    model="pipeline-auditor",
                    responses=[text_response(PlanAudit(decision="accepted").model_dump_json())],
                ),
            )

        monkeypatch.setattr("corsair.steps.intake.run_intake", intake)
        monkeypatch.setattr("corsair.steps.execution.run_execution_producer", producer)
        monkeypatch.setattr("corsair.steps.execution.run_execution_auditor", auditor)
        intake_activities = IntakeActivities(settings, store)
        original_record = intake_activities.record

        @activity.defn(name="corsair.intake.record")
        async def record(item: IntakeResult) -> IntakeResult:
            result = await original_record(item)
            if case == "source_changed":
                target.write_text("export function increment(x) { return x - 1; }\n")
            elif case == "image_missing":
                monkeypatch.setattr(
                    "corsair.steps.execution.discover_images",
                    lambda _: type(result.inventory)(images=[]),
                )
            return result

        monkeypatch.setattr(intake_activities, "record", record)
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[IssueInvestigationWorkflow, IntakeWorkflow, ExecutionWorkflow],
            activities=[
                *intake_activities.registered(),
                *ExecutionActivities(settings, store).registered(),
                *PipelineActivities(store).registered(),
            ],
        ):
            identity = temporal_id("pipeline-run")
            settings_path = workspace / "settings.json"
            settings_path.write_text(settings.model_dump_json())
            if case == "supported":
                path = workspace / "issue.json"
                path.write_text(json.dumps(issue))
                code = await execute(
                    parser().parse_args(
                        [
                            "investigate",
                            "--json",
                            str(path),
                            "--source",
                            str(source),
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
                assert code == 0
                assert json.loads(capsys.readouterr().out)["execution_outcome"] == "SUCCEEDED"
                handle = temporal_server.client.get_workflow_handle(
                    identity, result_type=IssueInvestigationResult
                )
            else:
                handle = await start_issue_investigation(
                    temporal_server.client, request, settings, run_id=identity
                )
            result = await handle.result()
            assert result.result_artifact == store.reconcile(f"issue-investigation.{identity}")
            assert result.security_assessment == "UNRESOLVED"
            assert result.intake is not None
            if case == "supported":
                assert len(producers) == 1
                assert result.execution_result is not None
                assert result.result_artifact is not None
                child = ExecutionResult.model_validate(store.get_json(result.execution_result))
                observation = child.rounds[0].observation
                assert observation is not None and observation.cleanup_confirmed
                assert observation.image_id == result.intake.decision.image_id == image.image_id
                assert producers[0].prepared.source == result.intake.source
                await execute(
                    parser().parse_args(
                        ["inspect", identity, "--settings", str(settings_path), "--format", "json"]
                    )
                )
                assert json.loads(capsys.readouterr().out)[
                    "result_artifact"
                ] == result.result_artifact.model_dump(mode="json")
            else:
                assert producers == []
                if case in {"outside", "unsupported"}:
                    assert result.status == "stopped" and result.execution_run_id is None
                else:
                    assert result.execution_outcome == "ERROR"
            history = await handle.fetch_history()
        await Replayer(
            workflows=[IssueInvestigationWorkflow], data_converter=pydantic_data_converter
        ).replay_workflow(history)


@pytest.mark.live
async def test_live_intake_gated_attempt(temporal_server):
    configured = os.environ.get("CORSAIR_LIVE_CONFIG")
    if configured is None:
        pytest.skip("explicit live configuration required")
    root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (root / "evals/fixtures/execution-roles/producer-traversal/input.json").read_bytes()
    )
    with TemporaryDirectory(prefix="pipeline-live-", dir=root / ".work") as directory:
        source = Path(directory) / "repository"
        source.mkdir()
        for name, content in payload["source"].items():
            (source / name).write_text(content)
        settings = load_settings(configured).model_copy(
            update={
                "source_root": directory,
                "task_queue": temporal_id("live-pipeline"),
                "temporal_address": temporal_server.client.service_client.config.target_host,
                "temporal_namespace": temporal_server.client.namespace,
            }
        )
        store = ArtifactStore(settings.artifact_root)
        request = IssueInvestigationRequest(
            case_id="synthetic-traversal",
            intake=IntakeRequest(
                input=JsonIssueInput(payload=payload["issue"]),
                source=Source(path=str(source)),
                budget={"max_rounds": 1, "episode_llm_calls": 2, "max_elapsed_seconds": 180},
            ),
        )
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[IssueInvestigationWorkflow, IntakeWorkflow, ExecutionWorkflow],
            activities=[
                *IntakeActivities(settings, store).registered(),
                *ExecutionActivities(settings, store).registered(),
                *PipelineActivities(store).registered(),
            ],
        ):
            handle = await start_issue_investigation(
                temporal_server.client, request, settings, run_id=temporal_id("live-pipeline")
            )
            result = await handle.result()
        assert result.result_artifact == store.reconcile(f"issue-investigation.{result.run_id}")
        assert result.security_assessment == "UNRESOLVED"
        (Path(settings.artifact_root) / "pipeline-live-result.json").write_text(
            result.model_dump_json(indent=2)
        )
