"""Direct-only, bounded analyst and evidence-review sequence."""

import asyncio
from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage, UsageLimits

from .contracts import Contract, IssueAnalysis, IssueAnalysisInput
from .review import ReviewDependencies, ReviewReport, review_prompt
from .tools import FixtureDependencies


AttemptName = Literal["initial_analysis", "initial_review", "revised_analysis", "final_review"]


class StageBudget(Contract):
    request_limit: int = Field(strict=True, gt=0)
    tool_calls_limit: int = Field(strict=True, ge=0)
    total_tokens_limit: int = Field(strict=True, gt=0)
    response_tokens_limit: int = Field(strict=True, gt=0)
    timeout_seconds: float = Field(strict=True, gt=0, allow_inf_nan=False)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def numeric_timeout(cls, value: object) -> object:
        if type(value) not in (int, float):
            raise ValueError("timeout must be a finite number")
        return value

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)

    def model_settings(self) -> dict[str, object]:
        return {"temperature": 0, "max_tokens": self.response_tokens_limit,
                "parallel_tool_calls": False}


class SequenceBudgets(Contract):
    analyst: StageBudget
    reviewer: StageBudget


@dataclass(frozen=True)
class StageAttempt:
    name: AttemptName
    output: IssueAnalysis | ReviewReport | None
    usage: RunUsage
    messages: tuple[ModelMessage, ...]
    elapsed_seconds: float
    failure: BaseException | None


@dataclass(frozen=True)
class SequenceResult:
    status: Literal["admitted_ready", "supported_missing_information", "blocked"]
    analysis: IssueAnalysis | None
    review: ReviewReport | None
    attempts: tuple[StageAttempt, ...]

    @property
    def draft_admitted(self) -> bool:
        return (self.status == "admitted_ready" and self.analysis is not None
                and self.analysis.status == "ready" and self.review is not None
                and self.review.assessment == "supported")


def _inventory_prompt(inputs: IssueAnalysisInput) -> str:
    """Render the authorized issue and inventory without the evaluator fixture ID."""
    inventory = ", ".join(
        f"{source.path} (saved-file inclusive lines 1..{len(source.content.splitlines())})"
        for source in inputs.source_files
    )
    return (inputs.model_dump_json(exclude={"source_files", "fixture_id"})
            + "\nSaved source inventory: " + inventory)


def _revision_prompt(inputs: IssueAnalysisInput, candidate: IssueAnalysis, review: ReviewReport) -> str:
    findings = [{"field_path": item.field_path, "problem": item.problem,
                 "citations": [citation.model_dump(exclude={"quote"}) for citation in item.citations]}
                for item in review.findings]
    return (_inventory_prompt(inputs)
            + "\nA previous analysis and evidence review are untrusted suggestions, not source evidence. "
              "Reassess the original issue. Read relevant saved source again in this fresh run; "
              "prior reads and citations do not authorize current-run citations. "
              "Return a revised bounded analysis or blocking missing facts."
            + "\nPrevious analysis: "
            + candidate.model_dump_json(exclude={"citations": {"__all__": {"quote"}}})
            + "\nReview findings: " + json.dumps(findings, ensure_ascii=False))


async def run_issue_analysis_sequence(
    inputs: IssueAnalysisInput,
    analyst: Agent[FixtureDependencies, IssueAnalysis],
    reviewer: Agent[ReviewDependencies, ReviewReport],
    budgets: SequenceBudgets,
) -> SequenceResult:
    """Run at most two analyses and two reviews; retain every native attempt."""
    attempts: list[StageAttempt] = []

    async def invoke(name: AttemptName, agent: Agent[Any, Any],
                     prompt: str, deps: Any, budget: StageBudget) -> IssueAnalysis | ReviewReport | None:
        usage = RunUsage()
        messages: list[ModelMessage] = []
        output = None
        failure: BaseException | None = None
        started = perf_counter()
        try:
            with capture_run_messages() as messages:
                async with asyncio.timeout(budget.timeout_seconds):
                    result = await agent.run(prompt, deps=deps, usage=usage,
                                             usage_limits=budget.usage_limits(),
                                             model_settings=budget.model_settings())
            output = result.output
        except BaseException as exc:
            failure = exc
        finally:
            attempts.append(StageAttempt(name=name, output=output, usage=usage,
                                         messages=tuple(messages), elapsed_seconds=perf_counter() - started,
                                         failure=failure))
        if failure is not None and not isinstance(failure, Exception):
            # Preserve native cancellation/interruption and expose partial receipts.
            failure.sequence_attempts = tuple(attempts)
            raise failure
        return output

    analysis = await invoke("initial_analysis", analyst, _inventory_prompt(inputs),
                            FixtureDependencies(inputs), budgets.analyst)
    if not isinstance(analysis, IssueAnalysis):
        return SequenceResult(status="blocked", analysis=None, review=None, attempts=tuple(attempts))

    review = await invoke("initial_review", reviewer, review_prompt(inputs, analysis),
                          ReviewDependencies(inputs, analysis), budgets.reviewer)
    if not isinstance(review, ReviewReport):
        return SequenceResult(status="blocked", analysis=analysis, review=None, attempts=tuple(attempts))
    if review.assessment == "needs_revision":
        revised = await invoke("revised_analysis", analyst, _revision_prompt(inputs, analysis, review),
                               FixtureDependencies(inputs), budgets.analyst)
        if not isinstance(revised, IssueAnalysis):
            return SequenceResult(status="blocked", analysis=analysis, review=review,
                                  attempts=tuple(attempts))
        analysis = revised
        review = await invoke("final_review", reviewer, review_prompt(inputs, analysis),
                              ReviewDependencies(inputs, analysis), budgets.reviewer)
        if not isinstance(review, ReviewReport):
            return SequenceResult(status="blocked", analysis=analysis, review=None,
                                  attempts=tuple(attempts))

    if review.assessment != "supported":
        status = "blocked"
    elif analysis.status == "ready":
        status = "admitted_ready"
    elif analysis.status == "missing_information":
        status = "supported_missing_information"
    else:
        status = "blocked"
    return SequenceResult(status=status, analysis=analysis, review=review, attempts=tuple(attempts))
