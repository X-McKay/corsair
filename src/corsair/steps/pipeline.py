"""Committed provenance and aggregate recording at ordinary activity boundaries."""

import asyncio

from temporalio import activity

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ArtifactRef
from corsair.contracts.execution import ExecutionResult
from corsair.contracts.intake import IntakeResult
from corsair.contracts.pipeline import IssueInvestigationResult


def load_committed_intake(store: ArtifactStore, reference: ArtifactRef) -> IntakeResult:
    result = IntakeResult.model_validate(store.get_json(reference))
    if store.reconcile(f"intake.{result.run_id}") != reference:
        raise ValueError("intake result is not the committed result for its identity")
    return result.model_copy(update={"result_artifact": reference})


class PipelineActivities:
    def __init__(self, store: ArtifactStore):
        self.store = store

    @activity.defn(name="corsair.issue-investigation.record.v4")
    async def record(self, result: IssueInvestigationResult) -> IssueInvestigationResult:
        return await asyncio.to_thread(self._record, result)

    def _record(self, result: IssueInvestigationResult) -> IssueInvestigationResult:
        normalized = IssueInvestigationResult.model_validate(
            result.model_dump(exclude={"result_artifact"})
        )
        if normalized.intake is not None:
            reference = normalized.intake.result_artifact
            if (
                reference is None
                or load_committed_intake(self.store, reference) != normalized.intake
            ):
                raise ValueError("aggregate intake differs from committed child")
        if normalized.execution_result is not None:
            reference = normalized.execution_result
            execution = ExecutionResult.model_validate(self.store.get_json(reference))
            if (
                execution.run_id != normalized.execution_run_id
                or self.store.reconcile(f"execution-result.{execution.run_id}") != reference
                or execution.case_id != normalized.case_id
                or execution.outcome != normalized.execution_outcome
                or execution.error != normalized.execution_error
            ):
                raise ValueError("aggregate execution differs from committed child")
        reference = self.store.put_json(normalized)
        self.store.commit(f"issue-investigation.{normalized.run_id}", reference)
        return normalized.model_copy(update={"result_artifact": reference})

    def registered(self) -> list:
        return [self.record]
