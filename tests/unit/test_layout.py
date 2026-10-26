"""Package ownership checks, not interface-mirroring implementation tests."""

import ast
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

from corsair.contracts import PlanRevision, Submission

ROOT = Path(__file__).resolve().parents[2]


def imported_modules(path: Path) -> set[str]:
    """Return absolute import modules without importing the module under test."""

    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = ".".join(path.relative_to(ROOT / "src").parts[:-1])
                modules.add(resolve_name("." * node.level + (node.module or ""), package))
            elif node.module is not None:
                modules.add(node.module)
    return modules


def referenced_names(path: Path) -> set[str]:
    """Return names a module imports from anywhere or reads as a variable or attribute."""

    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def python_files(package: str) -> list[Path]:
    """Return source files for a package without deriving rules from file counts."""

    return sorted((ROOT / "src/corsair" / package).rglob("*.py"))


def imports_module(module: str, prefix: str) -> bool:
    """Match an import of a module or one of its children."""

    return module == prefix or module.startswith(f"{prefix}.")


def test_contracts_ports_and_workflows_do_not_load_execution_adapters():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import corsair.contracts
import corsair.ports.inference, corsair.ports.scm, corsair.ports.sandboxing
import corsair.policies
import corsair.workflows.investigation, corsair.workflows.evaluation
for name in ('google.adk', 'docker', 'litellm',
             'corsair.adapters.inference.adk', 'corsair.entrypoints.worker',
             'corsair.adapters.sandboxing.docker'):
    assert name not in sys.modules, name
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ports_depend_only_on_contracts_and_standard_library():
    for path in (ROOT / "src/corsair/ports").glob("*.py"):
        for module in imported_modules(path):
            if module.startswith("corsair."):
                assert module.startswith("corsair.contracts"), (path, module)


def test_contracts_ports_and_policies_are_free_of_native_sdk_imports():
    sdk_prefixes = ("docker", "google", "litellm", "temporalio")
    for package in ("contracts", "ports", "policies"):
        for path in python_files(package):
            for module in imported_modules(path):
                assert not any(imports_module(module, prefix) for prefix in sdk_prefixes), (
                    path,
                    module,
                )


def test_evaluation_does_not_depend_on_entrypoints():
    for path in python_files("evaluation"):
        assert not any(
            imports_module(module, "corsair.entrypoints") for module in imported_modules(path)
        ), path


def test_runtime_packages_never_reference_oracles_or_dataset_loaders():
    """Oracle and dataset schemas are canonical contracts; only evaluation/ may read them."""
    evaluator_only = {"Oracle", "Dataset", "DatasetEntry"}
    for package in ("agents", "steps", "adapters", "workflows"):
        for path in python_files(package):
            assert not any(
                imports_module(module, "corsair.evaluation") for module in imported_modules(path)
            ), path
            assert not referenced_names(path) & evaluator_only, path


@pytest.mark.parametrize("first", ["corsair.evaluation.intake", "corsair.evaluation.datasets"])
def test_intake_and_dataset_loaders_import_in_either_order(first):
    result = subprocess.run(
        [sys.executable, "-c", f"import {first}, corsair.evaluation.intake"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_agent_factories_do_not_depend_on_concrete_inference_adapters():
    factories = sorted((ROOT / "src/corsair/agents").glob("*/factory.py"))
    for path in factories:
        assert not any(
            imports_module(module, "corsair.adapters.inference")
            for module in imported_modules(path)
        ), path


def test_role_local_agent_layout_has_only_concrete_source_tools_and_native_toolsets():
    producer = ROOT / "src/corsair/agents/producer"
    auditor = ROOT / "src/corsair/agents/auditor"

    assert not (producer / "tools.py").exists()
    assert (producer / "tools/read_file.py").is_file()
    assert (producer / "tools/list_files.py").is_file()
    assert (producer / "toolsets.py").is_file()
    # The auditor is tool-free: no toolset module, no tools package.
    assert not (auditor / "toolsets.py").exists()
    assert not (auditor / "tools").exists()
    assert (producer / "contracts.py").is_file()
    assert (auditor / "contracts.py").is_file()


@pytest.mark.parametrize(
    "value", ["text", 7, 0.5, True, None, [1, {"nested": False}], {"a": [None]}]
)
def test_explicit_json_payload_types_preserve_all_supported_wire_values(value):
    submission = Submission(
        control_payload=value,
        exploit_payload=value,
        hypothesis="domain claim",
        plan=PlanRevision(revision=1, objective="check", next_steps=["probe"], reason="test"),
    )
    roundtrip = Submission.model_validate_json(submission.model_dump_json())
    assert type(roundtrip.control_payload) is type(value)
    assert roundtrip.control_payload == value
    schema = Submission.model_json_schema()
    assert "anyOf" in schema["properties"]["control_payload"]
    assert schema["$defs"]["PlanRevision"]["additionalProperties"] is False
