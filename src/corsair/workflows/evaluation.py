"""Finite evaluation batches, containing only case requests—not expected labels."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import BatchItem, BatchRequest, format_diagnostic
    from corsair.policies.time_bounds import investigation_execution_seconds
    from corsair.workflows.investigation import InvestigationWorkflow


@workflow.defn(name="corsair.evaluation")
class EvaluationWorkflow:
    def __init__(self):
        self.completed = self.total = self.running = self.errors = 0

    @workflow.query
    def status(self) -> dict:
        """Child-work counts only; labels and oracles never enter this workflow."""
        return {
            "completed": self.completed,
            "total": self.total,
            "running": self.running,
            "errors": self.errors,
        }

    @workflow.run
    async def run(self, request: BatchRequest) -> list[BatchItem]:
        self.total = len(request.requests) * request.repeats
        semaphore = asyncio.Semaphore(request.concurrency)

        async def investigate(index: int, repeat: int) -> BatchItem:
            async with semaphore:
                self.running += 1
                case_request = request.requests[index]
                run_id = f"{request.batch_id}.c{index}.r{repeat}"
                try:
                    result = await workflow.execute_child_workflow(
                        InvestigationWorkflow.run,
                        case_request,
                        id=run_id,
                        execution_timeout=timedelta(
                            seconds=investigation_execution_seconds(case_request.budget)
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
                    self.errors += 1
                    return BatchItem(
                        case_id=case_request.case.case_id,
                        run_id=run_id,
                        error=format_diagnostic(str(exc)),
                    )
                finally:
                    self.running -= 1
                    self.completed += 1

        return await asyncio.gather(
            *[
                investigate(index, repeat)
                for index in range(len(request.requests))
                for repeat in range(request.repeats)
            ]
        )
