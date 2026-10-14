"""Scripted (no model) checks of the two Probers: their one write, the protocol checks, the D3 correction and usage."""
import json
from hashlib import sha256

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from corsair.v2.agents import control_prober, exploit_prober
from corsair.v2.agents.probing.agent import framework_skills
from corsair.v2.agents.probing.draft import protocol_defects
from corsair.v2.contracts import Citation, ExitClass, ProbeBrief, ProbeDraft, Runtime

CONTROL_SOURCE = ("def test_ordinary():\n    open(env['CORSAIR_MARKER_DIR'] + '/start')\n"
                  "    assert target('a') == 'a', env['CORSAIR_TOKEN']\n")
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


EXPLOIT_SOURCE = ("def test_unsafe():\n    open(env['CORSAIR_MARKER_DIR'] + '/start')\n"
                  "    assert safe(target('../x')), env['CORSAIR_TOKEN']\n")


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "target.txt").write_text("line one\nfunction target(name)\nline three\n")
    (tmp_path.parent / "outside.txt").write_text("secret\n")
    return tmp_path


RUNTIME = Runtime(row_id="row", image="img", framework="frame", skill="frame-skill", run_template=("run", "{file}"),
                  exit_codes={0: ExitClass.PASS}, evidence="image-only")


def brief(role):
    name = "test_ordinary" if role == "control" else "test_unsafe"
    return ProbeBrief(role=role, test_file=f"tests/{name}.src", test_name=name, target="lib/target.txt:target",
                      seam="direct call", input_description="an input", property_to_assert="a property",
                      citations=(Citation(path="lib/target.txt", start_line=2, end_line=2),))


def scripted(calls, final=None, seen=None):
    """Make each listed tool call in turn, then answer ``final`` as prompted JSON text; record every request."""
    calls = list(calls)

    async def respond(messages, info: AgentInfo):
        if seen is not None:
            seen.append(messages)
        if calls:
            name, args = calls.pop(0)
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart(json.dumps(final or {"status": "drafted"}))])
    return FunctionModel(respond, model_name="scripted")


def tool_returns(seen, name):
    return [part.content for messages in seen for message in messages for part in getattr(message, "parts", ())
            if isinstance(part, (ToolReturnPart, RetryPromptPart)) and part.tool_name == name]


async def test_control_drafts_from_its_own_write_and_records_usage(tree):
    seen = []
    model = scripted([("read_file", {"path": "lib/target.txt"}),
                      ("write_test_file", {"path": "tests/test_ordinary.src", "content": CONTROL_SOURCE})], seen=seen)
    draft, usage = await control_prober.probe(brief("control"), RUNTIME, model, source_root=tree)
    assert draft == ProbeDraft(role="control", test_file="tests/test_ordinary.src", test_name="test_ordinary",
                               source=CONTROL_SOURCE)
    assert "function target(name)" in str(tool_returns(seen, "read_file")[-1])
    assert (usage.agent, usage.model, usage.status, usage.requests, usage.tool_calls) == (
        "control_prober", "scripted", "ok", 3, 2)
    assert usage.wall_s is not None


async def test_write_test_file_refuses_any_other_path(tree):
    seen = []
    model = scripted([("write_test_file", {"path": "lib/target.txt", "content": CONTROL_SOURCE}),
                      ("write_test_file", {"path": "../escape.src", "content": CONTROL_SOURCE})], seen=seen)
    draft, usage = await control_prober.probe(brief("control"), RUNTIME, model, source_root=tree)
    assert all(r.startswith("refused") for r in tool_returns(seen, "write_test_file"))
    # Nothing was admitted, so "drafted" is refused until the output retries run out.
    assert draft is None and usage.status == "output_invalid"
    assert (tree / "lib" / "target.txt").read_text().startswith("line one")
    assert not (tree.parent / "escape.src").exists()


async def test_either_role_without_the_token_is_refused(tree):
    seen = []
    control_without_token = CONTROL_SOURCE.replace(", env['CORSAIR_TOKEN']", "")
    model = scripted([("write_test_file", {"path": "tests/test_ordinary.src", "content": control_without_token})],
                     seen=seen)
    draft, _ = await control_prober.probe(brief("control"), RUNTIME, model, source_root=tree)
    assert draft is None and "never reads CORSAIR_TOKEN" in tool_returns(seen, "write_test_file")[0]

    seen.clear()
    no_token = EXPLOIT_SOURCE.replace(", env['CORSAIR_TOKEN']", "")
    model = scripted([("write_test_file", {"path": "tests/test_unsafe.src", "content": no_token})], seen=seen)
    draft, _ = await exploit_prober.probe(brief("exploit"), RUNTIME, model, source_root=tree)
    assert draft is None and "never reads CORSAIR_TOKEN" in tool_returns(seen, "write_test_file")[0]


def test_protocol_defects_name_markers_and_test_name():
    defects = protocol_defects("exploit", "test_unsafe", "def test_other(): assert x, env['CORSAIR_TOKEN']")
    assert any("CORSAIR_MARKER_DIR" in d for d in defects)
    assert any("test_unsafe" in d for d in defects)
    assert protocol_defects("exploit", "test_unsafe", EXPLOIT_SOURCE) == []
    assert protocol_defects("control", "test_ordinary", CONTROL_SOURCE) == []


async def test_correction_shows_previous_draft_and_sets_revision_of(tree):
    seen = []
    previous = ProbeDraft(role="exploit", test_file="tests/test_unsafe.src", test_name="test_unsafe",
                          source=EXPLOIT_SOURCE)
    revised = EXPLOIT_SOURCE.replace("target(", "real_target(")
    model = scripted([("write_test_file", {"path": "tests/test_unsafe.src", "content": revised})], seen=seen)
    draft, usage = await exploit_prober.probe(brief("exploit"), RUNTIME, model, source_root=tree,
                                              diagnostics="NameError: target", previous=previous)
    assert draft.source == revised and usage.status == "ok"
    assert draft.revision_of == sha256(EXPLOIT_SOURCE.encode()).hexdigest()
    prompt = str(seen[0][0].parts)
    assert "NameError: target" in prompt and "safe(target('../x'))" in prompt
    with pytest.raises(ValueError):
        await exploit_prober.probe(brief("exploit"), RUNTIME, model, source_root=tree, diagnostics="only half")


async def test_blocked_returns_no_draft_and_roles_are_not_interchangeable(tree):
    model = scripted([], final={"status": "blocked", "note": "no load path for the target"})
    draft, usage = await control_prober.probe(brief("control"), RUNTIME, model, source_root=tree)
    assert draft is None and usage.status == "ok"
    with pytest.raises(ValueError):
        await control_prober.probe(brief("exploit"), RUNTIME, model, source_root=tree)


async def test_source_tools_are_native_read_only_and_stay_inside_the_tree(tree):
    seen = []
    model = scripted([("read_file", {"path": "../outside.txt"}), ("read_file", {"path": "/etc/hostname"}),
                      ("search_files", {"pattern": "target", "path": "lib"}),
                      ("read_file", {"path": "lib/target.txt"})],
                     final={"status": "blocked", "note": "x"}, seen=seen)
    await control_prober.probe(brief("control"), RUNTIME, model, source_root=tree)
    reads = [str(content) for content in tool_returns(seen, "read_file")]
    assert "outside the project root" in reads[0] and "secret" not in "".join(reads)
    assert "function target(name)" in reads[-1]
    assert "target.txt" in str(tool_returns(seen, "search_files")[0])


async def test_model_sees_no_runner_and_only_its_own_brief(tree):
    offered, prompts = [], []

    async def respond(messages, info: AgentInfo):
        offered.append({tool.name for tool in info.function_tools})
        prompts.append(str(messages[0].parts))
        return ModelResponse(parts=[TextPart('{"status": "blocked", "note": "x"}')])
    await control_prober.probe(brief("control"), RUNTIME, FunctionModel(respond), source_root=tree)
    assert offered == [{"load_capability", "read_file", "list_directory", "find_files", "search_files",
                        "write_test_file"}]
    assert "test_unsafe" not in prompts[0] and "frame-skill" in prompts[0]


def test_factories_construct_in_direct_and_durable_modes():
    for package in (control_prober, exploit_prober):
        agent = package.create_agent(TestModel())
        durable = package.create_agent(TestModel(), durability=TemporalDurability(models={"m": TestModel()}))
        assert agent.name == durable.name == package.NAME
    with pytest.raises(TypeError):
        control_prober.create_agent("openai:anything")


async def test_packaged_skills_load_natively_and_a_missing_framework_skill_is_tolerated(tree):
    seen = []
    model = scripted([("load_capability", {"id": "exploit-probe"}), ("load_capability", {"id": "probe-protocol"})],
                     final={"status": "blocked", "note": "x"}, seen=seen)
    _, usage = await exploit_prober.probe(brief("exploit"), RUNTIME, model, source_root=tree)
    loaded = " ".join(str(part.content) for message in seen[-1] for part in message.parts
                      if type(part).__name__ == "LoadCapabilityReturnPart")
    assert "SAFE behaviour" in loaded and "CORSAIR_MARKER_DIR" in loaded and usage.status == "ok"
    assert framework_skills("no-such-framework") == []
