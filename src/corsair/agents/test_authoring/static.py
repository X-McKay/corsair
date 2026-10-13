"""Deterministic Python AST facts about authored tests; structure, not proof of test semantics."""

import ast

from corsair.ports.test_runner import RubyTestId

from .ruby import ruby_assertion_lines

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


def _executable(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Nodes the test body itself runs; nested functions, classes and lambdas run only if called."""
    deferred = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    nodes: list[ast.AST] = []
    pending: list[ast.AST] = [node for node in function.body if not isinstance(node, deferred)]
    while pending:
        node = pending.pop()
        nodes.append(node)
        pending.extend(child for child in ast.iter_child_nodes(node) if not isinstance(child, deferred))
    return nodes


def _pytest_raises(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Module-level bindings of pytest and of pytest.raises."""
    modules, names = set(), set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules |= {alias.asname or alias.name for alias in node.names if alias.name == "pytest"}
        elif isinstance(node, ast.ImportFrom) and node.module == "pytest" and not node.level:
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "raises"}
    return modules, names


def _checks(tree: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[int]:
    modules, names = _pytest_raises(tree)

    def raises(call: ast.expr) -> bool:
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        return (isinstance(func, ast.Attribute) and func.attr == "raises" and isinstance(func.value, ast.Name)
                and func.value.id in modules) or (isinstance(func, ast.Name) and func.id in names)

    return {node.lineno for node in _executable(function)
            if isinstance(node, ast.Assert) or (isinstance(node, (ast.With, ast.AsyncWith))
                                                and any(raises(item.context_expr) for item in node.items))}


def assertion_lines(content: str, test_id: str) -> tuple[int, ...]:
    """Lines where the named test can fail on its own check: assert statements and pytest.raises blocks it runs."""
    try:
        ruby = RubyTestId.parse(test_id)
    except ValueError:
        ruby = None
    if ruby is not None:
        lines = ruby_assertion_lines(content, ruby.class_name, ruby.method)
        if not lines:
            raise ValueError(f"{test_id} has no assertion")
        return lines
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise ValueError(f"test file does not parse: {exc.msg} at line {exc.lineno}") from exc
    lines = _checks(tree, _function(tree, test_id))
    if not lines:
        raise ValueError(f"{test_id} has no assertion")
    return tuple(sorted(lines))


def _name(node: ast.AST) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None


def static_checks(content: str, test_id: str, target_symbol: str) -> dict[str, bool]:
    """Structural evaluation facts; target calls exclude deferred bodies, without proving reachability or semantics."""
    try:
        tree = ast.parse(content)
        function = _function(tree, test_id)
    except (SyntaxError, ValueError):
        return {"parses_and_defines_test": False}
    nodes = list(ast.walk(tree))
    body = _executable(function)
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
        "has_assertion": bool(_checks(tree, function)),
    }
