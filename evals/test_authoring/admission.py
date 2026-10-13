"""Deterministic admission facts about an authored patch, scored by the eval only (SPEC-0044).

Structure, not proof of test semantics: they flag patches that could not be valid evidence whatever
they would do when executed. The audit-hook rule belongs to the authoring stage's own admission check
(the "author stays out of the witness" work, PLAN-0047 on its own branch) and is not duplicated here.
"""

import ast
import re

from corsair.agents.test_authoring.static import _function
from corsair.agents.test_planning.contracts import ReadyTestPlan

PROCESS_OR_NETWORK = frozenset({"subprocess", "socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
                                "ftplib", "smtplib", "telnetlib", "ctypes", "multiprocessing", "pty"})
OS_PROCESS_CALLS = frozenset({"system", "popen", "spawnl", "spawnv", "execv", "execve", "execl", "fork", "startfile"})
QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def quoted_literals(text: str) -> set[str]:
    return {single or double for single, double in QUOTED.findall(text)}


def _strings(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def no_process_or_network(content: str) -> bool:
    """No process creation, raw network or foreign-function use anywhere in the file."""
    for node in ast.walk(ast.parse(content)):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in PROCESS_OR_NETWORK for a in node.names):
            return False
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in PROCESS_OR_NETWORK:
            return False
        if isinstance(node, ast.Attribute) and node.attr in OS_PROCESS_CALLS and isinstance(node.value, ast.Name) \
                and node.value.id == "os":
            return False
    return True


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
        # The planned adversarial value reaches only the security test.
        facts["planned_input_in_security"] = all(any(value in s for s in _strings(security)) for value in adversarial)
        facts["planned_input_not_in_control"] = not any(value in s for value in adversarial for s in _strings(control))
    if plan.security_expectation.failure_type == "AssertionError":
        # Decision recorded with authoring v5: the planned failure is a plain assert, not pytest.raises.
        asserts = {n.lineno for n in ast.walk(security) if isinstance(n, ast.Assert)}
        facts["planned_failure_is_assert"] = bool(security_lines) and set(security_lines) <= asserts
    return facts
