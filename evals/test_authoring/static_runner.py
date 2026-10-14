"""Host-only development runner for authoring evals: parses the authored patch and executes nothing (SPEC-0044).

Model-written tests may run only in the qualified sandbox, so on the host the author's development loop is
answered by static discovery: a parse error or an import nothing could satisfy is a collection error, the node
ids are those pytest would collect from the patch files, and the real runner's rule applies (execution only
when exactly the two planned ids are found). Execution itself is simulated: the control is reported passed
and the security test failed, which the author never sees by default. Every observation is marked simulated
in the eval receipt; nothing here is evidence that the tests run or measure the planned behavior.

Minitest (`.rb`) and Jest (`.js`) files are discovered statically by ``languages.discover`` (ids through the
production assertion readers and a lexical scan; loading refused for an unreadable file or an unresolved
``require``), and a simulated security failure carries that framework's native assertion type. Java and Perl
test files are refused here; cases for them answer runs with injected observations.
"""

import ast
import sys
from uuid import UUID

from corsair.agents.source.contracts import SourceFile
from corsair.ports.test_runner import (
    JS_TEST_ID, RUBY_TEST_ID, ApprovedPatch, Discovery, Execution, FailureDetail, NativeTestRun, TestCaseResult,
)
from evals.test_authoring.languages import discover

TEST_PLUGINS = frozenset({"pytest", "_pytest"})
SIMULATED = ("static-host-runner", "not-executed")


def source_modules(files: tuple[SourceFile, ...]) -> frozenset[str]:
    """Top-level importable names the saved source provides from the workspace root."""
    names = set()
    for source in files:
        head = source.path.split("/")[0]
        names.add(head[:-3] if head.endswith(".py") else head)
    return frozenset(names)


def unresolved_imports(tree: ast.Module, available: frozenset[str]) -> list[str]:
    """Absolute imports whose top-level module is neither stdlib, the test framework nor saved source."""
    known = available | TEST_PLUGINS | sys.stdlib_module_names
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name.split(".")[0] not in known]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module \
                and node.module.split(".")[0] not in known:
            found.append(node.module)
    return found


def collected_ids(path: str, tree: ast.Module) -> list[str]:
    """pytest's default collection for an explicitly named file: test* functions and Test* classes without __init__."""
    ids = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            ids.append(f"{path}::{node.name}")
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test") and not any(
                isinstance(item, ast.FunctionDef) and item.name == "__init__" for item in node.body):
            ids += [f"{path}::{node.name}::{item.name}" for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test")]
    return ids


class StaticRunner:
    """TestRunner port double for host evals; raises for patches it cannot analyse rather than guessing."""

    def __init__(self, source_files: tuple[SourceFile, ...]):
        self.available = source_modules(source_files)
        self.paths = {source.path for source in source_files}

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID, witness=None) -> NativeTestRun:
        command = discovery_command + tuple(item.path for item in patch.files)
        ids, errors = [], []
        for item in patch.files:
            if not item.path.endswith(".py"):
                planned = tuple(test_id for test_id in (control_test_id, security_test_id)
                                if test_id.startswith(item.path + "::"))
                try:
                    content = item.content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    errors.append(f"E   {type(exc).__name__}: {exc} ({item.path})")
                    continue
                found, refused = discover(item.path, content, planned, self.paths, discovery_command)
                ids += found
                errors += [f"E   {error}" for error in refused]
                continue
            try:
                tree = ast.parse(item.content.decode("utf-8"), filename=item.path)
            except (SyntaxError, UnicodeDecodeError) as exc:
                errors.append(f"E   {type(exc).__name__}: {getattr(exc, 'msg', exc)} ({item.path}, line {getattr(exc, 'lineno', '?')})")
                continue
            missing = unresolved_imports(tree, self.available)
            if missing:
                errors.append(f"E   ModuleNotFoundError: No module named {missing[0]!r} ({item.path})")
            ids += collected_ids(item.path, tree)
        base = dict(operation=str(operation), patch_sha256=patch.sha256, workspace=None, cleanup="not_required")
        expected = {control_test_id, security_test_id}
        if errors or len(ids) != len(set(ids)) or set(ids) != expected:
            detail = "\n".join(errors) or f"collected {ids}, expected exactly {sorted(expected)}"
            discovery = Discovery("collection_error", () if errors else tuple(ids), detail, command, None)
            return NativeTestRun(**base, discovery=discovery, execution=None, failure_layer="discovery",
                                 detail=f"discovery (static): {detail}")
        # The framework's native assertion failure type: Minitest::Assertion, Jest's Error, pytest's AssertionError.
        native = ("Minitest::Assertion" if RUBY_TEST_ID.fullmatch(security_test_id)
                  else "Error" if JS_TEST_ID.fullmatch(security_test_id) else "AssertionError")
        failure = FailureDetail("failure", native, security_test_id.split("::")[0],
                                security_test_id.split("::")[-1], None, "simulated: not executed on the host")
        cases = (TestCaseResult(control_test_id, "passed", None, ""),
                 TestCaseResult(security_test_id, "failed", failure, ""))
        execution = Execution("completed", cases, None, None, "simulated: not executed on the host", SIMULATED, None)
        return NativeTestRun(**base, discovery=Discovery("discovered", tuple(ids), "", command, None),
                             execution=execution, failure_layer=None, detail="static host runner; execution simulated")
