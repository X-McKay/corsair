from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.messages import ModelResponse, TextPart, WorkspaceRef as NativeWorkspaceRef
from pydantic_ai.usage import RunUsage
from pydantic_ai.workspaces import WorkspaceReadOnlyError

from corsair.v2.agents import (
    AgentDeps,
    SourceWorkspaceCapability,
    WorkspaceRef,
    build_agents,
    cleanup_source_workspace,
    prepare_source_workspace,
)
from corsair.v2.contracts import AnalysisInput, ModelProfile, OperatorConfig, SandboxProfile
from corsair.v2.runtime import _capture_analysis_input, _metrics, _usage_snapshot, analyze_case, run_agent
from corsair.v2.storage import Store


def _config(tmp_path: Path) -> OperatorConfig:
    policy_path = tmp_path / "operator-policy.yaml"
    policy_path.write_text("version: test-policy\n", encoding="utf-8")
    return OperatorConfig(
        storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
        sandbox=SandboxProfile(image="example@sha256:" + "b" * 64, policy_path=str(policy_path)),
    )


def test_run_agent_returns_typed_output_and_usage_delta(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = Store(config.storage_root)
    snapshot = _capture_analysis_input(AnalysisInput(files={"a.py": "x = 1\n"}), store)
    ref = prepare_source_workspace(snapshot, config)
    deps = AgentDeps(run_id="run-1", stage_id="analysis", source_manifest=snapshot.manifest, workspace_ref=ref)

    async def check() -> None:
        shared = RunUsage()
        agent = build_agents(config, model_override=TestModel(call_tools=[], custom_output_args={
            "prediction": "unknown", "rationale": "source only", "citations": [],
        }))["analysis"]
        result = await run_agent(agent, "analysis", {"concern": "x", "files": ["a.py"]}, deps, config.budget, shared)
        assert result.output == {"prediction": "unknown", "rationale": "source only", "citations": [], "limitations": []}
        assert result.metrics.requests == 1
        assert result.metrics.input_tokens is not None
        assert result.metrics.field_availability["input_tokens"] == "reported"
        assert result.metrics.usage_details["field_availability"] == result.metrics.field_availability
        assert result.metrics.trajectory[-1]["kind"] == "tool_return"
    try:
        asyncio.run(check())
    finally:
        cleanup_source_workspace(ref, config)


def test_native_usage_availability_requires_explicit_provider_cache_zero() -> None:
    def metrics(cache_present: bool):
        response = ModelResponse(parts=[TextPart("fixture")], metadata={
            "corsair_usage_presence": {"fields": {
                "input_tokens": True,
                "output_tokens": True,
                "cache_read_tokens": cache_present,
                "cache_write_tokens": False,
                "reasoning_tokens": False,
            }},
        })
        return _metrics(
            role="analysis", model="fixture", started=0.0, clock="perf_counter_direct_process",
            before=_usage_snapshot(RunUsage()),
            usage=RunUsage(requests=1, input_tokens=17, output_tokens=3, cache_read_tokens=0),
            status="completed", responses=(response,),
        )

    missing_cache = metrics(cache_present=False)
    assert missing_cache.input_tokens == 17
    assert missing_cache.field_availability["input_tokens"] == "reported"
    assert missing_cache.cache_read_tokens is None
    assert missing_cache.field_availability["cache_read_tokens"] == "not_reported"

    reported_zero_cache = metrics(cache_present=True)
    assert reported_zero_cache.cache_read_tokens == 0
    assert reported_zero_cache.field_availability["cache_read_tokens"] == "reported_zero"


def test_analyze_case_shares_guarded_source_cache_until_explicit_quiescent_cleanup(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    model = TestModel(call_tools=[], custom_output_args={
        "prediction": "vulnerable", "rationale": "bounded source observation", "citations": [
            {"path": "a.py", "start_line": 1, "end_line": 1}
        ],
    })
    entered = asyncio.Event()
    release = asyncio.Event()
    source_reads: list[bytes] = []
    manifest_ids: list[str] = []
    original_run_agent = run_agent

    async def gated_run_agent(agent, role, public_input, deps, budget, usage=None):
        workspace = SourceWorkspaceCapability(config.storage_root).get_workspace(
            SimpleNamespace(deps=deps),
            ref=NativeWorkspaceRef(provider="corsair-source", id=deps.workspace_ref.id),
        )
        assert workspace is not None
        source_reads.append(await workspace.read_bytes("source/a.py"))
        manifest_ids.append(workspace.ref.id)
        assert workspace.ref.id == deps.source_manifest.sha256
        with pytest.raises(WorkspaceReadOnlyError):
            await workspace.write_bytes("source/a.py", b"tamper")
        if len(source_reads) == 2:
            entered.set()
        await release.wait()
        return await original_run_agent(agent, role, public_input, deps, budget, usage)

    monkeypatch.setattr("corsair.v2.runtime.build_agents", lambda _: build_agents(config, model_override=model))
    monkeypatch.setattr("corsair.v2.runtime.run_agent", gated_run_agent)

    async def run_concurrently():
        inputs = AnalysisInput(files={"a.py": "danger()\n"})
        first = asyncio.create_task(analyze_case(inputs, config))
        second = asyncio.create_task(analyze_case(inputs, config))
        await asyncio.wait_for(entered.wait(), timeout=2)
        workspace_parent = Path(config.storage_root) / "agent-workspaces"
        roots = [path for path in workspace_parent.iterdir() if path.is_dir()]
        assert len(roots) == 1
        source = roots[0] / "source" / "a.py"
        assert source.read_bytes() == b"danger()\n"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(b"danger()\n").hexdigest()
        assert list(workspace_parent.glob("*.lock"))  # Publication locks are legitimate shared-cache state.
        release.set()
        return await asyncio.gather(first, second), roots[0]

    results, root = asyncio.run(run_concurrently())
    assert all(result.assessment is not None and result.output_ref is not None for result in results)
    assert source_reads == [b"danger()\n", b"danger()\n"]
    assert len(set(manifest_ids)) == 1
    assert all(event.get("tool") != "read_file" for result in results for event in result.metrics.trajectory)
    assert root.is_dir()  # analyze_case must not delete a shared source cache after either trial completes.
    cleanup_source_workspace(WorkspaceRef(id=manifest_ids[0]), config)
    assert not root.exists()


def test_analyze_case_refuses_out_of_range_model_citation(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    model = TestModel(call_tools=[], custom_output_args={
        "prediction": "vulnerable", "rationale": "bad cite", "citations": [
            {"path": "a.py", "start_line": 8, "end_line": 8}
        ],
    })
    monkeypatch.setattr("corsair.v2.runtime.build_agents", lambda _: build_agents(config, model_override=model))
    result = asyncio.run(analyze_case(AnalysisInput(files={"a.py": "danger()\n"}), config))
    assert result.assessment is None
    assert result.metrics.status == "failed"
    assert result.metrics.error and "CitationAdmissionError" in result.metrics.error
