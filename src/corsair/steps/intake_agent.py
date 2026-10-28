"""Trusted intake activities; all model, filesystem, network and Docker I/O lives here."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.resources import files

from temporalio import activity
from temporalio.exceptions import ApplicationError

from corsair.adapters.inference.intake_agent import run_intake
from corsair.adapters.sandboxing.images import discover_images, recheck_image
from corsair.adapters.sandboxing.inspection import DockerInspection, inspection_session
from corsair.adapters.scm.github import fetch_issue
from corsair.adapters.scm.local import iter_snapshot_files, snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.resources import intake_resources_digest, load_agent_spec, prompt_text
from corsair.contracts import digest
from corsair.contracts.intake_agent import (
    IntakeDecision,
    IntakeResult,
    IntakeStart,
    IssueReference,
    PreparedIntake,
)
from corsair.policies.intake_agent import classify_intake
from corsair.settings import Settings


@asynccontextmanager
async def intake_heartbeats() -> AsyncGenerator[None]:
    async def beat():
        while True:
            activity.heartbeat("intake preparation")
            await asyncio.sleep(2)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class IntakeActivities:
    def __init__(self, settings: Settings, store: ArtifactStore):
        self.settings = settings
        self.store = store

    @activity.defn(name="corsair.intake.prepare")
    async def prepare(self, start: IntakeStart) -> PreparedIntake:
        async with intake_heartbeats():
            return await self._prepare(start)

    async def _prepare(self, start: IntakeStart) -> PreparedIntake:
        request = start.request
        activity.heartbeat("admitting intake")
        if isinstance(request.input, IssueReference):
            reference = request.input
            if (
                f"{reference.owner}/{reference.repository}"
                not in self.settings.intake_github_repositories
            ):
                raise ApplicationError(
                    "repository not authorized", type="OUTSIDE_SCOPE_POLICY", non_retryable=True
                )
            try:
                payload = (await asyncio.to_thread(fetch_issue, reference)).model_dump(mode="json")
            except Exception:
                raise ApplicationError(
                    "issue fetch failed", type="ISSUE_FETCH_FAILED", non_retryable=True
                ) from None
        else:
            payload = request.input.payload
        input_artifact = self.store.put_json(
            {"input": request.input.model_dump(mode="json"), "payload": payload}
        )
        try:
            source = await asyncio.to_thread(
                snapshot_source, request.source, self.settings, self.store
            )
        except Exception:
            raise ApplicationError(
                "source admission failed", type="SOURCE_DENIED", non_retryable=True
            ) from None
        try:
            inventory = await asyncio.to_thread(discover_images, self.settings)
        except Exception:
            raise ApplicationError(
                "image inventory failed", type="IMAGE_CHECK_FAILED", non_retryable=True
            ) from None
        return PreparedIntake(
            run_id=start.run_id,
            request=request,
            source=source,
            input_artifact=input_artifact,
            payload=payload,
            inventory=inventory,
            config_digest=self.settings.identity,
        )

    @activity.defn(name="corsair.intake.analyze")
    async def analyze(self, prepared: PreparedIntake) -> IntakeResult:
        started = time.perf_counter()
        result = IntakeResult(
            run_id=prepared.run_id,
            source=prepared.source,
            input_artifact=prepared.input_artifact,
            inventory=prepared.inventory,
            identities={
                "config": prepared.config_digest,
                "request": digest(prepared.request),
                "source": prepared.source.sha256,
                "inventory": digest(prepared.inventory),
                "input": digest(
                    json.dumps(
                        prepared.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode()
                ),
                "model": digest(self.settings.models),
                "prompt": digest(prompt_text("intake")),
                "metadata": digest(load_agent_spec("intake")),
                "role_resources": intake_resources_digest(),
                "policy": digest(
                    files("corsair.policies").joinpath("intake_agent.py").read_bytes()
                ),
                "reader": digest(
                    files("corsair.adapters.sandboxing")
                    .joinpath("inspection_reader.py")
                    .read_bytes()
                ),
            },
            decision=IntakeDecision(status="error", error_code="INSPECTION_FAILED"),
        )
        if prepared.config_digest != self.settings.identity:
            return result

        async def heartbeat():
            while True:
                activity.heartbeat("intake episode")
                await asyncio.sleep(2)

        heartbeats = asyncio.create_task(heartbeat())
        try:
            from corsair.adapters.sandboxing.images import docker_client

            async with docker_client() as client:
                async with inspection_session(
                    DockerInspection(self.settings, self.store, prepared, client)
                ) as inspection:
                    window = prepared.episode_seconds or prepared.request.budget.max_elapsed_seconds
                    remaining = math.floor(window - (time.perf_counter() - started))
                    if remaining <= 0:
                        raise TimeoutError("intake setup exhausted its activity window")
                    bounded = prepared.model_copy(update={"episode_seconds": remaining})
                    output = await run_intake(bounded, self.settings, inspection)
                    result = result.model_copy(
                        update={
                            "usage": output.usage,
                            "proposal": output.proposal,
                            "inspection_reads": output.inspection_reads,
                        }
                    )
                    if inspection.image_id is not None:
                        result = result.model_copy(
                            update={
                                "identities": {
                                    **result.identities,
                                    "inspection_image": digest(inspection.image_id),
                                }
                            }
                        )
                result = result.model_copy(
                    update={
                        "usage": output.usage,
                        "proposal": output.proposal,
                        "inspection_reads": output.inspection_reads,
                    }
                )
                if output.error_code is not None or output.proposal is None:
                    return result.model_copy(
                        update={
                            "decision": IntakeDecision(
                                status="error", error_code=output.error_code or "OUTPUT_INVALID"
                            )
                        }
                    )
                proposal = output.proposal
                paths = {path for path, _ in iter_snapshot_files(prepared.source, self.store)}
                if any(location.path not in paths for location in proposal.locations):
                    return result.model_copy(
                        update={
                            "decision": IntakeDecision(status="error", error_code="OUTPUT_INVALID")
                        }
                    )
                image = next(
                    (
                        image
                        for image in prepared.inventory.images
                        if image.reference == proposal.suggested_image
                    ),
                    None,
                )
                decision = classify_intake(proposal, prepared.inventory)
                if image is not None and decision.classification == "in_scope_supported":
                    try:
                        available = await asyncio.to_thread(recheck_image, client, image)
                    except Exception:
                        return result.model_copy(
                            update={
                                "decision": IntakeDecision(
                                    status="error", error_code="IMAGE_CHECK_FAILED"
                                )
                            }
                        )
                    if not available:
                        decision = IntakeDecision(
                            status="completed",
                            classification="in_scope_not_supported",
                            reason_codes=["IMAGE_UNAVAILABLE"],
                            image_check="unavailable",
                        )
                return result.model_copy(update={"decision": decision})
        except asyncio.CancelledError:
            raise
        except Exception:
            return result.model_copy(
                update={"decision": IntakeDecision(status="error", error_code="INSPECTION_FAILED")}
            )
        finally:
            heartbeats.cancel()
            await asyncio.gather(heartbeats, return_exceptions=True)

    @activity.defn(name="corsair.intake.record")
    async def record(self, result: IntakeResult) -> IntakeResult:
        normalized = IntakeResult.model_validate(result.model_dump(exclude={"result_artifact"}))
        reference = await asyncio.to_thread(self.store.put_json, normalized)
        await asyncio.to_thread(self.store.commit, f"intake.{result.run_id}", reference)
        return normalized.model_copy(update={"result_artifact": reference})

    def registered(self) -> list:
        return [self.prepare, self.analyze, self.record]
