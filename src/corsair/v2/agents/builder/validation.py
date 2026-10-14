"""Output check for a Recipe: every command it names must have run in this episode and exited 0.

The evidence is the run's own message history (each ``run`` call and its returned exit code), not state kept in
tool dependencies, so the check reads the same in direct mode and under Temporal, where tools run in activities.
This only stops a recipe the agent never tried; trusted replay in a fresh container still decides if it holds.
"""
from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart

from corsair.v2.contracts import Recipe, RecipeFile


def last_exit_codes(messages: Sequence[ModelMessage]) -> dict[tuple[str, ...], int | None]:
    """Exit code of the latest ``run`` of each argv in ``messages``; None when it timed out or overflowed."""
    calls: dict[str, tuple[str, ...]] = {}
    codes: dict[tuple[str, ...], int | None] = {}
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == "run":
                argv = part.args_as_dict().get("argv")
                if isinstance(argv, list):
                    calls[part.tool_call_id] = tuple(str(arg) for arg in argv)
            elif isinstance(part, ToolReturnPart) and part.tool_name == "run" and part.tool_call_id in calls:
                content = part.content if isinstance(part.content, dict) else {}
                codes[calls[part.tool_call_id]] = content.get("exit_code")
    return codes


def written_files(messages: Sequence[ModelMessage]) -> tuple[RecipeFile, ...]:
    """The files ``write_new_file`` actually wrote in this episode, in order; the model's own list is ignored."""
    calls: dict[str, tuple[str, str]] = {}
    written: dict[str, str] = {}
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == "write_new_file":
                args = part.args_as_dict()
                calls[part.tool_call_id] = (str(args.get("path", "")), str(args.get("content", "")))
            elif (isinstance(part, ToolReturnPart) and part.tool_name == "write_new_file"
                  and part.tool_call_id in calls and str(part.content).startswith("wrote ")):
                path, content = calls[part.tool_call_id]
                written[path] = content
    return tuple(RecipeFile(path=path, content=content) for path, content in written.items())


def check_recipe(recipe: Recipe, messages: Sequence[ModelMessage]) -> Recipe:
    codes = last_exit_codes(messages)
    problems = [f"{list(argv)} {'was never run here' if argv not in codes else f'last exited {codes[argv]}'}"
                for argv in (*recipe.setup, recipe.baseline_test) if codes.get(argv, -1) != 0]
    if any(not argv for argv in recipe.setup):
        problems.append("a setup command is empty")
    if problems:
        raise ModelRetry("Every setup command and the baseline test must have run here and exited 0:\n- "
                         + "\n- ".join(problems))
    return recipe.model_copy(update={"files": written_files(messages)})
