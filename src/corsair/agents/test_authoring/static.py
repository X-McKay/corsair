"""Deterministic Python AST facts about authored tests; structure, not proof of test semantics."""

import ast

SKIP_NAMES = {"skip", "skipif", "xfail", "importorskip"}
MOCK_MODULES = {"mock", "unittest.mock", "pytest_mock"}


def _function(tree: ast.Module, test_id: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    names = test_id.split("::")[1:]
    scope: list[ast.stmt] = tree.body
    for depth, name in enumerate(names):
        last = depth == len(names) - 1
        kinds = (ast.FunctionDef, ast.AsyncFunctionDef) if last else (ast.ClassDef,)
        node = next((n for n in scope if isinstance(n, kinds) and n.name == name), None)
        if node is None:
            raise ValueError(f"{test_id} is not defined in its test file")
        if last:
            return node
        scope = node.body
    raise ValueError(f"{test_id} names no test function")


def assertion_lines(content: str, test_id: str) -> tuple[int, ...]:
    """Lines where the named test can fail on its own check: assert statements and pytest.raises blocks."""
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise ValueError(f"test file does not parse: {exc.msg} at line {exc.lineno}") from exc
    lines = set()
    for node in ast.walk(_function(tree, test_id)):
        if isinstance(node, ast.Assert):
            lines.add(node.lineno)
        elif isinstance(node, (ast.With, ast.AsyncWith)) and any(
                isinstance(item.context_expr, ast.Call) and _name(item.context_expr.func) == "raises"
                for item in node.items):
            lines.add(node.lineno)
    if not lines:
        raise ValueError(f"{test_id} has no assertion")
    return tuple(sorted(lines))


def _name(node: ast.AST) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None


def static_checks(content: str, test_id: str, target_symbol: str) -> dict[str, bool]:
    """Evaluation facts for one test: calls the planned target, no mocks, skips, swallowing or constant asserts."""
    try:
        tree = ast.parse(content)
        function = _function(tree, test_id)
    except (SyntaxError, ValueError):
        return {"parses_and_defines_test": False}
    nodes = list(ast.walk(tree))
    body = list(ast.walk(function))
    return {
        "parses_and_defines_test": True,
        "calls_target": any(isinstance(n, ast.Call) and _name(n.func) == target_symbol for n in body),
        "no_mock": not any(
            (isinstance(n, ast.Import) and any(a.name in MOCK_MODULES for a in n.names))
            or (isinstance(n, ast.ImportFrom) and (n.module in MOCK_MODULES or any(
                f"{n.module}.{a.name}" in MOCK_MODULES for a in n.names)))
            or (isinstance(n, ast.arg) and n.arg in {"monkeypatch", "mocker"})
            or (isinstance(n, ast.Call) and _name(n.func) in {"patch", "setattr"})
            for n in nodes),
        "no_skip": not any(isinstance(n, (ast.Attribute, ast.Name)) and _name(n) in SKIP_NAMES for n in nodes),
        "no_swallowing_except": not any(
            isinstance(n, ast.ExceptHandler) and (n.type is None or _name(n.type) in {"Exception", "BaseException"})
            for n in nodes),
        "no_constant_assert": not any(isinstance(n, ast.Assert) and isinstance(n.test, ast.Constant) for n in nodes),
        "has_assertion": any(isinstance(n, ast.Assert) for n in body) or any(
            isinstance(n, (ast.With, ast.AsyncWith)) and any(
                isinstance(i.context_expr, ast.Call) and _name(i.context_expr.func) == "raises" for i in n.items)
            for n in body),
    }
