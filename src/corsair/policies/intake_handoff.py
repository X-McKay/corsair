"""Pure adapter from a supported normalized issue to an operator-owned main Case."""

from corsair.contracts import InvestigationRequest, Usage, digest
from corsair.contracts.intake_agent import AvailableImage, IntakeResult
from corsair.contracts.intake_pipeline import IntakeInvestigationRequest, StopReason
from corsair.policies.intake_agent import classify_intake


def stop_reason(result: IntakeResult) -> StopReason | None:
    if result.decision.status == "error":
        return "INTAKE_ERROR"
    if result.decision.status == "needs_input":
        return "NEEDS_INPUT"
    if result.decision.classification == "out_of_scope":
        return "OUT_OF_SCOPE"
    if result.decision.classification == "in_scope_not_supported":
        return "UNSUPPORTED"
    return None if result.decision.classification == "in_scope_supported" else "HANDOFF_INVALID"


def selected_image(result: IntakeResult) -> AvailableImage:
    if (
        stop_reason(result) is not None
        or result.proposal is None
        or result.source is None
        or result.result_artifact is None
        or classify_intake(result.proposal, result.inventory) != result.decision
    ):
        raise ValueError("intake has no supported committed image selection")
    image = next(
        (i for i in result.inventory.images if i.reference == result.proposal.suggested_image), None
    )
    if image is None or image.image_id != result.decision.image_id:
        raise ValueError("selected image differs from inventory identity")
    return image


def charged_usage(result: IntakeResult) -> Usage:
    return result.usage.model_copy(
        update={"tool_calls": result.usage.tool_calls + result.inspection_reads}
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


def bind_investigation(
    root: IntakeInvestigationRequest, result: IntakeResult, expected_id: str, seconds: int
) -> InvestigationRequest:
    image = selected_image(result)
    if root.binding is None:
        raise ValueError("operator-owned target binding required")
    if result.run_id != expected_id or result.identities.get("request") != digest(root.intake):
        raise ValueError("intake does not bind original input")
    if result.proposal is None or result.source is None:
        raise ValueError("missing source or issue")
    binding = root.binding
    paths = {loc.path for loc in result.proposal.locations}
    paths.update(loc.path for loc in result.proposal.issue.locations)
    if paths != {binding.finding.file} or image.language != binding.recipe.kind.split(".", 1)[0]:
        raise ValueError("normalized issue/image does not bind the operator's target")
    if root.case_id != binding.case_id or root.intake.source != binding.source:
        raise ValueError("trusted binding identity changed")
    usage = charged_usage(result)
    llms = root.intake.budget.max_llm_calls - usage.llm_calls
    tools = root.intake.budget.max_tool_calls - usage.tool_calls
    if llms < 2 or tools < 1 or seconds < 30:
        raise ValueError("remaining budget exhausted")
    budget = root.intake.budget.model_copy(
        update={
            "max_llm_calls": llms,
            "max_tool_calls": tools,
            "episode_llm_calls": min(root.intake.budget.episode_llm_calls, llms),
            "max_elapsed_seconds": min(seconds, root.intake.budget.max_elapsed_seconds),
        }
    )
    issue = result.proposal.issue
    if not issue.title or not issue.description:
        raise ValueError("main investigation requires title and description")
    case = binding.model_copy(
        update={
            "source": binding.source.model_copy(update={"expected_digest": result.source.sha256}),
            "finding": binding.finding.model_copy(
                update={"title": issue.title, "description": issue.description}
            ),
        }
    )
    return InvestigationRequest(case=case, budget=budget, intake_result=result.result_artifact)


def remaining_budget(root, result, seconds):
    usage = charged_usage(result)
    llms = root.max_llm_calls - usage.llm_calls
    tools = root.max_tool_calls - usage.tool_calls
    if llms < 2 or tools < 1 or seconds < 30:
        raise ValueError("insufficient remaining investigation budget")
    return root.model_copy(
        update={
            "max_llm_calls": llms,
            "max_tool_calls": tools,
            "episode_llm_calls": min(root.episode_llm_calls, llms),
            "max_elapsed_seconds": min(seconds, root.max_elapsed_seconds),
        }
    )


def investigation_usage(result) -> Usage:
    recorded = [item.producer.usage for item in result.rounds]
    recorded.extend(item.audit.usage for item in result.rounds if item.audit is not None)
    if not recorded:
        return Usage()
    total = recorded[0]
    for usage in recorded[1:]:
        total = combine_usage(total, usage)
    return total
