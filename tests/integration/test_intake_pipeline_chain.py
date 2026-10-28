"""Actual main evidence chain behind agentic intake; no verdict oracles reach agents."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer, Worker

from corsair.adapters.inference.adk import AdkInference
from corsair.adapters.inference.intake_agent import run_intake
from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import InvestigationResult
from corsair.contracts.intake_agent import (
    ImageCandidate,
    IntakeProposal,
    IntakeRequest,
    IntakeResult,
    JsonIssueInput,
)
from corsair.contracts.intake_pipeline import IntakeInvestigationRequest, IntakeInvestigationResult
from corsair.entrypoints.api import start_intake_investigation
from corsair.entrypoints.cli import execute, parser
from corsair.entrypoints.requests import load_investigation_request
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.steps.intake_agent import IntakeActivities
from corsair.steps.intake_handoff import IntakePipelineActivities
from corsair.workflows.intake import IntakeWorkflow
from corsair.workflows.intake_pipeline import IntakeInvestigationWorkflow
from corsair.workflows.investigation import InvestigationWorkflow
from tests.integration.test_chain import ReferenceModel
from tests.unit.adk import ScriptedLlm, text_response, tool_response
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.docker, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


@pytest.mark.parametrize(
    "case",
    ["supported", "outside", "unsupported", "binding_missing", "source_changed", "image_missing"],
)
async def test_main_pipeline_uses_committed_intake_image(
    temporal_server, monkeypatch, case, capsys
):
    root = Path(__file__).resolve().parents[2]
    scratch = root / ".work"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="intake-main-chain-", dir=scratch) as directory:
        workspace = Path(directory)
        original = load_investigation_request(root / "evals/fixtures/case01/request.json")
        source = workspace / "source"
        shutil.copytree(original.case.source.path, source)
        assert original.case.fixed_source is not None
        fixed = workspace / "comparison"
        shutil.copytree(original.case.fixed_source.path, fixed)
        binding = original.case.model_copy(
            update={
                "source": original.case.source.model_copy(update={"path": str(source)}),
                "fixed_source": original.case.fixed_source.model_copy(update={"path": str(fixed)}),
            }
        )
        settings = Settings(
            source_root=directory,
            artifact_root=str(workspace / "artifacts"),
            image="corsair-python:pre-intake-main-20261028",
            images={"python.secret_disclosure/1": "corsair-python:pre-intake-main-20261028"},
            intake_images=[
                ImageCandidate(
                    reference="corsair-python:intake-main-20261028",
                    language="python",
                    execution_mode="callable",
                )
            ],
            task_queue=temporal_id("intake-main"),
            temporal_address=temporal_server.client.service_client.config.target_host,
            temporal_namespace=temporal_server.client.namespace,
        )
        inventory = discover_images(settings)
        selected = next(
            i for i in inventory.images if i.reference == "corsair-python:intake-main-20261028"
        )
        assert selected.image_id != next(
            i.image_id for i in inventory.images if i.reference == settings.image
        )
        store = ArtifactStore(settings.artifact_root)
        payload = {
            "title": binding.finding.title,
            "description": binding.finding.description,
            "locations": [{"path": "target.py"}],
        }
        intake_request = IntakeRequest(
            input=JsonIssueInput(payload=payload),
            source=binding.source,
            budget=original.budget.model_copy(update={"max_rounds": 1}),
        )
        request = IntakeInvestigationRequest(
            case_id=binding.case_id,
            intake=intake_request,
            binding=None if case == "binding_missing" else binding,
        )
        proposal = IntakeProposal(
            issue=payload,
            scope="out_of_scope" if case == "outside" else "in_scope",
            surface="function",
            language="python",
            execution_mode="callable",
            requirements=["network_access"] if case == "unsupported" else [],
            suggested_image=selected.reference,
            reason_codes=[],
            locations=[{"path": "target.py"}],
        )

        async def intake(prepared, configuration, reader):
            model = ScriptedLlm(
                model="native-intake-main",
                responses=[
                    tool_response(
                        "compare_images",
                        {"language": "python", "execution_mode": "callable", "requirements": []},
                    ),
                    text_response(proposal.model_dump_json()),
                ],
            )
            return await run_intake(prepared, configuration, reader, model)

        monkeypatch.setattr("corsair.steps.intake_agent.run_intake", intake)
        intake_activities = IntakeActivities(settings, store)
        original_record = intake_activities.record

        @activity.defn(name="corsair.intake.record")
        async def record(item: IntakeResult) -> IntakeResult:
            result = await original_record(item)
            if case == "source_changed":
                (source / "target.py").write_text(
                    'raise RuntimeError("changed source must not run")\n'
                )
            if case == "image_missing":
                monkeypatch.setattr(
                    "corsair.steps.intake_handoff.discover_images",
                    lambda _: type(inventory)(images=[]),
                )
            return result

        monkeypatch.setattr(intake_activities, "record", record)
        model = ReferenceModel(model="retained-main-native-chain")
        main = Activities(
            settings,
            store=store,
            inference=AdkInference(settings, store, model),
            sources=LocalSourceSnapshots(settings, store),
            sandbox=DockerSandbox(settings, store=store),
        )
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[IntakeInvestigationWorkflow, IntakeWorkflow, InvestigationWorkflow],
            activities=[
                *intake_activities.registered(),
                *main.registered(),
                *IntakePipelineActivities(store).registered(),
            ],
        ):
            identity = temporal_id("intake-main-parent")
            if case == "supported":
                binding_path = workspace / "binding.json"
                binding_path.write_text(
                    original.model_copy(
                        update={"case": binding, "budget": intake_request.budget}
                    ).model_dump_json()
                )
                input_path = workspace / "issue.json"
                input_path.write_text(json.dumps(payload))
                settings_path = workspace / "settings.json"
                settings_path.write_text(settings.model_dump_json())
                assert (
                    await execute(
                        parser().parse_args(
                            [
                                "investigate",
                                str(binding_path),
                                "--json",
                                str(input_path),
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
                assert emitted["status"] == "investigation_finished"
                handle = temporal_server.client.get_workflow_handle(
                    identity, result_type=IntakeInvestigationResult
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
                handle = await start_intake_investigation(
                    temporal_server.client, request, settings, run_id=identity
                )
            result = await handle.result()
            assert result.result_artifact == store.reconcile(
                f"intake-investigation.{result.run_id}"
            )
            assert result.intake is not None
            if case == "supported":
                assert result.status == "investigation_finished"
                assert result.investigation_execution_status == "COMPLETED", result
                assert result.investigation_result is not None
                child = InvestigationResult.model_validate(
                    store.get_json(result.investigation_result)
                )
                assert child.manifest is not None
                assert child.verdict is not None
                assert child.rounds[0].observation is not None
                assert child.manifest.image_reference == selected.reference
                assert (
                    child.manifest.image_id == result.intake.decision.image_id == selected.image_id
                )
                assert child.verdict.value == "EXPLOIT_DEMONSTRATED"
                assert child.rounds[0].observation.cleanup_confirmed
                assert child.rounds[0].observation.control is not None
                assert len(model.requests) == 3
                assert result.usage.llm_calls == 5
            else:
                assert model.requests == []
                if case in {"outside", "unsupported", "binding_missing"}:
                    assert result.status == "stopped" and result.investigation_run_id is None
                else:
                    assert result.investigation_execution_status != "COMPLETED"
            history = await handle.fetch_history()
        await Replayer(
            workflows=[IntakeInvestigationWorkflow], data_converter=pydantic_data_converter
        ).replay_workflow(history)
