"""Unit coverage for producer mechanical helper tools and their native ADK binding."""

from __future__ import annotations

import builtins
import json
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.tool_context import ToolContext

from corsair.adapters.inference.adk import run_producer
from corsair.adapters.scm.local import StoredSourceReader
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.agents.producer.tools.preview_invocation import create_preview_invocation
from corsair.agents.producer.tools.relative_path import create_relative_path
from corsair.agents.producer.toolsets import build_producer_toolset
from corsair.contracts import JavaRecipe, JavaScriptRecipe, ProducerInput, PythonRecipe
from corsair.settings import ModelSettings
from tests.unit.adk import ScriptedLlm, text_response, tool_batch_response, tool_response
from tests.unit.test_agents import _producer_input, _proposal_args

_TOOL_CONTEXT = cast(ToolContext, object())
_PreviewTool = Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]
_RelativePathTool = Callable[[str, str, ToolContext], Awaitable[dict[str, Any]]]


def _preview_tool(producer_input: ProducerInput) -> _PreviewTool:
    return cast(_PreviewTool, create_preview_invocation(producer_input))


def _relative_path_tool(producer_input: ProducerInput) -> _RelativePathTool:
    return cast(_RelativePathTool, create_relative_path(producer_input))


def _input_for_recipe(
    store: ArtifactStore,
    recipe: PythonRecipe | JavaScriptRecipe | JavaRecipe,
    *,
    tool_output_bytes: int | None = None,
    tool_call_limit: int = 3,
):
    producer_input = _producer_input(store, tool_call_limit=tool_call_limit)
    budget = producer_input.budget
    if tool_output_bytes is not None:
        budget = budget.model_copy(update={"tool_output_bytes": tool_output_bytes})
    prepared = producer_input.prepared.model_copy(update={"recipe": recipe})
    return producer_input.model_copy(update={"budget": budget, "prepared": prepared})


def _assert_rejected(result: dict[str, Any]) -> None:
    assert isinstance(result.get("error"), str)
    assert result["target_executed"] is False


@pytest.mark.asyncio
async def test_preview_invocation_preserves_python_fixed_kwargs_and_nested_payload(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    recipe = PythonRecipe(
        module_file="target.py",
        function="disclose",
        payload_parameter="payload",
        fixed_kwargs={"prefix": "fixed:", "options": {"levels": [1, {"safe": True}]}},
    )
    producer_input = _input_for_recipe(store, recipe)
    payload = {"nested": ["payload", {"item": None}]}

    result = await _preview_tool(producer_input)(payload, _TOOL_CONTEXT)

    assert result == {
        "module_file": "target.py",
        "function": "disclose",
        "recipe_kind": "python.secret_disclosure/1",
        "keyword_arguments": {
            "prefix": "fixed:",
            "options": {"levels": [1, {"safe": True}]},
            "payload": payload,
        },
        "target_executed": False,
        "scope": "mechanical_only",
    }
    assert producer_input.prepared.recipe.fixed_kwargs == recipe.fixed_kwargs


@pytest.mark.parametrize(
    ("payload_index", "expected_arguments"),
    [
        (0, ["payload", "left", "right"]),
        (1, ["left", "payload", "right"]),
        (2, ["left", "right", "payload"]),
    ],
)
@pytest.mark.asyncio
async def test_preview_invocation_inserts_node_payload_at_each_declared_position(
    tmp_path: Path,
    payload_index: int,
    expected_arguments: list[str],
):
    store = ArtifactStore(tmp_path)
    recipe = JavaScriptRecipe(
        module_file="target.mjs",
        function="disclose",
        fixed_args=("left", "right"),
        payload_index=payload_index,
    )

    result = await _preview_tool(_input_for_recipe(store, recipe))("payload", _TOOL_CONTEXT)

    assert result["module_file"] == "target.mjs"
    assert result["function"] == "disclose"
    assert result["recipe_kind"] == "javascript.secret_disclosure/1"
    assert result["positional_arguments"] == expected_arguments
    assert result["target_executed"] is False
    assert result["scope"] == "mechanical_only"


@pytest.mark.asyncio
async def test_preview_invocation_preserves_nested_node_payload_and_java_string_abi(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    node_recipe = JavaScriptRecipe(
        module_file="target.mjs",
        function="disclose",
        fixed_args=("left", {"operator": ["fixed"]}),
        payload_index=1,
    )
    node_payload = {"nested": [1, {"value": False}]}
    node_result = await _preview_tool(_input_for_recipe(store, node_recipe))(
        node_payload, _TOOL_CONTEXT
    )
    java_recipe = JavaRecipe(
        module_file="example/Target.java",
        class_name="example.Target",
        function="disclose",
        fixed_args=("left", "right"),
        payload_index=1,
    )
    java_result = await _preview_tool(_input_for_recipe(store, java_recipe))(
        "payload", _TOOL_CONTEXT
    )

    assert node_result["positional_arguments"] == [
        "left",
        node_payload,
        {"operator": ["fixed"]},
    ]
    assert java_result["recipe_kind"] == "java.secret_disclosure/1"
    assert java_result["class_name"] == "example.Target"
    assert java_result["positional_arguments"] == ["left", "payload", "right"]
    assert java_result["target_executed"] is False


@pytest.mark.asyncio
async def test_preview_invocation_rejects_non_json_non_finite_and_java_non_string_payloads(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    python_preview = _preview_tool(
        _input_for_recipe(
            store,
            PythonRecipe(module_file="target.py", function="disclose", payload_parameter="payload"),
        )
    )
    java_preview = _preview_tool(
        _input_for_recipe(
            store, JavaRecipe(module_file="Target.java", class_name="Target", function="disclose")
        )
    )

    for payload in (cast(Any, object()), float("nan"), float("inf"), -float("inf")):
        _assert_rejected(await python_preview(payload, _TOOL_CONTEXT))
    _assert_rejected(await java_preview({"not": "a String"}, _TOOL_CONTEXT))


@pytest.mark.asyncio
async def test_preview_invocation_rejects_payload_and_rendered_output_over_limits(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    recipe = PythonRecipe(module_file="target.py", function="disclose", payload_parameter="payload")
    absolute_preview = _preview_tool(_input_for_recipe(store, recipe, tool_output_bytes=131072))
    output_preview = _preview_tool(_input_for_recipe(store, recipe, tool_output_bytes=1024))

    _assert_rejected(await absolute_preview("x" * 32768, _TOOL_CONTEXT))
    _assert_rejected(await output_preview("x" * 1000, _TOOL_CONTEXT))


@pytest.mark.parametrize(
    ("base_root", "target_path", "expected_base", "expected_target", "relative_path"),
    [
        (
            "/workspace/app",
            "/workspace/lib/file.py",
            "/workspace/app",
            "/workspace/lib/file.py",
            "../lib/file.py",
        ),
        ("/", "/target.py", "/", "/target.py", "target.py"),
        ("/工作/源", "/工作/测试/文件.py", "/工作/源", "/工作/测试/文件.py", "../测试/文件.py"),
    ],
)
@pytest.mark.asyncio
async def test_relative_path_is_lexical_posix_only(
    tmp_path: Path,
    base_root: str,
    target_path: str,
    expected_base: str,
    expected_target: str,
    relative_path: str,
):
    relative = _relative_path_tool(_producer_input(ArtifactStore(tmp_path)))

    result = await relative(base_root, target_path, _TOOL_CONTEXT)

    assert result == {
        "base_root": expected_base,
        "target_path": expected_target,
        "relative_path": relative_path,
        "scope": "lexical_posix_only",
        "target_executed": False,
    }


@pytest.mark.asyncio
async def test_relative_path_normalizes_in_memory_and_has_no_filesystem_or_network_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    producer_input = _producer_input(ArtifactStore(tmp_path))
    before = producer_input.model_dump(mode="json")

    def forbidden_io(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("mechanical helper must not perform I/O")

    monkeypatch.setattr(builtins, "open", forbidden_io)
    monkeypatch.setattr(socket, "socket", forbidden_io)
    preview = _preview_tool(producer_input)
    relative = _relative_path_tool(producer_input)

    preview_result = await preview({"safe": ["nested"]}, _TOOL_CONTEXT)
    relative_result = await relative(
        "/workspace//app/./", "/workspace/app/src/../target.py", _TOOL_CONTEXT
    )

    assert preview_result["target_executed"] is False
    assert relative_result == {
        "base_root": "/workspace/app",
        "target_path": "/workspace/app/target.py",
        "relative_path": "target.py",
        "scope": "lexical_posix_only",
        "target_executed": False,
    }
    assert producer_input.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("base_root", "target_path"),
    [
        ("", "/workspace/target.py"),
        ("/workspace", ""),
        ("workspace", "/workspace/target.py"),
        ("/workspace", "workspace/target.py"),
        ("//workspace", "/workspace/target.py"),
        ("/workspace", "//target.py"),
        ("/workspace\\app", "/workspace/target.py"),
        ("/workspace", "/workspace\\target.py"),
        ("/workspace\x00app", "/workspace/target.py"),
        ("/workspace", "/workspace/target\x00.py"),
        ("/" + "a" * 1024, "/workspace/target.py"),
        ("/workspace", "/" + "a" * 1024),
    ],
)
@pytest.mark.asyncio
async def test_relative_path_rejects_disallowed_or_oversized_inputs(
    tmp_path: Path, base_root: str, target_path: str
):
    result = await _relative_path_tool(_producer_input(ArtifactStore(tmp_path)))(
        base_root, target_path, _TOOL_CONTEXT
    )

    _assert_rejected(result)


@pytest.mark.asyncio
async def test_relative_path_rejects_a_rendered_output_beyond_the_tool_budget(tmp_path: Path):
    producer_input = _input_for_recipe(
        ArtifactStore(tmp_path),
        PythonRecipe(module_file="target.py", function="disclose", payload_parameter="payload"),
        tool_output_bytes=1024,
    )
    base_root = "/" + "a" * 1023
    target_path = "/" + "b" * 1023

    result = await _relative_path_tool(producer_input)(base_root, target_path, _TOOL_CONTEXT)

    _assert_rejected(result)


def test_producer_toolset_binds_helpers_before_the_one_native_skill_toolset(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    tools = build_producer_toolset(_producer_input(store), StoredSourceReader(store))

    assert [getattr(tool, "__name__", None) for tool in tools[:4]] == [
        "read_file",
        "list_files",
        "preview_invocation",
        "relative_path",
    ]
    assert isinstance(tools[4], SkillToolset)


@pytest.mark.asyncio
async def test_native_adk_invokes_both_helpers_then_returns_a_producer_decision(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-helper-tools",
        responses=[
            tool_batch_response(
                [
                    ("preview_invocation", {"payload": {"nested": ["value"]}}),
                    (
                        "relative_path",
                        {
                            "base_root": "/workspace/app",
                            "target_path": "/workspace/target.py",
                        },
                    ),
                ]
            ),
            text_response(json.dumps(_proposal_args())),
        ],
    )

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.decision is not None
    assert output.feedback is None
    assert output.usage.llm_calls == 2
    assert output.usage.tool_calls == 2
    assert len(model.requests) == 2
    assert all(
        set(request.tools_dict)
        == {
            "read_file",
            "list_files",
            "preview_invocation",
            "relative_path",
            "load_skill",
            "load_skill_resource",
        }
        for request in model.requests
    )


@pytest.mark.asyncio
async def test_native_adk_schema_tool_fallback_counts_helpers_and_schema_completion(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-helper-tools-fallback",
        structured_tools=False,
        responses=[
            tool_batch_response(
                [
                    ("preview_invocation", {"payload": "payload"}),
                    (
                        "relative_path",
                        {
                            "base_root": "/workspace/app",
                            "target_path": "/workspace/target.py",
                        },
                    ),
                ]
            ),
            tool_response("set_model_response", _proposal_args()),
        ],
    )

    output = await run_producer(_producer_input(store), ModelSettings(), store, model)

    assert output.decision is not None
    assert output.feedback is None
    assert output.usage.llm_calls == 2
    assert output.usage.tool_calls == 3
    assert {"preview_invocation", "relative_path", "set_model_response"} <= set(
        model.requests[0].tools_dict
    )


@pytest.mark.asyncio
async def test_native_adk_rejects_helper_batch_when_the_tool_budget_is_exhausted(
    tmp_path: Path,
):
    store = ArtifactStore(tmp_path)
    model = ScriptedLlm(
        model="scripted-helper-tool-limit",
        responses=[
            tool_batch_response(
                [
                    ("preview_invocation", {"payload": "payload"}),
                    (
                        "relative_path",
                        {
                            "base_root": "/workspace/app",
                            "target_path": "/workspace/target.py",
                        },
                    ),
                ]
            )
        ],
    )

    output = await run_producer(
        _producer_input(store, tool_call_limit=1), ModelSettings(), store, model
    )

    assert output.decision is None
    assert output.feedback is not None
    assert "tool-call budget" in output.feedback.reason
    assert output.usage.llm_calls == output.usage.tool_calls == 1
    assert len(model.requests) == 1
