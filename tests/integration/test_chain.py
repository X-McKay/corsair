"""Real native execution and durability with scripted native ADK responses.

This is not a live-model accuracy baseline: the scripted model supplies a frozen
proposal, while actual ADK, activities, source snapshots, containers and policy execute.
"""

import json
import logging
import os
from pathlib import Path

import pytest
from google.adk.models import BaseLlm
from pydantic import Field
from temporalio.worker import Worker

from corsair.contracts import Disposition, FixStatus
from corsair.observability.logging import LifecycleLoggingInterceptor
from corsair.runtime.artifacts import ArtifactStore
from corsair.runtime.requests import load_investigation_request
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.workflows.investigation import InvestigationWorkflow
from tests.fixtures.adk import text_response, tool_response
from tests.fixtures.temporal import temporal_id


class ReferenceModel(BaseLlm):
    requests: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        del stream  # Native ADK interface; this labelled fixture returns one complete response.
        self.requests.append(llm_request)
        if llm_request.tools_dict:
            user_message = next(
                content for content in llm_request.contents if content.role == "user"
            )
            packet = json.loads(user_message.parts[0].text.split("\n", maxsplit=1)[1])
            revision = packet["round"]["revision"]
            yield tool_response(
                "submit",
                {
                    "control_payload": "hello.txt",
                    "exploit_payload": "../private/secret.txt",
                    "hypothesis": "Caller-controlled path joins the root without containment.",
                    "plan": {
                        "revision": revision,
                        "parent_revision": packet["round"]["parent_revision"],
                        "objective": "Exercise the reported component file-access boundary",
                        "next_steps": ["Submit benign and path-traversal payloads"],
                        "reason": "The reported callable is the production seam",
                    },
                },
            )
        else:
            yield text_response(
                json.dumps(
                    {
                        "decision": "ACCEPT",
                        "rule": "source-grounded-fixture",
                        "reason": "The paired payloads exercise the configured file-access seam",
                    }
                )
            )


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
async def test_native_adk_docker_temporal_chain_and_fix(temporal_server, tmp_path, caplog):
    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for real native execution")
    root = Path(__file__).resolve().parents[2]
    request = load_investigation_request(root / "evals/fixtures/case01/request.json")
    store = ArtifactStore(tmp_path / "artifacts")
    settings = Settings(source_root=str(root), artifact_root=str(store.root))
    model = ReferenceModel(model="scripted-reference")
    activities = Activities(settings, model_override=model)
    caplog.set_level(logging.INFO, logger="corsair")
    queue, identity = temporal_id("native-queue"), temporal_id("native-run")
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow],
        activities=activities.registered(),
        interceptors=[LifecycleLoggingInterceptor()],
    ):
        result = await temporal_server.client.execute_workflow(
            InvestigationWorkflow.run,
            request,
            id=identity,
            task_queue=queue,
        )
    assert result.disposition == Disposition.SUPPORTED, result.model_dump_json(indent=2)
    assert result.fix_status == FixStatus.DEMONSTRATION_BLOCKED
    assert result.execution_status.value == "COMPLETED"
    assert result.rounds[0].observation.cleanup_confirmed
    assert result.fix_observation.cleanup_confirmed
    assert result.result_artifact and store.reconcile(f"result.{identity}")
    assert len(model.requests) == 2
    assert result.manifest.capabilities["producer"]["tools"] == [
        "read_file",
        "list_files",
        "submit",
    ]
    from corsair.observability.evaluation import Oracle, score

    relabelled = result.model_copy(update={"case_id": "different-case"})
    row = score(relabelled, Oracle(acceptable=[Disposition.SUPPORTED]), store)
    assert row["status"] == "fail"
    assert row["evidence_valid"] is False
    assert row["fix_correct"] is False
    receipts = [record for record in caplog.records if record.name == "corsair"]
    assert any(record.message == "activity.started" for record in receipts)
    completed = [record for record in receipts if record.message == "activity.completed"]
    assert any(record.fields["activity"] == "corsair.produce" for record in completed)
    assert any(record.fields["cleanup_confirmed"] for record in completed)
    assert all(
        "payload" not in record.fields and "prompt" not in record.fields for record in receipts
    )


@pytest.mark.docker
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="module")
async def test_cli_frozen_batch_uses_native_chain_and_external_oracles(
    temporal_server, tmp_path, capsys
):
    from corsair.cli import execute, parser
    from corsair.workflows.evaluation import EvaluationWorkflow

    if os.environ.get("CORSAIR_TEST_DOCKER") != "1":
        pytest.skip("set CORSAIR_TEST_DOCKER=1 for native batch execution")
    root = Path(__file__).resolve().parents[2]
    queue = temporal_id("batch-queue")
    settings = Settings(
        source_root=str(root),
        artifact_root=str(tmp_path / "artifacts"),
        task_queue=queue,
        temporal_address=temporal_server.client.service_client.config.target_host,
    )
    config = tmp_path / "settings.json"
    config.write_text(settings.model_dump_json())
    report = tmp_path / "report.json"
    activities = Activities(settings, model_override=ReferenceModel(model="scripted-batch"))
    args = parser().parse_args(
        [
            "eval",
            str(root / "evals/datasets/dev.json"),
            "--settings",
            str(config),
            "--run-id",
            temporal_id("native-batch"),
            "--concurrency",
            "2",
            "--output",
            str(report),
        ]
    )
    async with Worker(
        temporal_server.client,
        task_queue=queue,
        workflows=[InvestigationWorkflow, EvaluationWorkflow],
        activities=activities.registered(),
    ):
        assert await execute(args) == 0
        assert json.loads(capsys.readouterr().out)["summary"]["attempts"] == 3
        inspection = ["inspect", args.run_id, "--online", "--settings", str(config)]
        assert await execute(parser().parse_args(inspection)) == 0
        assert json.loads(capsys.readouterr().out) == {"completed": 3, "total": 3}
        assert await execute(parser().parse_args([*inspection, "--watch"])) == 0
        children = json.loads(capsys.readouterr().out)
        assert len(children) == 3
        child_inspection = ["inspect", children[0]["run_id"], "--online", "--settings", str(config)]
        assert await execute(parser().parse_args(child_inspection)) == 0
        assert json.loads(capsys.readouterr().out)["phase"] == "complete"
        assert await execute(parser().parse_args([*child_inspection, "--watch"])) == 0
        assert json.loads(capsys.readouterr().out)["disposition"] == "SUPPORTED"
    rows = json.loads(report.read_text())["rows"]
    assert {row["case_id"]: row["disposition"] for row in rows} == {
        "case01": "SUPPORTED",
        "case02": "INCONCLUSIVE",
        "case03": "CONDITIONAL",
    }
    assert all(row["status"] == "pass" for row in rows)
