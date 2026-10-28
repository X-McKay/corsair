"""Ordinary activities own recipe-free admission, native agents and sandbox I/O."""

from __future__ import annotations

import asyncio

from temporalio import activity

from corsair.adapters.inference.execution import (
    execution_resources_digest,
    run_execution_auditor,
    run_execution_producer,
)
from corsair.adapters.sandboxing.execution import DockerExecutor
from corsair.adapters.sandboxing.images import discover_images, docker_client, recheck_image
from corsair.adapters.sandboxing.inspection import DockerInspection, inspection_session
from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import digest
from corsair.contracts.execution import (
    AuditEpisodeInput,
    ExecutePlanInput,
    ExecutionEpisode,
    ExecutionResult,
    ExecutionRoundInput,
    ExecutionStart,
    PreparedExecution,
    ProcessObservation,
)
from corsair.contracts.intake import (
    ImageInventory,
    IntakeRequest,
    JsonIssueInput,
    PreparedIntake,
)
from corsair.policies.execution import admit_execution_image
from corsair.ports.execution import ExecutionPort
from corsair.settings import Settings
from corsair.steps.intake import intake_heartbeats


def validate_execution_identity(
    prepared: PreparedExecution, settings: Settings, store: ArtifactStore
) -> None:
    if prepared.artifact is None:
        raise ValueError("missing immutable admission artifact")
    admitted = PreparedExecution.model_validate(store.get_json(prepared.artifact))
    if admitted != prepared.model_copy(update={"artifact": None}):
        raise ValueError("admitted source/request identity changed")
    if (
        prepared.config_digest != settings.identity
        or prepared.request_digest != digest(prepared.request)
        or prepared.resources_digest != execution_resources_digest()
    ):
        raise ValueError("admitted execution identity changed")


def inspection_input(item: ExecutionRoundInput, role: str) -> PreparedIntake:
    prepared = item.prepared
    return PreparedIntake(
        run_id=f"{prepared.run_id}-{role}-{item.revision}",
        request=IntakeRequest(
            input=JsonIssueInput(payload=prepared.request.issue.model_dump(mode="json")),
            source=prepared.request.source,
            budget=prepared.request.budget,
        ),
        source=prepared.source,
        input_artifact=prepared.source,
        payload=prepared.request.issue.model_dump(mode="json"),
        inventory=ImageInventory(images=[prepared.request.image]),
        config_digest=prepared.config_digest,
    )


class ExecutionActivities:
    def __init__(
        self, settings: Settings, store: ArtifactStore, executor: ExecutionPort | None = None
    ):
        self.settings = settings
        self.store = store
        self.executor = executor if executor is not None else DockerExecutor(settings, store)

    @activity.defn(name="corsair.execution.prepare.v3")
    async def prepare(self, start: ExecutionStart) -> PreparedExecution:
        async with intake_heartbeats():
            request = type(start.request).model_validate(start.request.model_dump())
            inventory = await asyncio.to_thread(discover_images, self.settings)
            admit_execution_image(request, inventory)
            source = await asyncio.to_thread(
                snapshot_source, request.source, self.settings, self.store
            )
            fixed = (
                None
                if request.fixed_source is None
                else await asyncio.to_thread(
                    snapshot_source,
                    request.fixed_source,
                    self.settings,
                    self.store,
                )
            )
            if request.intake_result is not None:
                from corsair.policies.pipeline import validated_intake_image
                from corsair.steps.pipeline import load_committed_intake

                intake = load_committed_intake(self.store, request.intake_result)
                selected = validated_intake_image(intake)
                if (
                    intake.decision.classification != "in_scope_supported"
                    or intake.proposal is None
                    or intake.proposal.issue != request.issue
                    or intake.source != source
                    or request.image not in intake.inventory.images
                    or intake.proposal.suggested_image != request.image.reference
                    or selected != request.image
                    or intake.identities.get("config") != self.settings.identity
                ):
                    raise ValueError("intake handoff does not bind this issue/source/image")
            prepared = PreparedExecution(
                run_id=start.run_id,
                request=request,
                source=source,
                fixed_source=fixed,
                config_digest=self.settings.identity,
                request_digest=digest(request),
                resources_digest=execution_resources_digest(),
            )
            artifact = self.store.put_json(prepared)
            return prepared.model_copy(update={"artifact": artifact})

    @activity.defn(name="corsair.execution.produce.v3")
    async def produce(self, item: ExecutionRoundInput) -> ExecutionEpisode:
        validate_execution_identity(item.prepared, self.settings, self.store)
        async with intake_heartbeats(), docker_client() as client:
            if not await asyncio.to_thread(recheck_image, client, item.prepared.request.image):
                raise ValueError("selected image changed before producer")
            async with inspection_session(
                DockerInspection(
                    self.settings,
                    self.store,
                    inspection_input(item, "p"),
                    client,
                )
            ) as reader:
                output = await run_execution_producer(item, self.settings, reader)
                if output.plan is not None:
                    output = output.model_copy(
                        update={"plan_artifact": self.store.put_json(output.plan)}
                    )
                return output

    @activity.defn(name="corsair.execution.audit.v3")
    async def audit(self, item: AuditEpisodeInput) -> ExecutionEpisode:
        validate_execution_identity(item.round.prepared, self.settings, self.store)
        async with intake_heartbeats(), docker_client() as client:
            if not await asyncio.to_thread(
                recheck_image, client, item.round.prepared.request.image
            ):
                raise ValueError("selected image changed before auditor")
            async with inspection_session(
                DockerInspection(
                    self.settings,
                    self.store,
                    inspection_input(item.round, "a"),
                    client,
                )
            ) as reader:
                return await run_execution_auditor(item.round, item.plan, self.settings, reader)

    @activity.defn(name="corsair.execution.execute.v3")
    async def execute(self, item: ExecutePlanInput) -> ProcessObservation:
        validate_execution_identity(item.prepared, self.settings, self.store)
        if item.audit.decision != "accepted":
            raise ValueError("semantic audit did not accept the plan")
        identity = f"{item.prepared.run_id}-r{item.plan.revision}-" + (
            "fixed" if item.fixed else "original"
        )
        async with intake_heartbeats():
            task = asyncio.create_task(
                asyncio.to_thread(
                    self.executor.execute,
                    item.prepared,
                    item.plan,
                    identity,
                    fixed=item.fixed,
                    timeout_seconds=item.timeout_seconds,
                )
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Reconcile the bounded operation and cleanup before acknowledging cancellation.
                await task
                raise

    @activity.defn(name="corsair.execution.record.v3")
    async def record(self, result: ExecutionResult) -> ExecutionResult:
        result = ExecutionResult.model_validate(result.model_dump())
        prepared = None
        if result.prepared_artifact is not None:
            prepared = PreparedExecution.model_validate(
                self.store.get_json(result.prepared_artifact)
            )
            if prepared.run_id != result.run_id or prepared.request.case_id != result.case_id:
                raise ValueError("admitted request identity changed")
            expected = {
                "request": prepared.request_digest,
                "source": prepared.source.sha256,
                "config": prepared.config_digest,
                "resources": prepared.resources_digest,
            }
            if result.identities != expected or prepared.request_digest != digest(prepared.request):
                raise ValueError("admission identities differ from recorded result")
        if result.outcome == "SUCCEEDED" and not result.rounds:
            raise ValueError("success requires actual process evidence")
        last_observation = None
        for round_result in result.rounds:
            for observation in (round_result.observation, round_result.fixed_observation):
                if observation is None:
                    continue
                if prepared is None or round_result.plan is None or round_result.audit is None:
                    raise ValueError(
                        "process observation requires admitted request, plan and audit"
                    )
                if round_result.audit.decision != "accepted":
                    raise ValueError("execution without accepted audit")
                plan = round_result.plan
                source = (
                    prepared.fixed_source
                    if observation is round_result.fixed_observation
                    else prepared.source
                )
                if source is None or (
                    observation.source_digest != source.sha256
                    or observation.image_id != prepared.request.image.image_id
                    or observation.plan_digest != digest(plan)
                    or len(observation.receipts) > len(plan.commands)
                    or any(
                        receipt.command_digest != digest(command)
                        for receipt, command in zip(
                            observation.receipts, plan.commands, strict=False
                        )
                    )
                ):
                    raise ValueError("process evidence does not bind the admitted experiment")
                if observation.outcome in ("SUCCEEDED", "FAILED"):
                    if (
                        not observation.cleanup_confirmed
                        or observation.error is not None
                        or len(observation.receipts) != len(plan.commands)
                        or any(receipt.state != "completed" for receipt in observation.receipts)
                    ):
                        raise ValueError("completed experiment has incomplete process evidence")
                    success = all(
                        (receipt.exit_code == 0) == (command.expected == "zero")
                        for receipt, command in zip(
                            observation.receipts, plan.commands, strict=True
                        )
                    )
                    if (observation.outcome == "SUCCEEDED") != success:
                        raise ValueError("process outcome differs from native exits")
                if observation is round_result.observation:
                    last_observation = observation
                if observation.artifact is None:
                    raise ValueError("process observation was not committed")
                kind = (
                    "execution-refusal"
                    if observation.error == "OPERATION_UNCERTAIN"
                    else "execution"
                )
                if observation.error == "OPERATION_UNCERTAIN" and (
                    observation.receipts
                    or observation.cleanup_confirmed
                    or observation.outcome != "INCOMPLETE"
                ):
                    raise ValueError("refusal cannot establish execution or cleanup")
                if (
                    self.store.reconcile(f"{kind}.{observation.operation_id}")
                    != observation.artifact
                ):
                    raise ValueError("process observation receipt changed")
                recorded = ProcessObservation.model_validate(
                    self.store.get_json(observation.artifact)
                )
                if recorded != observation.model_copy(update={"artifact": None}):
                    raise ValueError("process observation differs from immutable evidence")
                for receipt in observation.receipts:
                    self.store.get(receipt.stdout)
                    self.store.get(receipt.stderr)
        if result.outcome == "SUCCEEDED" and (
            last_observation is None
            or last_observation.outcome != "SUCCEEDED"
            or result.error is not None
        ):
            raise ValueError("success requires a successful committed experiment")
        artifact = self.store.put_json(result.model_copy(update={"result_artifact": None}))
        self.store.commit(f"execution-result.{result.run_id}", artifact)
        return result.model_copy(update={"result_artifact": artifact})

    def registered(self):
        return [self.prepare, self.produce, self.audit, self.execute, self.record]
