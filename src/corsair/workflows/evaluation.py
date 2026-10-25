"""Finite evaluation batches, containing only case requests—not expected labels."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import BatchItem, BatchRequest
    from corsair.workflows.investigation import InvestigationWorkflow


@workflow.defn(name="corsair.evaluation")
class EvaluationWorkflow:
    @workflow.run
    async def run(self, request: BatchRequest) -> list[BatchItem]:
        semaphore = asyncio.Semaphore(request.concurrency)

        async def investigate(index: int, repeat: int) -> BatchItem:
            async with semaphore:
                case_request = request.requests[index]
                run_id = f"{request.batch_id}.c{index}.r{repeat}"
                try:
                    result = await workflow.execute_child_workflow(
                        InvestigationWorkflow.run,
                        case_request,
                        id=run_id,
                        execution_timeout=timedelta(
                            seconds=case_request.budget.max_elapsed_seconds + 120
                        ),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                        parent_close_policy=workflow.ParentClosePolicy.REQUEST_CANCEL,
                    )
                    return BatchItem(
                        case_id=case_request.case.case_id,
                        run_id=run_id,
                        artifact=result.result_artifact,
                    )
                except ChildWorkflowError as exc:
                    return BatchItem(
                        case_id=case_request.case.case_id, run_id=run_id, error=str(exc)
                    )

        return await asyncio.gather(
            *[
                investigate(index, repeat)
                for index in range(len(request.requests))
                for repeat in range(request.repeats)
            ]
        )
