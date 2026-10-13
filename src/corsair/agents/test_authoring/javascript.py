"""Deterministic JavaScript facts about an authored Jest test: where it can fail on its own check.

esprima (ES2017 and earlier, the language Node 8 runs) gives the syntax tree; a file it cannot parse is refused as
unparseable, as Python's ``ast`` does for a Python test. Structure, not proof of test semantics.
"""

import esprima

from corsair.ports.test_runner import JsTestId

# Jest's test and suite functions as plain calls; `test.skip`, `test.only` and `test.each` are not a planned test.
TESTS = {"test", "it"}
SUITES = {"describe"}
FUNCTIONS = {"FunctionExpression", "ArrowFunctionExpression"}


def _parse(content: str):
    """A CommonJS script, else an ES module; the module's error is the one reported."""
    try:
        return esprima.parseScript(content, {"loc": True})
    except (esprima.Error, RecursionError):
        pass
    try:
        return esprima.parseModule(content, {"loc": True})
    except (esprima.Error, RecursionError) as exc:
        raise ValueError(f"test file does not parse: {str(exc)[:256]}") from exc


def _callback(statement, functions: set[str], title: str):
    """The function a top-level `name('title', fn)` statement registers, or None for any other statement."""
    if statement.type != "ExpressionStatement" or statement.expression.type != "CallExpression":
        return None
    call = statement.expression
    if (call.callee.type != "Identifier" or call.callee.name not in functions or len(call.arguments) < 2
            or call.arguments[0].type != "Literal" or call.arguments[0].value != title
            or call.arguments[1].type not in FUNCTIONS):
        return None
    return call.arguments[1]


def _one(statements, functions: set[str], title: str, test_id: str):
    found = [f for f in (_callback(s, functions, title) for s in statements) if f is not None]
    if not found:
        raise ValueError(f"{test_id} is not defined in its test file")
    if len(found) > 1:
        raise ValueError(f"{test_id} is defined more than once in its test file")
    return found[0]


def _statements(function):
    return function.body.body if function.body.type == "BlockStatement" else []


def _children(node):
    for value in vars(node).values():
        if isinstance(value, esprima.nodes.Node):
            yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, esprima.nodes.Node))


def _checks(function) -> set[int]:
    """Lines of `expect(...)` matcher calls and `assert` calls anywhere in the test callback.

    Nested functions count: a Jest test checks a promise's outcome inside the callback it returns or awaits.
    A matcher call spanning lines contributes each line, since the stack frame may name any of them.
    """
    lines: set[int] = set()
    pending = [function.body]
    while pending:
        node = pending.pop()
        if node.type == "CallExpression" and (_matcher(node.callee) or _assert(node.callee)):
            lines.update(range(node.loc.start.line, node.loc.end.line + 1))
        pending.extend(_children(node))
    return lines


def _matcher(callee) -> bool:
    """`expect(x).toBe(y)`, `expect(x).not.toBe(y)`, `expect(p).rejects.toThrow()`: a member chain on expect()."""
    if callee.type != "MemberExpression":
        return False
    node = callee.object
    while node.type == "MemberExpression":
        node = node.object
    return node.type == "CallExpression" and node.callee.type == "Identifier" and node.callee.name == "expect"


def _assert(callee) -> bool:
    """`assert(x)` and `assert.equal(a, b)`: Node's assert module, or chai's, bound to the name assert."""
    return (callee.type == "Identifier" and callee.name == "assert") or (
        callee.type == "MemberExpression" and callee.object.type == "Identifier" and callee.object.name == "assert")


def assertion_lines(content: str, test_id: str) -> tuple[int, ...]:
    """Lines where the named Jest test can fail on its own check: its expect matcher and assert calls."""
    test = JsTestId.parse(test_id)
    program = _parse(content)
    scope = program.body
    if test.suite:
        scope = _statements(_one(scope, SUITES, test.suite, test_id))
    lines = _checks(_one(scope, TESTS, test.name, test_id))
    if not lines:
        raise ValueError(f"{test_id} has no assertion")
    return tuple(sorted(lines))
