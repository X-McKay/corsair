"""Finite evaluation batches, containing only case requests—not expected labels."""

import asyncio
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from corsair.contracts import BatchItem, BatchRequest, format_diagnostic
    from corsair.workflows.investigation import InvestigationWorkflow

# The status query returns at most this many child rows, most informative state first.
# Rows are read-only presentation state that never feeds a command, so replay is
# unaffected; a child's own phase is not visible to its parent and is not reported.
_CHILD_ROWS = 64
_STATE_ORDER = {"running": 0, "failed": 1, "pending": 2, "completed": 3}

ChildRow = dict[str, str | int | None]


def _row_order(row: ChildRow) -> tuple[int, str, int]:
    repeat = row["repeat"]
    return (
        _STATE_ORDER[str(row["state"])],
        str(row["case_id"]),
        repeat if isinstance(repeat, int) else 0,
    )


@workflow.defn(name="corsair.evaluation")
class EvaluationWorkflow:
    def __init__(self):
        self.completed = self.total = self.running = self.errors = 0
        self.started: datetime | None = None
        self.children: list[ChildRow] = []

    @workflow.query
    def status(self) -> dict:
        """Child-work counts and states only; labels and oracles never enter this workflow."""
        rows = sorted(self.children, key=_row_order)
        return {
            "completed": self.completed,
            "total": self.total,
            "running": self.running,
            "errors": self.errors,
            "started": self.started.isoformat() if self.started else None,
            "children": [dict(row) for row in rows[:_CHILD_ROWS]],
            "children_omitted": max(0, len(rows) - _CHILD_ROWS),
        }

    @staticmethod
    def _transition(row: ChildRow, state: str) -> None:
        """Record a child state change at deterministic workflow time."""
        row["state"] = state
        row["started" if state == "running" else "finished"] = workflow.now().isoformat()

    @workflow.run
    async def run(self, request: BatchRequest) -> list[BatchItem]:
        self.started = workflow.now()
        self.total = len(request.requests) * request.repeats
        semaphore = asyncio.Semaphore(request.concurrency)
        self.children = [
            {
                "case_id": case_request.case.case_id,
                "repeat": repeat,
                "run_id": f"{request.batch_id}.c{index}.r{repeat}",
                "state": "pending",
                "started": None,
                "finished": None,
            }
            for index, case_request in enumerate(request.requests)
            for repeat in range(request.repeats)
        ]

        async def investigate(index: int, repeat: int) -> BatchItem:
            row = self.children[index * request.repeats + repeat]
            async with semaphore:
                self.running += 1
                self._transition(row, "running")
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
                    self._transition(row, "completed")
                    return BatchItem(
                        case_id=case_request.case.case_id,
                        run_id=run_id,
                        artifact=result.result_artifact,
                    )
                except ChildWorkflowError as exc:
                    self.errors += 1
                    self._transition(row, "failed")
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
