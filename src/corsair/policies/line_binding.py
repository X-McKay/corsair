"""Bind a declared finding line to the line coverage can report for it. Pure.

The kernel's coverage gate requires one exact line to execute in both runs, and
coverage.py reports execution per logical line (one tokenizer NEWLINE-terminated
line, however many physical lines it spans), at that line's first physical line,
and never reports a docstring. A declared line that continues a multi-line
statement, or lies in a docstring, is therefore never reported, and a session bound
to it could only ever be INCONCLUSIVE. This module chooses, in code and before any
model call, the one reportable line the declared line belongs to:

- A function's ``def``/``async def`` header (its decorators, signature continuation
  lines and interior comments) or its docstring binds to the first statement of
  the body, skipping the docstring and ``global``/``nonlocal`` declarations, which
  compile to nothing. The ``def`` and decorator lines themselves run when the
  enclosing scope runs (at import, for a top-level function) whether or not the
  function is ever called, so this binding asks for more than the declared line:
  that the body was entered.
- Any other continuation line of a multi-line logical line (a statement, a compound
  header such as ``if``/``with``/``class``, an ``except`` or ``case`` clause, a
  decorator, or statements joined by ``;``) binds to that logical line's first
  line, provided that line starts a statement, decorator or clause coverage reports.
- Except that a continuation line holding any part of a subexpression that can be
  skipped while its statement runs is kept, whichever rule above would bind it:
  ``and``/``or`` operands after the first, a conditional expression's two branches,
  chained-comparison operands after the first comparison, a lambda body, everything
  in a comprehension or generator but its first iterable, an ``assert`` message, a
  ``for`` target, and a ``case`` pattern or guard. Coverage reports the statement's
  first line whether or not that part ran, so binding it would call an unexecuted
  line covered. coverage.py never reports the kept line, so the session stays
  INCONCLUSIVE. (A line that starts its logical line is outside this exception: it
  is already the line coverage reports, and a ``def`` or decorator line binds to the
  body, which asks for more than the line itself.)
- Every other line is kept: a line that already starts its logical line, a module or
  class docstring, a ``global``/``nonlocal`` or annotation-only declaration, a comment
  or blank line between statements, the ``else:``/``finally:`` keyword lines, a
  one-line ``def``, a function body that holds only a docstring or begins with an
  annotation-only declaration, and a module that does not parse or tokenize. A kept
  line that coverage cannot report still ends INCONCLUSIVE, as before.

The gate is unchanged: it still demands exact coverage of one line in both runs;
only which line is decided here, deterministically, from the admitted module text.
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
_Owner = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
_NON_CODE = frozenset(
    {
        tokenize.NL,
        tokenize.COMMENT,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)


@dataclass(frozen=True)
class _LogicalLines:
    """The tokenizer's logical lines, which coverage.py reports at their first line."""

    first: dict[int, int]  # every physical line of a logical line -> its first line
    last: dict[int, int]  # a logical line's first line -> its last line

    @classmethod
    def of(cls, text: str) -> _LogicalLines:
        first: dict[int, int] = {}
        last: dict[int, int] = {}
        start: int | None = None
        for token in tokenize.generate_tokens(io.StringIO(text, newline=None).readline):
            if start is None:
                if token.type in _NON_CODE:
                    continue
                start = token.start[0]
            if token.type == tokenize.NEWLINE:
                end = token.start[0]
                first.update(dict.fromkeys(range(start, end + 1), start))
                last[start] = end
                start = None
        return cls(first, last)


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _docstring(owner: _Owner) -> ast.stmt | None:
    return owner.body[0] if owner.body and _is_docstring(owner.body[0]) else None


def _spans(node: ast.stmt, line: int) -> bool:
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return node.lineno <= line <= end


def _uncompiled(node: ast.stmt) -> bool:
    """Statements that compile to no line coverage reports (or may not): never targets."""
    return isinstance(node, (ast.Global, ast.Nonlocal)) or (
        isinstance(node, ast.AnnAssign) and node.value is None
    )


def _first_body_statement(function: _FunctionNode, line: int, logical: _LogicalLines) -> int:
    """The first line coverage reports once the function is entered, else ``line``."""
    docstring = _docstring(function)
    for statement in function.body[1:] if docstring is not None else function.body:
        if isinstance(statement, (ast.Global, ast.Nonlocal)):
            continue
        if _uncompiled(statement):
            return line  # An annotation-only declaration: not decidable here.
        # A body sharing the header's logical line (a one-line def) has no line of its own.
        return statement.lineno if logical.first.get(statement.lineno) == statement.lineno else line
    return line  # Only a docstring: nothing in the body is a reportable statement.


def _function_header(function: _FunctionNode, line: int, logical: _LogicalLines) -> bool:
    """Whether ``line`` is a decorator, signature or docstring line of ``function``."""
    start = min(
        (decorator.lineno for decorator in function.decorator_list), default=function.lineno
    )
    end = logical.last.get(logical.first.get(function.lineno, function.lineno), function.lineno)
    docstring = _docstring(function)
    return start <= line <= end or (docstring is not None and _spans(docstring, line))


def _reportable_starts(module: ast.Module) -> set[int]:
    """First lines coverage reports: statements, decorators, ``except`` and ``case`` lines."""
    return _starts(module, ast.walk(module))


def _import_time_nodes(module: ast.Module) -> Iterator[ast.AST]:
    """Every node the import itself runs: the module and class bodies, never a function body.

    A ``def`` or ``lambda`` runs its decorators, defaults and annotations where it stands,
    but its body only when called; a class body runs where the class statement stands.
    """
    pending: list[ast.AST] = [module]
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, _FunctionNode):
            pending.extend(node.decorator_list)
            pending.append(node.args)
            if node.returns is not None:
                pending.append(node.returns)
        elif isinstance(node, ast.Lambda):
            pending.append(node.args)
        else:
            pending.extend(ast.iter_child_nodes(node))


def _starts(module: ast.Module, nodes: Iterable[ast.AST]) -> set[int]:
    """The reportable first lines of ``nodes`` (statements, decorators, clauses)."""
    docstrings = {
        id(docstring)
        for node in ast.walk(module)
        if isinstance(node, _Owner) and (docstring := _docstring(node)) is not None
    }
    starts: set[int] = set()
    for node in nodes:
        if isinstance(node, ast.stmt) and id(node) not in docstrings and not _uncompiled(node):
            starts.add(node.lineno)
        if isinstance(node, (_FunctionNode, ast.ClassDef)):
            starts.update(decorator.lineno for decorator in node.decorator_list)
        elif isinstance(node, ast.ExceptHandler):
            starts.add(node.lineno)
        elif isinstance(node, ast.match_case):
            starts.add(node.pattern.lineno)
    return starts


def _lines(node: ast.AST) -> range:
    start = getattr(node, "lineno", None)
    if start is None:
        return range(0)
    end = getattr(node, "end_lineno", None)
    return range(start, (end if end is not None else start) + 1)


def _skippable_parts(node: ast.AST) -> list[ast.AST]:
    """Subexpressions that may not run when the statement that holds them runs."""
    if isinstance(node, ast.BoolOp):
        return list(node.values[1:])  # Short-circuit: ``a or b``, ``a and b``.
    if isinstance(node, ast.IfExp):
        return [node.body, node.orelse]  # Only the test always runs.
    if isinstance(node, ast.Compare):
        return list(node.comparators[1:])  # ``a < b < c`` stops at the first false link.
    if isinstance(node, ast.Lambda):
        return [node.body]  # Runs only when called; the defaults run at definition.
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        # Only the first iterable is evaluated unconditionally (eagerly, even for a
        # generator); everything else runs per element, and possibly never.
        first, *rest = node.generators
        elements = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        return [*elements, first.target, *first.ifs, *rest]
    if isinstance(node, ast.Assert):
        return [] if node.msg is None else [node.msg]  # Evaluated only on failure.
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [node.target]  # Assigned per item: never on an empty iterable.
    if isinstance(node, ast.match_case):
        guard = [] if node.guard is None else [node.guard]
        return [node.pattern, *guard]  # Sub-patterns and the guard can be skipped.
    return []


def _skippable_lines(module: ast.Module) -> frozenset[int]:
    """Physical lines that hold any part of a subexpression that can be skipped.

    coverage.py reports a multi-line logical line at its first line whenever the
    statement starts, whether or not a short-circuit, conditional or lazy part on a
    later line ran, so such a line must never be bound to that first line.
    """
    return frozenset(
        line
        for node in ast.walk(module)
        for part in _skippable_parts(node)
        for line in _lines(part)
    )


def bind_target_line(module_text: str, line: int) -> int:
    """Return the statement line coverage reports for declared ``line``, or ``line``.

    ``module_text`` is the recipe module read from the admitted snapshot. The result
    is ``line`` itself whenever the rule in this module's docstring does not
    certainly choose another line.
    """
    # The importer accepts a UTF-8 BOM in bytes; ast.parse of the decoded str does not.
    text = module_text.removeprefix("\ufeff")
    try:
        module = ast.parse(text)
        logical = _LogicalLines.of(text)
    except (SyntaxError, ValueError, RecursionError, tokenize.TokenError):
        return line
    if logical.first.get(line, line) != line and line in _skippable_lines(module):
        return line  # Coverage never reports it, and its statement can run without it.
    for node in ast.walk(module):
        if isinstance(node, _FunctionNode) and _function_header(node, line, logical):
            return _first_body_statement(node, line, logical)
    for node in ast.walk(module):
        if isinstance(node, (ast.Module, ast.ClassDef)):
            docstring = _docstring(node)
            if docstring is not None and _spans(docstring, line):
                return line  # coverage.py never reports a module or class docstring.
    start = logical.first.get(line, line)
    return start if start in _reportable_starts(module) else line


def runs_at_import(module_text: str, line: int) -> bool:
    """Whether coverage reports bound ``line`` when the module is merely imported.

    ``line`` is the bound target line (``bind_target_line``). True when it starts a
    statement, decorator or clause whose innermost enclosing scope is the module or a
    class body reached from it, so the import executes it whatever the recipe call
    did and its coverage in both runs shows nothing about that call. A line in any
    function body (the entry, a helper it calls, a nested function or a class defined
    inside a function) runs only when called and is never import-time here; neither is
    a line coverage never reports, nor anything in a module that does not parse.
    """
    try:
        module = ast.parse(module_text.removeprefix("\ufeff"))
    except (SyntaxError, ValueError, RecursionError):
        return False
    return line in _starts(module, _import_time_nodes(module))
