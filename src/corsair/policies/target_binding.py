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


def _parse(module_text: str, filename: str) -> ast.Module:
    # The importer accepts a UTF-8 BOM in bytes; ast.parse of the decoded str does not.
    return ast.parse(module_text.removeprefix("\ufeff"), filename=filename)


def _plain_top_level_def(module: ast.Module, name: str) -> ast.FunctionDef | None:
    """The one undecorated, synchronous top-level ``def`` binding ``name``, else None."""
    bindings = _bindings(module, name)
    if bindings is None or len(bindings) != 1:
        return None
    binding = bindings[0]
    if (
        not isinstance(binding, ast.FunctionDef)
        or binding not in module.body
        or binding.decorator_list
    ):
        return None
    return binding


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _compiles_to_nothing(statement: ast.stmt) -> bool:
    """Declarations that emit no bytecode, so their line never executes."""
    return isinstance(statement, (ast.Global, ast.Nonlocal)) or (
        isinstance(statement, ast.AnnAssign) and statement.value is None
    )


def derive_target_line(recipe: Recipe, module_text: str) -> int | None:
    """Bind a line-less finding to the recipe function's first body statement.

    Trusted, deterministic and model-free: the line comes from the operator-owned
    ``recipe.function`` and the admitted module text only, never from a finding's
    description or any scanner narrative. The ``def`` line itself is never chosen:
    the module import executes it, so its coverage would not show the call ran. A
    leading docstring, ``global``/``nonlocal`` and bare annotations are skipped:
    they emit no line event of their own.

    Returns None -- leaving the finding line-less, so ``target_binding`` reports
    ``line_missing`` -- unless the function is exactly one plain top-level ``def``
    whose first executable statement starts its own source line after the
    signature (a one-line ``def f(): return x`` shares the import-time line).
    """
    try:
        module = _parse(module_text, recipe.module_file)
    except (SyntaxError, ValueError, RecursionError):
        return None
    function = _plain_top_level_def(module, recipe.function)
    if function is None:
        return None
    first = next(
        (
            statement
            for index, statement in enumerate(function.body)
            if not (index == 0 and _is_docstring(statement)) and not _compiles_to_nothing(statement)
        ),
        None,
    )
    if first is None:
        return None  # No statement of the body has a line event of its own to bind.
    lines = module_text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    source_line = lines.split("\n")[first.lineno - 1].encode("utf-8")
    if first.lineno <= function.lineno or source_line[: first.col_offset].strip():
        return None  # The statement shares a line with the signature.
    return first.lineno


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
    # Prepare already bound one from the recipe function where that is certain
    # (derive_target_line), so a line-less finding here is one it could not bind.
    if finding.line is None:
        return TargetBindingFailure(
            TargetBindingReason.LINE_MISSING,
            "finding declares no target line to bind the demonstration to, and none "
            f"could be derived from recipe function {recipe.function}",
        )
    line_count = _source_line_count(module_text)
    if finding.line > line_count:
        return TargetBindingFailure(
            TargetBindingReason.LINE_OUT_OF_RANGE,
            f"line {finding.line} is beyond the {line_count} lines of {finding.file}",
        )
    try:
        module = _parse(module_text, recipe.module_file)
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
