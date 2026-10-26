"""Offline `corsair agent preview`: the exact request a role would receive, never a model.

Renders the frozen case01 request through the production run_producer / run_auditor path
with the capturing model in corsair.evaluation.preview; no provider, container or oracle
is touched. Byte bounds are the ones pinned by the request-size tests.
"""

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import pytest

from corsair.contracts import Feedback, Submission
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal, failure_remedy
from corsair.evaluation import preview
from corsair.settings import Settings
from tests.unit.test_auditor_request_size import MAX_SYSTEM_AND_TOOLS_BYTES
from tests.unit.test_producer_request_size import (
    MAX_CORSAIR_INSTRUCTION_BYTES,
    MAX_SYSTEM_INSTRUCTION_BYTES,
    REQUIRED_CONSTRAINTS,
)

ROOT = Path(__file__).resolve().parents[2]
CASE01 = ROOT / "evals/fixtures/case01"
REQUEST = CASE01 / "request.json"
SUBMISSION = CASE01 / "submission.json"
PREVIEW_KEYS = {
    "schema_version",
    "role",
    "inputs",
    "route",
    "generation",
    "token_estimate",
    "declared_tools",
    "parts",
    "totals",
    "request_sha256",
}
PART_KEYS = {"name", "kind", "bytes", "approx_tokens", "sha256", "text"}


def _submission() -> Submission:
    return Submission.model_validate_json(SUBMISSION.read_bytes())


def _settings() -> Settings:
    return Settings(source_root=str(ROOT))


def _instruction_bytes(value: dict[str, Any], *, adk: bool) -> int:
    return sum(
        part["bytes"]
        for part in value["parts"]
        if part["kind"] == "instruction" and (adk or part["name"] != "instruction.adk")
    )


def _assert_consistent(value: dict[str, Any]) -> None:
    """Every part's sizes and digest describe its text; totals are the part sums."""
    assert set(value) == PREVIEW_KEYS
    assert value["schema_version"] == preview.PREVIEW_SCHEMA
    assert value["token_estimate"] == "ceil(bytes/4)"
    for part in value["parts"]:
        assert set(part) == PART_KEYS
        raw = part["text"].encode()
        assert part["bytes"] == len(raw)
        assert part["approx_tokens"] == math.ceil(len(raw) / 4)
        assert part["sha256"] == hashlib.sha256(raw).hexdigest()
    for kind in preview.PART_KINDS:
        kind_bytes = sum(part["bytes"] for part in value["parts"] if part["kind"] == kind)
        assert value["totals"][kind]["bytes"] == kind_bytes
    request_bytes = sum(part["bytes"] for part in value["parts"])
    assert value["totals"]["request"] == {
        "bytes": request_bytes,
        "approx_tokens": math.ceil(request_bytes / 4),
    }
    joined = "".join(part["text"] for part in value["parts"]).encode()
    assert value["request_sha256"] == hashlib.sha256(joined).hexdigest()
    # One part per declared tool, in declaration order, whatever the factory returned.
    tools = [part["name"] for part in value["parts"] if part["kind"] == "tool"]
    assert tools == [f"tool.{name}" for name in value["declared_tools"]]


# rendering


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_tools", [False, True])
async def test_producer_preview_renders_case01_through_the_production_factory(
    structured_tools: bool,
):
    value = await preview.preview_request(
        "producer", REQUEST, _settings(), structured_tools=structured_tools
    )

    _assert_consistent(value)
    names = [part["name"] for part in value["parts"]]
    assert names[:2] == ["instruction.prompt", "instruction.skill.source-grounding"]
    assert names[-1] == "packet"
    assert {"read_file", "list_files"} <= set(value["declared_tools"])
    assert ("set_model_response" in value["declared_tools"]) is not structured_tools
    assert ("response_schema" in names) is structured_tools
    assert value["route"]["capability"] == "override"
    assert value["inputs"] == {
        "request": str(REQUEST),
        "case_id": "case01",
        "round": 1,
        "previous_submission": None,
        "feedback_gate": None,
        "submission": None,
    }
    corsair = _instruction_bytes(value, adk=False)
    assert corsair <= MAX_CORSAIR_INSTRUCTION_BYTES
    assert _instruction_bytes(value, adk=True) <= MAX_SYSTEM_INSTRUCTION_BYTES
    system = "".join(part["text"] for part in value["parts"] if part["kind"] == "instruction")
    assert all(rule in system for rule in REQUIRED_CONSTRAINTS)
    packet = value["parts"][-1]["text"]
    assert '"payload_parameter":"path"' in packet
    assert '"round":{"parent_revision":null,"revision":1}' in packet


@pytest.mark.asyncio
async def test_producer_preview_matches_the_measurement_script_sections():
    """The CLI preview and the measurement script are one renderer, byte for byte."""
    value = await preview.preview_request("producer", REQUEST, _settings(), structured_tools=False)
    requests = await preview.render_requests(
        "producer", preview.load_request(REQUEST), _settings(), structured_tools=False
    )
    sections = preview.request_sections("producer", requests[0])

    assert len(sections["corsair_instruction"].encode()) == _instruction_bytes(value, adk=False)
    tool_parts = [part for part in value["parts"] if part["kind"] == "tool"]
    # The script reports one JSON list: brackets plus a comma between declarations.
    expected_list = sum(part["bytes"] for part in tool_parts) + 2 + len(tool_parts) - 1
    assert len(sections["tool_declarations"].encode()) == expected_list
    assert sections["user_packet"] == value["parts"][-1]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_tools", [False, True])
async def test_auditor_preview_is_one_tool_free_schema_request(structured_tools: bool):
    value = await preview.preview_request(
        "auditor",
        REQUEST,
        _settings(),
        submission=_submission(),
        structured_tools=structured_tools,
    )

    _assert_consistent(value)
    names = [part["name"] for part in value["parts"]]
    assert names[:2] == ["instruction.prompt", "instruction.skill.semantic-review"]
    assert value["declared_tools"] == []
    assert value["totals"]["tool"]["bytes"] == 0
    assert "response_schema" in names
    assert value["generation"]["response_mime_type"] == "application/json"
    system_and_tools = _instruction_bytes(value, adk=True) + value["totals"]["tool"]["bytes"]
    assert system_and_tools <= MAX_SYSTEM_AND_TOOLS_BYTES
    packet = value["parts"][-1]["text"]
    assert "## Submission" in packet and "../private/secret.txt" in packet
    assert value["inputs"]["submission"] is not None


@pytest.mark.asyncio
async def test_producer_retry_preview_carries_previous_submission_and_feedback():
    value = await preview.preview_request(
        "producer",
        REQUEST,
        _settings(),
        round_index=2,
        previous=_submission(),
        feedback=Feedback(gate="audit", reason="the exploit payload never reaches open"),
        structured_tools=False,
    )

    packet = json.loads(value["parts"][-1]["text"].split("\n", 1)[1])
    assert packet["round"] == {"revision": 2, "parent_revision": 1}
    assert packet["previous_submission"] == _submission().model_dump(mode="json")
    assert packet["previous_feedback"]["reason"] == "the exploit payload never reaches open"
    assert value["inputs"]["feedback_gate"] == "audit"


@pytest.mark.asyncio
async def test_producer_preview_never_carries_oracle_data():
    value = await preview.preview_request("producer", REQUEST, _settings(), structured_tools=False)
    rendered = json.dumps(value)

    oracle = json.loads((CASE01 / "producer-oracle.json").read_text())
    # The finding itself names the fixture path; every other oracle payload stays out.
    request = REQUEST.read_text()
    private = [value for value in oracle["candidate_payloads"] if value not in request]
    assert private == ["../private/secret.txt"]
    for absent in (*private, "candidate_payloads", "acceptable_verdicts"):
        assert absent not in rendered
    assert "EXPLOIT_DEMONSTRATED" not in rendered


@pytest.mark.asyncio
async def test_preview_refuses_a_case_the_workflow_stops_before_any_model(tmp_path: Path):
    shutil.copytree(CASE01 / "source", tmp_path / "source")
    request = json.loads(REQUEST.read_text())
    request["case"]["finding"]["line"] = 99
    del request["case"]["fixed_source"]
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))

    with pytest.raises(ValueError, match="before any model request") as refused:
        await preview.preview_request(
            "producer", path, Settings(source_root=str(tmp_path)), structured_tools=False
        )
    assert "target_binding" in str(refused.value)
    assert "corsair dataset validate" in (failure_remedy(refused.value) or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "options", "message"),
    [
        ("auditor", {}, "pass --submission"),
        ("auditor", {"round_index": 2, "submission": "submission"}, "producer inputs"),
        ("producer", {"submission": "submission"}, "auditor's input"),
        ("producer", {"feedback": Feedback(gate="audit", reason="x")}, "pass --round 2"),
        ("producer", {"round_index": 3}, "max_rounds"),
    ],
)
async def test_preview_rejects_inputs_the_role_never_receives(role, options, message):
    if options.get("submission") == "submission":
        options = {**options, "submission": _submission()}

    with pytest.raises(ValueError, match=message) as refused:
        await preview.preview_request(role, REQUEST, _settings(), structured_tools=False, **options)

    assert str(refused.value).startswith("agent preview:")
    assert "corsair agent preview --help" in (failure_remedy(refused.value) or "")


@pytest.mark.parametrize(("environment", "capable"), [(None, False), ("true", True)])
def test_route_reports_the_configured_schema_capability(monkeypatch, environment, capable):
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    if environment is None:
        monkeypatch.delenv("GOOGLE_GENAI_USE_ENTERPRISE", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", environment)

    route = preview.describe_route(Settings(), "producer", None)

    assert route == {
        "connector": "gemini",
        "model": "gemini-2.5-flash",
        "output_schema_and_tools": capable,
        "capability": "configured",
    }
    assert preview.describe_route(Settings(), "producer", not capable)["capability"] == "override"


# diff


def _synthetic(parts: list[tuple[str, str, str]], *, role: str = "producer") -> dict[str, Any]:
    rendered = [preview._part(name, kind, text) for name, kind, text in parts]
    return {
        "schema_version": preview.PREVIEW_SCHEMA,
        "role": role,
        "inputs": {"request": "request.json", "case_id": "synthetic", "round": 1},
        "route": {},
        "generation": {},
        "token_estimate": preview.TOKEN_ESTIMATE,
        "declared_tools": [name[5:] for name, kind, _ in parts if kind == "tool"],
        "parts": rendered,
        "totals": preview.part_totals(rendered),
        "request_sha256": hashlib.sha256(
            "".join(text for _, _, text in parts).encode()
        ).hexdigest(),
    }


def test_diff_compares_two_previews_part_by_part():
    baseline = _synthetic(
        [
            ("instruction.prompt", "instruction", "Rule one.\nRule two.\n"),
            ("tool.read_file", "tool", '{"name":"read_file","parameters":{"path":1}}'),
            ("tool.load_skill", "tool", '{"name":"load_skill"}'),
            ("packet", "packet", 'Header\n{"round":1}'),
        ]
    )
    candidate = _synthetic(
        [
            ("instruction.prompt", "instruction", "Rule one.\nRule two, tightened.\n"),
            ("tool.read_file", "tool", '{"name":"read_file","parameters":{"path":1}}'),
            ("tool.set_model_response", "tool", '{"name":"set_model_response"}'),
            ("packet", "packet", 'Header\n{"round":1}'),
        ]
    )

    diff = preview.diff_previews(baseline, candidate)

    assert diff["schema_version"] == preview.DIFF_SCHEMA and diff["changed"] is True
    rows = {row["name"]: row for row in diff["parts"]}
    assert [row["name"] for row in diff["parts"]] == [
        "instruction.prompt",
        "tool.read_file",
        "tool.set_model_response",
        "packet",
        "tool.load_skill",
    ]
    assert {name: row["status"] for name, row in rows.items()} == {
        "instruction.prompt": "changed",
        "tool.read_file": "unchanged",
        "tool.set_model_response": "added",
        "packet": "unchanged",
        "tool.load_skill": "removed",
    }
    assert rows["instruction.prompt"]["bytes"] == {"baseline": 20, "candidate": 31, "delta": 11}
    assert rows["tool.set_model_response"]["bytes"]["baseline"] is None
    assert rows["tool.load_skill"]["bytes"] == {"baseline": 21, "candidate": None, "delta": -21}
    assert "unified_diff" not in rows["tool.read_file"]
    assert "+Rule two, tightened." in rows["instruction.prompt"]["unified_diff"]
    assert '+  "name": "set_model_response"' in rows["tool.set_model_response"]["unified_diff"]
    request = diff["totals"]["request"]["bytes"]
    assert request["delta"] == request["candidate"] - request["baseline"]
    assert diff["totals"]["tool"]["bytes"]["delta"] == 29 - 21


def test_diff_of_identical_previews_reports_no_change():
    value = _synthetic([("packet", "packet", "same")])

    diff = preview.diff_previews(value, json.loads(json.dumps(value)))

    assert diff["changed"] is False
    assert [row["status"] for row in diff["parts"]] == ["unchanged"]
    assert diff["totals"]["request"]["bytes"]["delta"] == 0


def test_diff_refuses_two_roles_and_other_documents(tmp_path: Path):
    with pytest.raises(ValueError, match="one role"):
        preview.diff_previews(_synthetic([]), _synthetic([], role="auditor"))
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"summary": {}}))
    with pytest.raises(ValueError, match="not a saved") as refused:
        preview.load_preview(report)
    assert failure_remedy(refused.value) is not None


# CLI


def _arguments(tmp_path: Path, *argv: str, format: str = "json") -> cli.CliArguments:
    settings = tmp_path / "settings.json"
    settings.write_text(_settings().model_dump_json())
    return cli.parser().parse_args(
        ["--format", format, "agent", "preview", *argv, "--settings", str(settings)],
        namespace=cli.CliArguments(),
    )


async def _run(args: cli.CliArguments) -> int:
    return await cli.execute(args, Terminal(args))


@pytest.mark.asyncio
async def test_cli_saves_a_json_preview_and_diffs_a_retry_against_it(tmp_path: Path, capsys):
    saved = tmp_path / "previews" / "round1.json"
    args = _arguments(
        tmp_path, "producer", str(REQUEST), "--no-structured-tools", "--output", str(saved)
    )

    assert await _run(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(saved.read_text())
    assert printed["role"] == "producer" and printed["route"]["capability"] == "override"

    retry = _arguments(
        tmp_path,
        "producer",
        str(REQUEST),
        "--no-structured-tools",
        "--round",
        "2",
        "--previous",
        str(SUBMISSION),
        "--feedback",
        "audit:the exploit never reaches open",
        "--diff",
        str(saved),
    )
    assert await _run(retry) == 0
    diff = json.loads(capsys.readouterr().out)
    statuses = {row["name"]: row["status"] for row in diff["parts"]}
    assert statuses["packet"] == "changed"
    assert {status for name, status in statuses.items() if name != "packet"} == {"unchanged"}
    assert diff["totals"]["packet"]["bytes"]["delta"] > 0


@pytest.mark.asyncio
async def test_cli_human_preview_is_collapsed_unless_full(tmp_path: Path, capsys):
    argv = ("auditor", str(REQUEST), "--submission", str(SUBMISSION), "--structured-tools")

    assert await _run(_arguments(tmp_path, *argv, format="human")) == 0
    collapsed = capsys.readouterr().out
    assert await _run(_arguments(tmp_path, *argv, "--full", format="human")) == 0
    full = capsys.readouterr().out

    assert "Corsair · Agent preview · auditor" in collapsed
    assert "instruction.skill.semantic-review" in collapsed and "total request" in collapsed
    assert "--full prints every part" in collapsed
    assert "## Submission" not in collapsed
    assert "## Submission" in full and "--full prints every part" not in full


def test_cli_feedback_requires_gate_and_reason(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.parser().parse_args(
            ["agent", "preview", "producer", "request.json", "--feedback", "audit"]
        )
    assert stopped.value.code == 2
    assert "GATE:REASON" in capsys.readouterr().err
