"""Authored-test admission: test code must not observe or replace what the operator witness observes.

The operator witness (SPEC-0033) installs its own audit hook and ``sys.monitoring`` tool around the
identified target, so a test that installs hooks, traces, forges audit events or patches the observed
facility re-implements or interferes with the oracle (PLAN-0039: a self-made hook made one security test
vacuous and broke another run's control). This is a deterministic Python AST check of what the file says,
not proof of behaviour: dynamic construction it cannot see stays possible, and the witness stays
tamper-evident, not tamper-proof.
"""

import ast
from hashlib import sha256

from .contracts import AdmissionFinding

# Interpreter facilities the witness uses or that would let test code see or steer what it sees.
SYS_FACILITIES = {"addaudithook", "audit", "monitoring", "settrace", "setprofile", "_getframe", "call_tracing"}
THREADING_FACILITIES = {"settrace", "setprofile", "settrace_all_threads", "setprofile_all_threads"}
# Modules whose import replaces, traces or reaches below the observed facilities.
MODULES = {"ctypes", "_testcapi", "_testinternalcapi", "tracemalloc", "trace", "bdb", "pdb", "unittest.mock", "mock",
           "pytest_mock", "builtins", "_io"}
# Facilities a patch would replace under the witness: file, process, network and import machinery.
PATCHED = {"builtins", "io", "_io", "os", "posix", "pathlib", "shutil", "subprocess", "socket", "importlib", "open"}
# Patch targets inside those roots that change inputs, not observation, and stay allowed; and sys.modules, whose
# patching swaps the imported target itself.
UNOBSERVED_TARGETS = {"os.environ"}
PATCHED_EXACT = {"sys.modules"}
PATCH_CALLS = {"setattr", "delattr", "setitem", "delitem", "patch"}
# Names whose string form is only useful to reach the facilities above dynamically.
NAMES = SYS_FACILITIES - {"audit", "monitoring"} | {"settrace_all_threads", "setprofile_all_threads", "__builtins__"}

# Operator-reviewed test bytes admitted as written: the SPEC-0018 pair observes opens itself because it
# predates the operator witness; it is the scripted control, never model output.
REVIEWED_SELF_OBSERVING = frozenset({"c9ce06213661ad5f9b97ac64ee7ade81895d7566e090d72837cecc7ff9f07673"})


def _bindings(tree: ast.Module, module: str) -> tuple[set[str], set[str]]:
    """Names bound to ``module`` itself and to its members anywhere in the file."""
    modules, members = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.asname or alias.name for alias in node.names if alias.name == module}
        elif isinstance(node, ast.ImportFrom) and node.module == module and not node.level:
            members |= {alias.asname or alias.name for alias in node.names}
    return modules, members


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *reversed(parts)])
    return None


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Each imported local name and the module path it is bound to: ``import socket as net`` binds net to socket."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bound


def _resolved(node: ast.AST, aliases: dict[str, str]) -> str | None:
    dotted = _dotted(node)
    if dotted is None:
        return None
    head, _, rest = dotted.partition(".")
    return ".".join(filter(None, (aliases.get(head, head), rest)))


def _unobserved(target: str | None) -> bool:
    return bool(target) and any(target == allowed or target.startswith(allowed + ".") for allowed in UNOBSERVED_TARGETS)


def _protected(target: str | None) -> bool:
    """A file, process, network or import facility, or sys.modules; environment inputs stay writable."""
    if not target or _unobserved(target):
        return False
    # Any component: documents.open and documents.subprocess.run reach the same facilities through the application.
    return any(part in PATCHED for part in target.split(".")) or any(target == exact or target.startswith(exact + ".")
                                                  for exact in PATCHED_EXACT)


def _key(target: ast.AST) -> str | None:
    """The constant name a subscript write rebinds: ``documents.__dict__['open'] = f`` rebinds open."""
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.slice.value
    return None


def _written(target: ast.AST) -> ast.AST | None:
    """The object an assignment or deletion writes into: ``io.open = f`` writes io.open, ``m['k'] = v`` writes m."""
    if isinstance(target, ast.Attribute):
        return target
    if isinstance(target, ast.Subscript):
        return target.value
    return None


def _imported(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level or node.module is None:
        return []
    return [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]


def self_observation(content: str) -> tuple[AdmissionFinding, ...]:
    """Every construct in ``content`` that observes, forges or replaces a witnessed facility, by line."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ()  # Native collection reports the syntax error; there is nothing to admit or refuse yet.
    if sha256(content.encode()).hexdigest() in REVIEWED_SELF_OBSERVING:
        return ()
    sys_modules, sys_members = _bindings(tree, "sys")
    threading_modules, threading_members = _bindings(tree, "threading")
    aliases = _aliases(tree)
    found: dict[tuple[int, str], None] = {}

    def refuse(node: ast.AST, construct: str) -> None:
        found[(getattr(node, "lineno", 1), construct)] = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _imported(node):
                if name in MODULES or name.split(".")[0] in MODULES - {"unittest.mock"}:
                    refuse(node, f"import {name}")
                if name in {f"sys.{facility}" for facility in SYS_FACILITIES} | {
                        f"threading.{facility}" for facility in THREADING_FACILITIES}:
                    refuse(node, f"import {name}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in sys_modules and node.attr in SYS_FACILITIES:
                refuse(node, f"sys.{node.attr}")
            elif node.value.id in threading_modules and node.attr in THREADING_FACILITIES:
                refuse(node, f"threading.{node.attr}")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in sys_members & SYS_FACILITIES or node.id in threading_members & THREADING_FACILITIES:
                refuse(node, node.id)
            elif node.id in {"__builtins__", "__import__"}:
                refuse(node, node.id)
        elif isinstance(node, ast.arg) and node.arg == "mocker":
            refuse(node, "mocker fixture")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in NAMES:
            refuse(node, f"string {node.value!r}")
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            # Direct writes and deletes: io.open = f, del os.system, sys.modules["x"] = m, sp.run += f.
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            verb = "delete" if isinstance(node, ast.Delete) else "assign"
            for target in targets:
                for element in (target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]):
                    written = _written(element)
                    resolved = _resolved(written, aliases) if written is not None else None
                    # As for patch calls, a module's own binding of a protected name is protected too:
                    # documents.open = f replaces the application's observed open as surely as builtins.open.
                    key = _key(element)
                    if _protected(resolved) or (key in PATCHED and not _unobserved(resolved)):
                        refuse(node, f"{verb} {resolved or key}")
        if isinstance(node, ast.Call):
            func = _dotted(node.func)
            name = func.rsplit(".", 1)[-1] if func else None
            if name in PATCH_CALLS:
                # monkeypatch.setattr(os, "open", f), setattr(builtins, ...), monkeypatch.setattr("builtins.open", f)
                # and a patch of any module's own "open" name.
                for argument in node.args[:2]:
                    patched = argument.value if isinstance(argument, ast.Constant) and isinstance(
                        argument.value, str) else _resolved(argument, aliases)
                    if _protected(patched):
                        refuse(node, f"{func}({patched})")
                        break
    return tuple(AdmissionFinding(line=line, facility=construct[:128]) for line, construct in sorted(found))


__all__ = ["REVIEWED_SELF_OBSERVING", "self_observation"]
