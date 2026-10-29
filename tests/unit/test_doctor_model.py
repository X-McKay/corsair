"""Offline regressions for the opt-in ``corsair doctor --model`` provider readiness check.

Every model here is a fake native ADK ``BaseLlm``; no test contacts a provider endpoint.
"""

import asyncio
import json
import subprocess
import sys
from typing import Any

import pytest
from google.adk.models import BaseLlm
from google.adk.models.base_llm import LlmCapabilities
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from corsair.entrypoints import cli, diagnostics
from corsair.entrypoints.diagnostics import diagnose, diagnose_model
from corsair.entrypoints.terminal import Terminal
from corsair.settings import ModelSettings, Settings
from tests.unit.adk import text_response, tool_response, truncated_response

ENDPOINT = "https://llm.example.test:8443/v1"


def _reply(text: str, finish: types.FinishReason = types.FinishReason.STOP) -> LlmResponse:
    response = text_response(text)
    response.finish_reason = finish
    response.usage_metadata = types.GenerateContentResponseUsageMetadata(candidates_token_count=2)
    return response


class ProbeLlm(BaseLlm):
    """A fake native model that answers a request by whether it declares tools."""

    text_reply: LlmResponse = Field(default_factory=lambda: _reply("ready"))
    tool_reply: LlmResponse = Field(
        default_factory=lambda: tool_response(diagnostics._PROBE_TOOL, {})
    )
    error: Exception | None = None
    delay: float = 0.0
    banner: str | None = None
    structured_tools: bool = True
    requests: list[Any] = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.structured_tools)

    async def generate_content_async(self, llm_request: Any, stream: bool = False):
        assert stream is False
        self.requests.append(llm_request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.banner is not None:
            print(self.banner)  # As LiteLLM prints its help banner on a provider error.
        if self.error is not None:
            raise self.error
        yield self.tool_reply if llm_request.config.tools else self.text_reply


def _settings(**models: Any) -> Settings:
    values = {
        "connector": "litellm",
        "producer": "hosted_vllm/served-model",
        "auditor": "hosted_vllm/served-model",
        "intake": "hosted_vllm/served-model",
        "api_base": ENDPOINT,
        "extra_body": {"reasoning_effort": "low"},
        **models,
    }
    # An unvalidated copy admits values the settings validator would reject (credential-bearing
    # endpoints, a zero timeout) so that the doctor's own redaction is what is tested.
    return Settings(models=ModelSettings().model_copy(update=values))


class _Resolver:
    """Return fake role models and record which roles were resolved."""

    def __init__(self, producer: BaseLlm, auditor: BaseLlm | None = None) -> None:
        self.models = {
            "producer": producer,
            "auditor": auditor or producer,
            "intake": producer.model_copy(deep=True),
        }
        self.calls: list[str] = []

    def __call__(self, settings: Settings, role: str) -> BaseLlm:
        del settings
        self.calls.append(role)
        return self.models[role]


_resolver = _Resolver


async def test_doctor_reports_intake_route_rejection_without_dispatch():
    resolve = _Resolver(ProbeLlm(model="producer"))
    checks = _by_name(
        await diagnose_model(_settings(intake="openai/blocked"), resolve_model=resolve)
    )
    assert checks["model_intake"]["status"] == "fail"
    assert "MODEL_CONFIGURATION_UNSUPPORTED" in checks["model_intake"]["detail"]
    assert "intake" not in resolve.calls


async def test_doctor_checks_intake_text_and_tools_independently():
    resolve = _Resolver(ProbeLlm(model="producer"))
    resolve.models["intake"] = ProbeLlm(model="intake", tool_reply=_reply("no tool"))
    checks = _by_name(await diagnose_model(_settings(), resolve_model=resolve))
    assert checks["model_intake"]["status"] == "pass"
    assert checks["model_intake_tools"]["status"] == "fail"


def test_doctor_reports_missing_reader_and_additional_candidate_separately(monkeypatch):
    from types import SimpleNamespace

    from docker.errors import ImageNotFound

    class Images:
        def get(self, tag):
            if tag in {"reader:missing", "extra:missing"}:
                raise ImageNotFound("image missing")
            return SimpleNamespace(
                id="sha256:" + "1" * 64, attrs={"Os": "linux", "Architecture": "arm64"}
            )

    client = SimpleNamespace(
        images=Images(),
        ping=lambda: True,
        close=lambda: None,
        info=lambda: {"Runtimes": {"runc": {}}, "OSType": "linux", "Architecture": "arm64"},
    )
    monkeypatch.setattr(diagnostics.docker, "from_env", lambda **kwargs: client)
    settings = Settings(
        image="python:available",
        images={},
        intake_image="reader:missing",
        intake_images=[
            {"reference": "extra:missing", "language": "python", "execution_mode": "callable"}
        ],
    )
    checks = _by_name(diagnostics._check_docker_images(settings))
    assert checks["image:reader:missing"]["status"] == "fail"
    assert checks["image:extra:missing"]["status"] == "fail"
    assert checks["image:python:available"]["status"] == "pass"


def _by_name(checks: list[dict]) -> dict[str, dict]:
    return {check["name"]: check for check in checks}


async def test_healthy_route_reports_config_credentials_latency_and_tool_round_trip(monkeypatch):
    monkeypatch.setenv("HOSTED_VLLM_API_KEY", "not-a-real-credential-value")
    producer, auditor = ProbeLlm(model="hosted_vllm/served-model"), ProbeLlm(model="auditor")

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer, auditor)))

    assert [check["status"] for check in checks.values()] == ["pass"] * 7
    config = checks["model_config"]["detail"]
    assert "connector=litellm" in config and "producer=hosted_vllm/served-model" in config
    assert "api_base host=llm.example.test:8443" in config and "/v1" not in config
    assert "request_timeout_seconds=120" in config and "extra_body keys=reasoning_effort" in config
    assert checks["model_credentials"]["detail"].count("HOSTED_VLLM_API_KEY is set") == 3
    assert "not-a-real-credential-value" not in json.dumps(checks)
    assert "finish_reason=STOP" in checks["model_producer"]["detail"]
    assert "output_tokens=2" in checks["model_auditor"]["detail"]
    assert "with a paired response schema" in checks["model_producer_tools"]["detail"]
    # Minimal typed requests: a 32-token text probe and one trivial tool, no agent content.
    text, tool = sorted(producer.requests, key=lambda request: bool(request.config.tools))
    assert text.config.max_output_tokens == 32 and not text.config.tools
    assert text.config.response_schema is None
    assert tool.config.max_output_tokens == diagnostics._TOOL_PROBE_OUTPUT_TOKENS
    declarations = tool.config.tools[0].function_declarations
    assert [declaration.name for declaration in declarations] == [diagnostics._PROBE_TOOL]
    assert tool.config.response_schema == diagnostics._PROBE_SCHEMA
    assert len(auditor.requests) == 1 and not auditor.requests[0].config.tools
    prompts = [part.text for request in producer.requests for part in request.contents[0].parts]
    assert all(len(prompt) < 80 for prompt in prompts)


async def test_tool_probe_without_structured_tools_capability_sends_no_schema():
    producer = ProbeLlm(model="m", structured_tools=False)

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer)))

    assert "without a paired response schema" in checks["model_producer_tools"]["detail"]
    assert all(request.config.response_schema is None for request in producer.requests)


async def test_text_answer_to_the_tool_probe_fails_with_the_route_remedy():
    # A guided-decoding route answers with schema-shaped text instead of a function call.
    producer = ProbeLlm(model="m", tool_reply=_reply('{"status": "ok"}'))

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer)))

    tools = checks["model_producer_tools"]
    assert tools["status"] == "fail" and "without a native function call" in tools["detail"]
    assert "hosted_vllm/" in tools["remedy"] and "status" not in tools["detail"]
    assert checks["model_producer"]["status"] == "pass"


async def test_call_of_an_undeclared_function_fails():
    producer = ProbeLlm(model="m", tool_reply=tool_response("other_tool", {}))

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer)))

    assert checks["model_producer_tools"]["status"] == "fail"
    assert "other_tool" not in checks["model_producer_tools"]["detail"]


async def test_output_cap_passes_the_text_probe_and_leaves_the_tool_probe_inconclusive():
    producer = ProbeLlm(model="m", text_reply=truncated_response(), tool_reply=truncated_response())

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer)))

    assert checks["model_producer"]["status"] == "pass"
    assert "32-token probe cap" in checks["model_producer"]["detail"]
    assert checks["model_producer_tools"]["status"] == "warn"
    assert "inconclusive" in checks["model_producer_tools"]["detail"]


async def test_provider_error_response_fails_with_a_fixed_remedy():
    error = LlmResponse(error_code="NotFoundError", error_message="404 model does not exist")
    producer = ProbeLlm(model="m", text_reply=error, tool_reply=error)

    checks = _by_name(await diagnose_model(_settings(), resolve_model=_resolver(producer)))

    for name in ("model_producer", "model_producer_tools", "model_auditor"):
        assert checks[name]["status"] == "fail"
        assert checks[name]["remedy"] == diagnostics._NOT_FOUND_REMEDY


async def test_probe_deadline_reports_a_timeout_failure(monkeypatch):
    monkeypatch.setattr(diagnostics, "_PROBE_GRACE_SECONDS", 0.05)
    producer = ProbeLlm(model="m", delay=5.0)

    checks = _by_name(
        await diagnose_model(
            _settings(request_timeout_seconds=0), resolve_model=_resolver(producer)
        )
    )

    for name in ("model_producer", "model_producer_tools", "model_auditor"):
        assert checks[name]["status"] == "fail"
        assert checks[name]["detail"].startswith("TimeoutError")
        assert checks[name]["remedy"] == diagnostics._TIMEOUT_REMEDY


async def test_provider_raised_timeout_is_mapped_by_class_name():
    timeout = type("Timeout", (Exception,), {})("litellm.Timeout: Request timed out")
    checks = _by_name(
        await diagnose_model(
            _settings(), resolve_model=_resolver(ProbeLlm(model="m", error=timeout))
        )
    )

    assert checks["model_producer"]["remedy"] == diagnostics._TIMEOUT_REMEDY


async def test_provider_stdout_banner_is_kept_off_the_json_stdout(capsys):
    producer = ProbeLlm(model="m", banner="Give Feedback / Get Help")

    await diagnose_model(_settings(), resolve_model=_resolver(producer))

    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.count("Give Feedback") == 5


async def test_api_base_userinfo_query_and_credentials_never_appear(monkeypatch):
    secret = "sk-this-must-never-appear-0123456789"
    monkeypatch.setenv("HOSTED_VLLM_API_KEY", secret)
    leaky = "https://operator:hunter2pass@llm.example.test:8443/v1/private?api_key=abcdef123#frag"
    failure = type("AuthenticationError", (Exception,), {})(
        f"401 from {leaky} with key {secret} and Authorization: Bearer {secret}"
    )
    producer = ProbeLlm(model="m", error=failure)

    checks = await diagnose_model(_settings(api_base=leaky), resolve_model=_resolver(producer))

    rendered = json.dumps(checks)
    for fragment in ("operator", "hunter2pass", "abcdef123", "api_key=", "private", "frag", secret):
        assert fragment not in rendered, fragment
    named = _by_name(checks)
    assert "api_base host=llm.example.test:8443;" in named["model_config"]["detail"]
    assert named["model_producer"]["remedy"] == diagnostics._AUTH_REMEDY


async def test_missing_required_credential_fails_by_name_only(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = _settings(producer="anthropic/model-a", auditor="unknownroute/model-b")

    credentials = _by_name(
        await diagnose_model(settings, resolve_model=_resolver(ProbeLlm(model="m")))
    )["model_credentials"]

    assert credentials["status"] == "fail"
    assert (
        "producer: ANTHROPIC_API_KEY is not set (required for anthropic/)" in credentials["detail"]
    )
    assert "auditor: no known credential variable for route unknownroute/" in credentials["detail"]
    assert credentials["remedy"] == diagnostics._AUTH_REMEDY


async def test_present_credential_and_unknown_route_warn(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "value-is-never-reported")
    settings = _settings(producer="anthropic/model-a", auditor="unknownroute/model-b")

    credentials = _by_name(
        await diagnose_model(settings, resolve_model=_resolver(ProbeLlm(model="m")))
    )["model_credentials"]

    assert credentials["status"] == "warn" and "remedy" not in credentials
    assert "ANTHROPIC_API_KEY is set" in credentials["detail"]
    assert "value-is-never-reported" not in credentials["detail"]


async def test_optional_and_gemini_credentials(monkeypatch):
    monkeypatch.delenv("HOSTED_VLLM_API_KEY", raising=False)
    optional = diagnostics._model_credentials_check(_settings())
    assert optional["status"] == "pass" and "optional for hosted_vllm/" in optional["detail"]

    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(name, raising=False)
    gemini = Settings()
    assert diagnostics._model_credentials_check(gemini)["status"] == "fail"
    monkeypatch.setenv("GEMINI_API_KEY", "x" * 16)
    assert diagnostics._model_credentials_check(gemini)["status"] == "pass"
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    vertex = diagnostics._model_credentials_check(gemini)
    assert vertex["status"] == "fail" and "GOOGLE_CLOUD_PROJECT" in vertex["detail"]


async def test_unresolvable_model_fails_before_any_request():
    def resolve(settings: Settings, role: str) -> BaseLlm:
        del settings, role
        raise ImportError("connector 'litellm' requires Corsair's providers extra")

    checks = _by_name(await diagnose_model(_settings(), resolve_model=resolve))

    assert set(checks) == {"model_config", "model_credentials", "model_resolution"}
    assert checks["model_resolution"]["status"] == "fail"
    assert checks["model_resolution"]["remedy"] == diagnostics._PROVIDERS_REMEDY


def test_plain_gemini_id_resolves_through_the_adk_registry_without_a_request():
    models = diagnostics._resolve_models(Settings(), lambda settings, role: "gemini-2.5-flash")

    assert all(isinstance(model, Gemini) for model in models.values())
    assert models["producer"].model == "gemini-2.5-flash"


def _offline_infrastructure(monkeypatch) -> None:
    """Fail Docker and Temporal locally so no test reaches a real daemon or service."""

    def no_docker(settings: Settings) -> str:
        del settings
        raise RuntimeError("docker disabled in this test")

    async def no_temporal(settings: Settings):
        del settings
        raise RuntimeError("Failed client connect: disabled in this test")

    monkeypatch.setattr(diagnostics, "_check_docker_images", no_docker)
    monkeypatch.setattr(diagnostics, "connect", no_temporal)


async def test_default_doctor_never_constructs_a_model(monkeypatch, tmp_path):
    _offline_infrastructure(monkeypatch)
    resolve = _resolver(ProbeLlm(model="m"))
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "a"))

    report = await diagnose(settings, resolve_model=resolve)

    assert resolve.calls == []
    assert not any(check["name"].startswith("model_") for check in report["checks"])
    assert report["qualification"] == diagnostics._INFRASTRUCTURE_QUALIFICATION


async def test_doctor_model_appends_model_checks_and_its_qualification(monkeypatch, tmp_path):
    _offline_infrastructure(monkeypatch)
    resolve = _resolver(ProbeLlm(model="m"))
    settings = Settings(
        source_root=str(tmp_path), artifact_root=str(tmp_path / "a"), models=_settings().models
    )

    report = await diagnose(settings, model=True, resolve_model=resolve)

    names = [check["name"] for check in report["checks"]]
    assert names[-7:] == [
        "model_config",
        "model_credentials",
        "model_producer",
        "model_producer_tools",
        "model_auditor",
        "model_intake",
        "model_intake_tools",
    ]
    assert resolve.calls == ["producer", "auditor", "intake"]
    assert report["qualification"] == diagnostics._MODEL_QUALIFICATION
    assert report["ready"] is False  # Docker and Temporal were failed above.


def test_importing_diagnostics_loads_no_adk_or_provider_sdk():
    probe = (
        "import sys; import corsair.entrypoints.diagnostics; "
        "loaded = [n for n in sys.modules if n.split('.')[0] == 'litellm' "
        "or n.startswith('google.adk')]; assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("argv", "expected"), [(["doctor"], False), (["doctor", "--model"], True)])
async def test_cli_doctor_passes_the_model_flag(monkeypatch, capsys, argv, expected):
    seen: list[bool] = []

    async def fake_diagnose(settings: Settings, *, model: bool = False) -> dict:
        del settings
        seen.append(model)
        return {"ready": True, "checks": [], "qualification": "test"}

    monkeypatch.setattr(diagnostics, "diagnose", fake_diagnose)
    args = cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())

    assert await cli.execute(args, Terminal(args)) == 0
    assert seen == [expected]
    assert json.loads(capsys.readouterr().out)["ready"] is True
