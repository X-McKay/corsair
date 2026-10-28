"""Real intake ADK/Docker/Temporal composition with explicit model cohorts."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from temporalio.worker import Worker

from corsair.adapters.inference.intake_agent import run_intake
from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source
from corsair.contracts.intake_agent import IntakeRequest, JsonIssueInput
from corsair.entrypoints.api import start_intake
from corsair.settings import Settings, load_settings
from corsair.steps.intake_agent import IntakeActivities
from corsair.workflows.intake import IntakeWorkflow
from tests.unit.adk import ScriptedLlm, text_response, tool_response
from tests.workflow.temporal import temporal_id

pytestmark = [pytest.mark.docker, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]


async def _run_chain(temporal_server, monkeypatch, *, live):
    root = Path(__file__).resolve().parents[2]
    scratch = root / ".work"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="intake-chain-", dir=scratch) as directory:
        workspace = Path(directory)
        repository = workspace / "repository"
        repository.mkdir()
        (repository / "reader.py").write_text(
            "from pathlib import Path\n\n"
            "def read_file(root, path):\n    return (Path(root) / path).read_text()\n"
        )
        configured = load_settings(os.environ["CORSAIR_LIVE_CONFIG"]) if live else Settings()
        settings = configured.model_copy(
            update={
                "source_root": str(workspace),
                "artifact_root": str(workspace / "artifacts"),
                "task_queue": temporal_id("intake-chain"),
            }
        )
        store = ArtifactStore(settings.artifact_root)
        source = Source(path=str(repository))
        snapshot = snapshot_source(source, settings, store)
        source = source.model_copy(update={"expected_digest": snapshot.sha256})
        payload = {
            "title": "Traversal",
            "description": "read_file accepts an unchecked path and may disclose private files",
            "locations": [{"path": "reader.py"}],
        }
        request = IntakeRequest(input=JsonIssueInput(payload=payload), source=source)
        if not live:
            model = ScriptedLlm(
                model="intake-native-chain",
                responses=[
                    tool_response("read_file", {"path": "reader.py"}),
                    text_response(
                        json.dumps(
                            {
                                "issue": payload,
                                "scope": "in_scope",
                                "surface": "function",
                                "language": "python",
                                "execution_mode": "callable",
                                "requirements": [],
                                "suggested_image": settings.image,
                                "reason_codes": [],
                                "locations": [{"path": "reader.py"}],
                            }
                        )
                    ),
                ],
            )

            async def native(prepared, configuration, reader):
                return await run_intake(prepared, configuration, reader, model)

            monkeypatch.setattr("corsair.steps.intake_agent.run_intake", native)
        activities = IntakeActivities(settings, store)
        async with Worker(
            temporal_server.client,
            task_queue=settings.task_queue,
            workflows=[IntakeWorkflow],
            activities=activities.registered(),
        ):
            identity = temporal_id("intake-chain")
            handle = await start_intake(temporal_server.client, request, settings, run_id=identity)
            result = await handle.result()
        assert result.decision.status == "completed", result.decision
        assert result.proposal is not None and result.result_artifact is not None
        assert store.reconcile(f"intake.{identity}") == result.result_artifact
        assert result.proposal.suggested_image in {
            image.reference for image in result.inventory.images
        } | {None}
        if not live:
            assert result.decision.classification == "in_scope_supported"


async def test_native_intake_chain_records_supported_image(temporal_server, monkeypatch):
    await _run_chain(temporal_server, monkeypatch, live=False)


@pytest.mark.live
async def test_live_intake_chain_records_categorical_result(temporal_server, monkeypatch):
    if not os.environ.get("CORSAIR_LIVE_CONFIG"):
        pytest.skip("explicit intake live settings required")
    await _run_chain(temporal_server, monkeypatch, live=True)
