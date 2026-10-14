"""Host checks of the pinned native Skills/workspace boundary, without a service."""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.workspaces import WorkspaceReadOnlyError
from pydantic_ai_harness import Skills


def library(tmp_path):
    for name, body in [('own', 'OWN_BODY'), ('peer', 'PEER_BODY')]:
        folder = tmp_path / 'skills' / name
        folder.mkdir(parents=True)
        (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: {name} procedure\n---\n{body}\n')
        (folder / 'bundled.py').write_text('raise RuntimeError("must not execute")')
    return LocalWorkspace(tmp_path, read_only=True)


def test_native_skill_loading_is_per_run_and_does_not_offer_filesystem(tmp_path):
    workspace = library(tmp_path)
    offers = []

    def respond(messages, info):
        loaded = [part for message in messages for part in message.parts
                  if part.__class__.__name__ == 'LoadCapabilityReturnPart']
        offers.append((bool(loaded), info.instructions))
        assert {tool.name for tool in info.function_tools} == {'load_capability'}
        assert 'peer procedure' not in info.instructions
        assert 'PEER_BODY' not in repr(messages)
        assert 'must not execute' not in repr(messages)
        if not loaded:
            assert 'OWN_BODY' not in info.instructions
            return ModelResponse(parts=[ToolCallPart('load_capability', {'id': 'own'})])
        assert 'OWN_BODY' in repr(loaded)
        return ModelResponse(parts=[TextPart('done')])

    agent = Agent(FunctionModel(respond), capabilities=[workspace, Skills('skills', include={'own'})])

    async def run():
        results = await asyncio.gather(agent.run('first'), agent.run('second'))
        assert [result.output for result in results] == ['done', 'done']
    asyncio.run(run())
    assert sum(not loaded for loaded, _ in offers) == 2
    assert sum(loaded for loaded, _ in offers) == 2


def test_native_readonly_denies_mutations_and_command_execution(tmp_path):
    capability = library(tmp_path)
    workspace = capability.get_workspace(None, ref=None)

    async def run():
        assert 'OWN_BODY' in await workspace.read_text('skills/own/SKILL.md')
        for operation in [workspace.write_bytes('marker', b'x'), workspace.make_dir('new'),
                          workspace.remove('skills'), workspace.run(['touch', 'marker'])]:
            with pytest.raises(WorkspaceReadOnlyError):
                await operation
    asyncio.run(run())
    assert not (tmp_path / 'marker').exists()
    assert not (tmp_path / 'new').exists()
    assert (tmp_path / 'skills').exists()
    # History cannot redirect the configured native workspace.
    from pydantic_ai.workspaces import WorkspaceRef
    assert capability.get_workspace(None, ref=WorkspaceRef(provider='local', id='/different')) is None


def test_native_durable_workspace_routes_reads_and_preserves_denial(tmp_path):
    from pydantic_ai.durable_exec._workspace import DurableWorkspace, execute_call
    from pydantic_ai.durable_exec.temporal import TemporalDurability

    wrapped = library(tmp_path).get_workspace(None, ref=None)
    calls = []

    class HostTemporal(TemporalDurability):
        @property
        def in_durable_context(self):
            return True

        async def _call_workspace(self, params):
            calls.append(params.call.method)
            # Host double for activity dispatch; actual native operation/result path.
            return await execute_call(wrapped, params.call)

    workspace = DurableWorkspace(wrapped, durability=HostTemporal(), ctx=SimpleNamespace())

    async def run():
        values = await asyncio.gather(workspace.read_text('skills/own/SKILL.md'),
                                      workspace.read_text('skills/peer/SKILL.md'))
        assert 'OWN_BODY' in values[0] and 'PEER_BODY' in values[1]
        with pytest.raises(WorkspaceReadOnlyError):
            await workspace.write_bytes('marker', b'x')
    asyncio.run(run())
    assert calls.count('ensure') == 1
    assert calls.count('read_bytes') == 2
    assert calls[-1] == 'write_bytes'
    assert not (tmp_path / 'marker').exists()


def test_native_skill_loader_is_metered_even_after_domain_tool_withdrawal(tmp_path):
    from pydantic_ai import capture_run_messages
    from pydantic_ai.exceptions import UsageLimitExceeded
    from pydantic_ai.messages import ToolReturnPart
    from pydantic_ai.usage import UsageLimits
    from corsair.agents.budget import tool_budget

    def respond(messages, info):
        loaded = [part for message in messages for part in message.parts
                  if isinstance(part, ToolReturnPart) and part.tool_name == 'load_capability']
        # The SDK's reserved loader stays visible; the native hard limit still applies.
        assert 'load_capability' in {tool.name for tool in info.function_tools}
        return ModelResponse(parts=[ToolCallPart('load_capability', {'id': 'peer' if loaded else 'own'})])

    agent = Agent(FunctionModel(respond), capabilities=[library(tmp_path),
                  Skills('skills', include={'own', 'peer'}), tool_budget()])

    async def run():
        with capture_run_messages() as messages:
            with pytest.raises(UsageLimitExceeded):
                await agent.run('load both', usage_limits=UsageLimits(tool_calls_limit=1))
        loaded = [part for message in messages for part in message.parts
                  if isinstance(part, ToolReturnPart) and part.tool_name == 'load_capability']
        assert len(loaded) == 1 and 'OWN_BODY' in str(loaded[0].content)
        assert 'PEER_BODY' not in repr(loaded)
    asyncio.run(run())
