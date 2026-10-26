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
    docstrings = {
        id(docstring)
        for node in ast.walk(module)
        if isinstance(node, _Owner) and (docstring := _docstring(node)) is not None
    }
    starts: set[int] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.stmt) and id(node) not in docstrings and not _uncompiled(node):
            starts.add(node.lineno)
        if isinstance(node, (_FunctionNode, ast.ClassDef)):
            starts.update(decorator.lineno for decorator in node.decorator_list)
        elif isinstance(node, ast.ExceptHandler):
            starts.add(node.lineno)
        elif isinstance(node, ast.match_case):
            starts.add(node.pattern.lineno)
    return starts


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
