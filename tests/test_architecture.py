"""Executable architecture constraints, not just a directory diagram."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from corsair.adapters.frameworks.pytest_ import Pytest
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel
from corsair.domain.artifacts import ArtifactRef
from corsair.domain.verification import Gate, GateVerdict
from corsair.ports.artifacts import Artifacts
from corsair.runtime import matrix
from tests.fakes import FakeSandboxes
from tests.test_kernel import CASE, REFERENCE, ROW

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/corsair"


def _imports(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("layer", ["domain", "application", "agents", "ports", "runtime"])
def test_inner_layers_do_not_import_concrete_adapters(layer):
    for path in (SOURCE / layer).rglob("*.py"):
        assert not any(name.startswith("corsair.adapters") for name in _imports(path)), path


def test_domain_does_not_depend_on_application_agents_or_runtime():
    for path in (SOURCE / "domain").rglob("*.py"):
        assert not any(
            name.startswith(("corsair.application", "corsair.agents", "corsair.runtime", "corsair.ports"))
            for name in _imports(path)
        ), path


def test_ports_do_not_depend_on_concrete_or_application_services():
    for path in (SOURCE / "ports").rglob("*.py"):
        assert not any(
            name.startswith(("corsair.application", "corsair.agents", "corsair.adapters"))
            for name in _imports(path)
        ), path


def test_agents_do_not_import_application_orchestration():
    for path in (SOURCE / "agents").rglob("*.py"):
        assert not any(name.startswith("corsair.application") for name in _imports(path)), path


def test_old_flat_implementation_modules_are_not_retained_as_shims():
    for name in [
        "producer.py",
        "auditor.py",
        "providers.py",
        "seed.py",
        "kernel.py",
        "case.py",
        "artifacts.py",
        "matrix.py",
    ]:
        assert not (SOURCE / name).exists(), name
    assert not (SOURCE / "sandbox").exists()
    assert not (SOURCE / "frameworks").exists()


class MemoryArtifacts:
    def __init__(self):
        self.contents = {}

    def put(self, data: bytes) -> ArtifactRef:
        digest = hashlib.sha256(data).hexdigest()
        self.contents[digest] = data
        return ArtifactRef(uri=f"memory://{digest}", sha256=digest, size=len(data))

    def ref(self, sha256: str) -> ArtifactRef | None:
        return self.put(self.contents[sha256]) if sha256 in self.contents else None

    def get(self, ref: ArtifactRef) -> bytes:
        return self.contents[ref.sha256]


@pytest.mark.anyio
async def test_kernel_uses_the_injected_framework_without_selecting_an_adapter():
    class DeniedFramework(Pytest):
        def guard(self, probe):
            return GateVerdict(passed=False, stage=Gate.AST_GUARD, reason="injected guard")

    backend = FakeSandboxes({})
    artifacts = MemoryArtifacts()
    assert isinstance(artifacts, Artifacts)
    injected = DeniedFramework()
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=artifacts, framework=injected)
    assert kernel.framework is injected
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.reason == "injected guard"
    assert not backend.creates


def test_kernel_refuses_framework_runtime_mismatch():
    class WrongFramework(Pytest):
        name = "not-selected"

    with pytest.raises(ValueError, match="does not match"):
        Kernel(
            FakeSandboxes({}), ROW, load_case(CASE), artifacts=MemoryArtifacts(), framework=WrongFramework()
        )


def test_runtime_matrix_is_package_relative_and_root_link_has_one_owner():
    assert matrix.DEFAULT_MATRIX == SOURCE / "runtime/runtime-matrix.yaml"
    assert (ROOT / "matrix.yaml").resolve() == matrix.DEFAULT_MATRIX
    assert len(matrix.load()) == 7


def test_agent_layout_preserves_original_producer_and_auditor_instruction_bytes():
    from corsair.agents.auditor.agent import instructions as auditor_instructions
    from corsair.agents.producer.agent import instructions as producer_instructions

    assert (
        hashlib.sha256(producer_instructions().encode()).hexdigest()
        == "875253ef4b506bc24b93c4d54583d8c9cd6f97a6ff1a85aa779278fe17c4bff8"
    )
    assert (
        hashlib.sha256(auditor_instructions().encode()).hexdigest()
        == "f6a4e03bad8cffe3482220786282ba0b8b9292e250780f3fb45c691c317c8dd1"
    )


def test_every_agent_has_a_spec_and_instruction_resources():
    for name in ["producer", "auditor", "bug_seeder", "skill_crystallizer"]:
        package = SOURCE / "agents" / name
        assert (package / "agent.py").is_file()
        assert (package / "agent.yaml").is_file()
        assert (package / "instructions/system.md").is_file()
    assert not (SOURCE / "agents/auditor/tools").exists()
    assert not (SOURCE / "agents/auditor/skills").exists()


def test_producer_skills_are_portable_packages_not_a_flat_markdown_catalog():
    import yaml

    skills = SOURCE / "agents/producer/skills"
    assert not list(skills.glob("*.md"))
    packages = list(skills.glob("*/SKILL.md"))
    assert len(packages) == 10
    for path in packages:
        prefix, metadata, body = path.read_text().split("---", 2)
        assert not prefix.strip()
        info = yaml.safe_load(metadata)
        assert info["name"] == path.parent.name
        assert info["description"]
        assert body.strip()


def test_imports_are_passive_and_factories_do_not_contact_external_services(monkeypatch):
    import importlib
    import socket
    import subprocess

    from pydantic_ai.models.test import TestModel

    def denied(*args, **kwargs):
        raise AssertionError("unexpected import/factory side effect")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    modules = [
        "corsair.agents.producer.agent",
        "corsair.agents.auditor.agent",
        "corsair.agents.bug_seeder.agent",
        "corsair.agents.skill_crystallizer.agent",
        "corsair.adapters.inference.openai",
        "corsair.adapters.scm.git",
        "corsair.cli",
    ]
    with monkeypatch.context() as files:
        files.setattr(Path, "read_text", denied)
        files.setattr(Path, "read_bytes", denied)
        for name in modules:
            importlib.reload(importlib.import_module(name))
    from corsair.adapters.inference.openai import OpenAIInference
    from corsair.adapters.scm.git import GitSCM
    from corsair.agents.auditor.agent import build_auditor
    from corsair.agents.bug_seeder.agent import build_bug_seeder
    from corsair.agents.producer.agent import build_producer
    from corsair.agents.skill_crystallizer.agent import build_skill_crystallizer
    from corsair.ports.sandbox import Sandboxes

    assert build_producer(TestModel()).name == "producer"
    assert build_auditor(TestModel()).name == "auditor"
    assert build_bug_seeder(TestModel()).name == "bug-seeder"
    assert build_skill_crystallizer(TestModel()).name == "skill-crystallizer"
    assert OpenAIInference()
    assert GitSCM()
    assert isinstance(FakeSandboxes({}), Sandboxes)
