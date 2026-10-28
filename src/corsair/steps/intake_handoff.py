"""Ordinary committed intake admission and aggregate recording, using main's runner."""

import asyncio

from temporalio import activity

from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import InvestigationRequest, InvestigationResult, PreparedCase
from corsair.contracts.intake_agent import AvailableImage, IntakeResult
from corsair.contracts.intake_pipeline import IntakeInvestigationResult
from corsair.policies.intake_handoff import selected_image
from corsair.settings import Settings


def load_committed_intake(store: ArtifactStore, reference) -> IntakeResult:
    result = IntakeResult.model_validate(store.get_json(reference))
    if store.reconcile(f"intake.{result.run_id}") != reference:
        raise ValueError("intake artifact is not committed for its identity")
    return result.model_copy(update={"result_artifact": reference})


def admit_intake_selection(
    request: InvestigationRequest, settings: Settings, store: ArtifactStore
) -> AvailableImage:
    if request.intake_result is None:
        raise ValueError("intake provenance required")
    result = load_committed_intake(store, request.intake_result)
    image = selected_image(result)
    if result.proposal is None or result.source is None:
        raise ValueError("missing intake issue/source")
    issue = result.proposal.issue
    paths = {loc.path for loc in result.proposal.locations} | {loc.path for loc in issue.locations}
    if (
        result.identities.get("config") != settings.identity
        or result.source.sha256 != request.case.source.expected_digest
        or issue.title != request.case.finding.title
        or issue.description != request.case.finding.description
        or paths != {request.case.finding.file}
        or image.language != request.case.recipe.kind.split(".", 1)[0]
        or image not in discover_images(settings).images
    ):
        raise ValueError("intake does not bind this issue/source/configuration/current image")
    return image


def validate_selected_image(prepared: PreparedCase, settings: Settings) -> None:
    reference = prepared.manifest.image_reference
    if reference is not None and not any(
        i.reference == reference and i.image_id == prepared.manifest.image_id
        for i in discover_images(settings).images
    ):
        raise ValueError("selected intake image changed before agent work")


class IntakePipelineActivities:
    def __init__(self, store: ArtifactStore):
        self.store = store

    @activity.defn(name="corsair.intake-investigation.record.v1")
    async def record(self, result: IntakeInvestigationResult) -> IntakeInvestigationResult:
        return await asyncio.to_thread(self._record, result)

    def _record(self, result: IntakeInvestigationResult) -> IntakeInvestigationResult:
        normalized = IntakeInvestigationResult.model_validate(
            result.model_dump(exclude={"result_artifact"})
        )
        if normalized.intake is not None:
            ref = normalized.intake.result_artifact
            if ref is None or load_committed_intake(self.store, ref) != normalized.intake:
                raise ValueError("aggregate intake differs from committed child")
        if normalized.investigation_result is not None:
            ref = normalized.investigation_result
            child = InvestigationResult.model_validate(self.store.get_json(ref))
            if (
                self.store.reconcile(f"result.{child.run_id}") != ref
                or child.run_id != normalized.investigation_run_id
                or child.case_id != normalized.case_id
                or child.disposition != normalized.investigation_disposition
                or child.execution_status != normalized.investigation_execution_status
            ):
                raise ValueError("aggregate investigation differs from committed child")
        ref = self.store.put_json(normalized)
        self.store.commit(f"intake-investigation.{normalized.run_id}", ref)
        return normalized.model_copy(update={"result_artifact": ref})

    def registered(self) -> list:
        return [self.record]
