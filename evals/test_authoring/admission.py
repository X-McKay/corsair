"""Deterministic admission facts about an authored patch, scored by the eval only (SPEC-0044).

Structure, not proof of test semantics: they flag patches that could not be valid evidence whatever
they would do when executed. The audit-hook rule belongs to the authoring stage's own admission check
(the "author stays out of the witness" work, PLAN-0047 on its own branch) and is not duplicated here.
"""

import ast
import re

from corsair.agents.test_authoring.static import _executable, _function
from corsair.agents.test_planning.contracts import ReadyTestPlan

PROCESS_OR_NETWORK = frozenset({"subprocess", "socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
                                "ftplib", "smtplib", "telnetlib", "ctypes", "multiprocessing", "pty", "importlib",
                                "runpy", "asyncio", "concurrent"})
# Dynamic forms that could reach any of the above without a visible import.
DYNAMIC_CALLS = frozenset({"__import__", "eval", "exec", "compile", "getattr"})
OS_PROCESS_CALLS = frozenset({"system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe",
                                "spawnv", "spawnve", "spawnvp", "spawnvpe",
                                "posix_spawn", "posix_spawnp", "execv", "execve", "execvp", "execvpe",
                                "execl", "execle", "execlp", "execlpe", "fork", "forkpty", "startfile"})
QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def quoted_literals(text: str) -> set[str]:
    return {single or double for single, double in QUOTED.findall(text)}


def _strings(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [n.value for n in _executable(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def no_process_or_network(content: str) -> bool:
    """No process creation, raw network or foreign-function use anywhere in the file.

    os process calls are refused through any binding of os (``import os as x``) and when imported by name
    (``from os import system``), not only as the literal ``os.system``; dynamic imports, eval/exec/compile
    and getattr are refused outright, since they could reach any of these without a visible import.
    """
    tree = ast.parse(content)
    os_names = {"os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in PROCESS_OR_NETWORK for a in node.names):
                return False
            os_names |= {a.asname for a in node.names if a.name == "os" and a.asname}
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if node.module.split(".")[0] in PROCESS_OR_NETWORK:
                return False
            if node.module == "os" and any(a.name in OS_PROCESS_CALLS or a.name == "*" for a in node.names):
                return False
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DYNAMIC_CALLS
           for node in ast.walk(tree)):
        return False
    return not any(isinstance(node, ast.Attribute) and node.attr in OS_PROCESS_CALLS
                   and isinstance(node.value, ast.Name) and node.value.id in os_names for node in ast.walk(tree))


WITNESS_HOOKS = frozenset({"addaudithook", "settrace", "setprofile", "monitoring"})


def witness_hooks(content: str) -> int:
    """Author-written audit, trace or monitoring hooks: the live failure mode where the author builds its own
    witness. Counted, not asserted, because the reviewed realization in today's cases installs one; the
    authoring stage's own admission rule decides what is refused."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 0
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in WITNESS_HOOKS
               and isinstance(n.value, ast.Name) and n.value.id == "sys")


def admission_facts(plan: ReadyTestPlan, files: dict[str, str], security_lines: tuple[int, ...]) -> dict[str, bool]:
    """Facts for a patch output; a fact whose plan premise is absent is omitted, not passed."""
    control_file, security_file = files.get(plan.control.test_path, ""), files.get(plan.security.test_path, "")
    try:
        control = _function(ast.parse(control_file), plan.control.test_id)
        security_tree = ast.parse(security_file)
        security = _function(security_tree, plan.security.test_id)
    except (SyntaxError, ValueError):
        return {"admission_parses": False}
    facts = {"no_process_or_network": all(no_process_or_network(content) for content in files.values())}
    adversarial = quoted_literals(plan.security.input) - quoted_literals(plan.control.input)
    if adversarial:
        # The literal occurs in the security body outside deferred scopes; this does not prove dataflow.
        facts["planned_input_in_security"] = all(any(value in s for s in _strings(security)) for value in adversarial)
        facts["planned_input_not_in_control"] = not any(value in s for value in adversarial for s in _strings(control))
    if plan.security_expectation.failure_type == "AssertionError":
        # Decision recorded with authoring v5: the planned failure is a plain assert, not pytest.raises.
        asserts = {n.lineno for n in _executable(security) if isinstance(n, ast.Assert)}
        facts["planned_failure_is_assert"] = bool(security_lines) and set(security_lines) <= asserts
    return facts
