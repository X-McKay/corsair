from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, WorkspaceRef as NativeWorkspaceRef
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from corsair.v2.agents import AgentDeps, SourceWorkspaceCapability, build_agents, cleanup_source_workspace, prepare_source_workspace
from corsair.v2.contracts import AnalysisInput, ModelProfile, OperatorConfig, SandboxProfile
from corsair.v2.runtime import _capture_analysis_input, run_agent
from corsair.v2.storage import Store


def _config(tmp_path: Path) -> OperatorConfig:
    return OperatorConfig(
        storage_root=str(tmp_path / "store"),
        default_model=ModelProfile(model="test"),
        sandbox=SandboxProfile(image="example@sha256:" + "a" * 64, policy_path="/operator/policy.yaml"),
    )


def _workspace(config: OperatorConfig):
    store = Store(config.storage_root)
    snapshot = _capture_analysis_input(AnalysisInput(files={"app.py": "def f():\n    return 1\n"}), store)
    ref = prepare_source_workspace(snapshot, config)
    deps = AgentDeps(run_id="run-1", stage_id="analysis", source_manifest=snapshot.manifest, workspace_ref=ref)
    return snapshot, ref, deps


def test_fixed_manifests_build_all_roles_and_durable_variants(tmp_path: Path) -> None:
    config = _config(tmp_path)
    direct = build_agents(config, model_override=TestModel(call_tools=[]))
    durable = build_agents(config, durable=True, model_override=TestModel(call_tools=[]))
    assert set(direct) == {"analysis", "investigator", "control_author", "exploit_author", "validity", "repair"}
    assert [agent.name for agent in direct.values()] == [f"corsair.v2.{role}.v1" for role in direct]
    assert set(durable) == set(direct)
    manifests = Path("src/corsair/v2/agents/roles")
    assert all((manifests / role / "agent.yaml").is_file() for role in direct)


def test_workspace_ref_is_manifest_pinned_and_denies_host_path_escape(tmp_path: Path) -> None:
    config = _config(tmp_path)
    snapshot, ref, deps = _workspace(config)

    async def check() -> None:
        workspace = SourceWorkspaceCapability(config.storage_root).get_workspace(
            SimpleNamespace(deps=deps), ref=NativeWorkspaceRef(provider="corsair-source", id=ref.id)
        )
        assert await workspace.read_text("source/app.py") == "def f():\n    return 1\n"
        for path in ("/etc/passwd", "../records.sqlite3", "operator-skills/../../records.sqlite3"):
            with pytest.raises(PermissionError):
                await workspace.read_text(path)
    try:
        asyncio.run(check())
    finally:
        cleanup_source_workspace(ref, config)


def test_native_filesystem_refuses_outside_and_secret_read_attempts(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _, ref, deps = _workspace(config)

    async def one(path: str) -> None:
        calls = 0

        def respond(messages, info):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(parts=[ToolCallPart("read_file", {"path": path})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "prediction": "unknown", "rationale": "tool denial retained", "citations": [],
            })])

        agent = build_agents(config, model_override=FunctionModel(respond))["analysis"]
        result = await run_agent(agent, "analysis", {"concern": "x", "files": ["app.py"]}, deps, config.budget)
        assert result.output is not None
        assert {item.get("tool") for item in result.metrics.trajectory if "tool" in item} >= {"read_file"}
        assert "passwd" not in repr(result.metrics.trajectory)

    try:
        asyncio.run(one("/etc/passwd"))
        asyncio.run(one(".env"))
    finally:
        cleanup_source_workspace(ref, config)


def test_author_output_cannot_escape_its_own_admitted_path(tmp_path: Path) -> None:
    config = _config(tmp_path)
    snapshot, ref, _ = _workspace(config)
    deps = AgentDeps(
        run_id="run-1", stage_id="control", source_manifest=snapshot.manifest, workspace_ref=ref,
        expected_probe_path="tests/test_control.py",
    )
    output = {"status": "drafted", "path": "tests/not-owned.py", "content": "def test_x(): pass\n", "rationale": "x"}

    async def check() -> None:
        agent = build_agents(config, model_override=TestModel(call_tools=[], custom_output_args=output))["control_author"]
        result = await run_agent(agent, "control_author", {"concern": "x", "probe": {}}, deps, config.budget)
        assert result.output is None
        assert result.metrics.status in {"failed", "budget_exhausted"}
    try:
        asyncio.run(check())
    finally:
        cleanup_source_workspace(ref, config)
