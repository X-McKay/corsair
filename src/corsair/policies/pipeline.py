"""Pure intake gates and source/image-bound construction; no I/O."""

from corsair.contracts import Budget, Usage, digest
from corsair.contracts.execution import ExecutionRequest
from corsair.contracts.intake import AvailableImage, IntakeResult
from corsair.contracts.pipeline import IssueInvestigationRequest, StopReason
from corsair.policies.intake import classify_intake


def intake_stop_reason(result: IntakeResult) -> StopReason | None:
    if result.decision.status == "error":
        return "INTAKE_ERROR"
    if result.decision.status == "needs_input":
        return "NEEDS_INPUT"
    if result.decision.classification == "out_of_scope":
        return "OUT_OF_SCOPE"
    if result.decision.classification == "in_scope_not_supported":
        return "UNSUPPORTED"
    return None if result.decision.classification == "in_scope_supported" else "HANDOFF_INVALID"


def validated_intake_image(result: IntakeResult) -> AvailableImage:
    if (
        intake_stop_reason(result) is not None
        or result.proposal is None
        or result.source is None
        or result.result_artifact is None
        or classify_intake(result.proposal, result.inventory) != result.decision
    ):
        raise ValueError("intake has no supported image-bound handoff")
    image = next(
        (
            image
            for image in result.inventory.images
            if image.reference == result.proposal.suggested_image
        ),
        None,
    )
    if image is None or image.image_id != result.decision.image_id:
        raise ValueError("intake image identity does not match selected inventory entry")
    return image


def charged_intake_usage(result: IntakeResult) -> Usage:
    return result.usage.model_copy(
        update={"tool_calls": result.usage.tool_calls + result.inspection_reads}
    )


def remaining_budget(root: Budget, result: IntakeResult, seconds: int) -> Budget:
    usage = charged_intake_usage(result)
    llms = root.max_llm_calls - usage.llm_calls
    tools = root.max_tool_calls - usage.tool_calls
    if llms < 2 or tools < 6 or seconds < 30:
        raise ValueError("insufficient remaining investigation budget")
    return root.model_copy(
        update={
            "max_llm_calls": llms,
            "max_tool_calls": tools,
            "episode_llm_calls": min(root.episode_llm_calls, llms),
            "max_elapsed_seconds": min(seconds, root.max_elapsed_seconds),
        }
    )


def execution_from_intake(
    request: IssueInvestigationRequest, result: IntakeResult, expected_id: str, budget: Budget
) -> ExecutionRequest:
    image = validated_intake_image(result)
    if result.run_id != expected_id or result.identities.get("request") != digest(request.intake):
        raise ValueError("intake does not bind the original request and child identity")
    if result.proposal is None or result.source is None:
        raise ValueError("missing intake provenance")
    return ExecutionRequest(
        case_id=request.case_id,
        issue=result.proposal.issue,
        source=request.intake.source.model_copy(update={"expected_digest": result.source.sha256}),
        image=image,
        intake_result=result.result_artifact,
        fixed_source=request.fixed_source,
        budget=budget,
    )


def combine_usage(left: Usage, right: Usage) -> Usage:
    return Usage(
        llm_calls=left.llm_calls + right.llm_calls,
        tool_calls=left.tool_calls + right.tool_calls,
        seconds=left.seconds + right.seconds,
        input_tokens=None
        if left.input_tokens is None or right.input_tokens is None
        else left.input_tokens + right.input_tokens,
        output_tokens=None
        if left.output_tokens is None or right.output_tokens is None
        else left.output_tokens + right.output_tokens,
        skills_loaded=sorted(set(left.skills_loaded) | set(right.skills_loaded)),
        skills_preloaded=sorted(set(left.skills_preloaded) | set(right.skills_preloaded)),
    )
