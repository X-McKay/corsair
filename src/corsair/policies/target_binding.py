"""Pre-model target binding: structural facts decided before any model call. Pure.

A case whose declared target cannot bind to the recipe's callable can never reach a
decisive verdict: the verdict-time gate would only discover that after producer,
auditor and container runs. This check reads the admitted module text (never a live
checkout) and fails only when a structural fact is *certainly* violated. Anything
static analysis cannot decide -- a decorated callable, a name bound more than once or
by assignment/import, a star import, a module ``__getattr__`` -- passes, so the kernel's
own run-time gates stay the authority and no runnable case is turned away.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum

from corsair.contracts import Finding, Recipe


class TargetBindingReason(StrEnum):
    FILE_ABSENT = "file_absent"
    LINE_MISSING = "line_missing"
    LINE_OUT_OF_RANGE = "line_out_of_range"
    MODULE_UNPARSEABLE = "module_unparseable"
    FUNCTION_NOT_DEFINED = "function_not_defined"
    FUNCTION_ASYNC = "function_async"
    PAYLOAD_PARAMETER_UNKNOWN = "payload_parameter_unknown"
    FIXED_KWARG_UNKNOWN = "fixed_kwarg_unknown"
    REQUIRED_PARAMETER_UNBOUND = "required_parameter_unbound"


@dataclass(frozen=True)
class TargetBindingFailure:
    reason: TargetBindingReason
    detail: str

    def __str__(self) -> str:
        return f"target_binding {self.reason.value}: {self.detail}"


def _source_line_count(text: str) -> int:
    """Count lines the way the Python tokenizer and coverage number them.

    ``str.splitlines`` also splits on form feeds and Unicode separators, which do
    not start a new source line, so only CRLF, CR and LF are line breaks here.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return len(lines)


def _bindings(module: ast.Module, name: str) -> list[ast.AST] | None:
    """Every node that may bind ``name`` anywhere in the module, or None if undecidable.

    Walking nested scopes too over-approximates the module's bindings, which only
    makes the check pass more often, never block a callable that exists.
    """
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__getattr__"
        for node in module.body
    ):
        return None  # A module __getattr__ can supply any attribute.
    found: list[ast.AST] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            return None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                found.append(node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id == name:
                found.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == name:
                    found.append(node)
    return found


def _signature_failure(function: ast.FunctionDef, recipe: Recipe) -> TargetBindingFailure | None:
    """The driver calls ``function(**fixed_kwargs, payload_parameter=payload)``."""
    arguments = function.args
    keyword_names = {argument.arg for argument in (*arguments.args, *arguments.kwonlyargs)}
    accepts_kwargs = arguments.kwarg is not None
    if recipe.payload_parameter not in keyword_names and not accepts_kwargs:
        return TargetBindingFailure(
            TargetBindingReason.PAYLOAD_PARAMETER_UNKNOWN,
            f"{recipe.payload_parameter!r} is not a keyword parameter of {function.name}()",
        )
    for key in sorted(recipe.fixed_kwargs):
        if key not in keyword_names and not accepts_kwargs:
            return TargetBindingFailure(
                TargetBindingReason.FIXED_KWARG_UNKNOWN,
                f"fixed argument {key!r} is not a keyword parameter of {function.name}()",
            )
    supplied = {recipe.payload_parameter, *recipe.fixed_kwargs}
    positional = [*arguments.posonlyargs, *arguments.args]
    required = positional[: len(positional) - len(arguments.defaults)]
    unbound = [
        argument.arg
        for argument in required
        if argument in arguments.posonlyargs or argument.arg not in supplied
    ]
    unbound += [
        argument.arg
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
        if default is None and argument.arg not in supplied
    ]
    if unbound:
        return TargetBindingFailure(
            TargetBindingReason.REQUIRED_PARAMETER_UNBOUND,
            f"{function.name}() requires {', '.join(unbound)} that the recipe does not supply "
            "by keyword",
        )
    return None


def target_binding(
    finding: Finding, recipe: Recipe, module_text: str | None
) -> TargetBindingFailure | None:
    """Return the first certain structural reason the case cannot bind, else None.

    ``module_text`` is the recipe module as read from the admitted snapshot (the
    request contract already requires ``finding.file == recipe.module_file``), or
    None when the snapshot has no such member.
    """
    if module_text is None:
        return TargetBindingFailure(
            TargetBindingReason.FILE_ABSENT, f"{finding.file} is absent from the admitted snapshot"
        )
    # A finding with no line can never be decisive (verdict-time target binding).
    if finding.line is None:
        return TargetBindingFailure(
            TargetBindingReason.LINE_MISSING,
            "finding declares no target line to bind the demonstration to",
        )
    line_count = _source_line_count(module_text)
    if finding.line > line_count:
        return TargetBindingFailure(
            TargetBindingReason.LINE_OUT_OF_RANGE,
            f"line {finding.line} is beyond the {line_count} lines of {finding.file}",
        )
    try:
        # The importer accepts a UTF-8 BOM in bytes; ast.parse of the decoded str does not.
        module = ast.parse(module_text.removeprefix("﻿"), filename=recipe.module_file)
    except (SyntaxError, ValueError) as exc:
        return TargetBindingFailure(
            TargetBindingReason.MODULE_UNPARSEABLE,
            f"{recipe.module_file} is not valid Python: {type(exc).__name__}",
        )
    except RecursionError:
        return None  # Too deep for this parser; the run-time gates decide.
    bindings = _bindings(module, recipe.function)
    if bindings is None:
        return None
    if not bindings:
        return TargetBindingFailure(
            TargetBindingReason.FUNCTION_NOT_DEFINED,
            f"{recipe.function} is not defined in {recipe.module_file}",
        )
    binding = bindings[0] if len(bindings) == 1 else None
    if (
        not isinstance(binding, (ast.FunctionDef, ast.AsyncFunctionDef))
        or binding not in module.body
        or binding.decorator_list
    ):
        return None  # Not one plain top-level def: the signature is not statically decidable.
    if isinstance(binding, ast.AsyncFunctionDef):
        return TargetBindingFailure(
            TargetBindingReason.FUNCTION_ASYNC,
            f"{recipe.function} is a coroutine function; the recipe calls it synchronously",
        )
    return _signature_failure(binding, recipe)
