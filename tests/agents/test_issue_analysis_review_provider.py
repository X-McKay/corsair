"""Offline native transport check for the separate evidence reviewer."""

import asyncio
import json
from pathlib import Path

import httpx2
from pydantic_ai.usage import UsageLimits

from corsair.agents.issue_analysis import IssueAnalysis, IssueAnalysisInput
from corsair.agents.issue_analysis.provider import LocalModelConfig, local_model
from corsair.agents.issue_analysis.review import (
    REVIEW_SKILL_TEXT, ReviewDependencies, create_evidence_reviewer, review_prompt,
)


ROOT = Path(__file__).resolve().parents[2] / "evals" / "issue_analysis"


def test_reviewer_native_wire_contains_skill_locator_tool_and_trusted_anchor():
    inputs = IssueAnalysisInput.model_validate_json((ROOT / "fixtures" / "path_traversal.json").read_text())
    analysis = IssueAnalysis.model_validate(
        json.loads((ROOT / "oracles.json").read_text())["cases"]["path_traversal"]
    )
    prompt = review_prompt(inputs, analysis)
    requests = []

    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/chat/completions"
        assert body["model"] == "explicit-model"
        assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
        assert sum(message["role"] == "system" for message in body["messages"]) == 1
        system = body["messages"][0]["content"]
        assert REVIEW_SKILL_TEXT in system
        assert "candidate_locator" in system and "preconditions" in system
        assert "condition_audit" in system and "required_condition" in system
        assert any(prompt == message["content"] for message in body["messages"] if message["role"] == "user")

        if len(requests) == 1:
            assert "Saved source inventory: documents.py" in prompt
            assert analysis.hypothesis.preconditions[0] in prompt
            assert analysis.citations[0].quote not in prompt
            call = {"name": "read_source", "arguments": json.dumps({
                "path": "documents.py", "start_line": 1, "end_line": 4,
            })}
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "review-read", "type": "function", "function": call,
            }]}
            finish_reason = "tool_calls"
        else:
            tool_result = json.loads(next(item["content"] for item in body["messages"]
                                          if item["role"] == "tool"))
            assert tool_result["path"] == "documents.py"
            assert [line["number"] for line in tool_result["lines"]] == [1, 2, 3, 4]
            assert "\n".join(line["text"] for line in tool_result["lines"]) == inputs.source_files[0].content.rstrip("\n")
            draft = {
                "assessment": "supported", "scope": "component", "findings": [],
                "citations": [{"path": "documents.py", "start_line": 3, "end_line": 4}],
                "condition_audit": [{
                    "operation": "A resource action occurs", "required_condition": "A stated condition holds",
                    "coverage": "explicit", "basis": "The candidate states this condition.",
                    "candidate_locator": {"field": "preconditions", "index": 0},
                }],
                "limitations": ["No execution was performed."],
            }
            message = {"role": "assistant", "content": json.dumps(draft)}
            finish_reason = "stop"
        return httpx2.Response(200, json={
            "id": f"review-fixture-{len(requests)}", "object": "chat.completion", "created": 1,
            "model": "explicit-model", "choices": [{"index": 0, "finish_reason": finish_reason,
                                                   "message": message}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        })

    async def exercise():
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
        async with local_model(LocalModelConfig(
            server="vllm", base_url="https://llm.example/v1", model_name="explicit-model",
        ), http_client=client) as model:
            result = await create_evidence_reviewer(model).run(
                prompt, deps=ReviewDependencies(inputs, analysis),
                usage_limits=UsageLimits(request_limit=3, tool_calls_limit=1),
                model_settings={"temperature": 0, "max_tokens": 4096,
                                "parallel_tool_calls": False},
            )
            assert result.output.assessment == "supported"
            assert result.output.condition_audit[0].candidate_statement == analysis.hypothesis.preconditions[0]
            assert result.output.citations[0].quote == "\n".join(inputs.source_files[0].content.splitlines()[2:4])
            assert result.usage.requests == 2 and result.usage.tool_calls == 1
        assert client.is_closed

    asyncio.run(exercise())
    assert len(requests) == 2
