"""Worker settings. Secrets stay in provider environment variables, never in run inputs."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from corsair.contracts import Contract, digest


class ModelSettings(Contract):
    connector: Literal["gemini", "litellm"] = "gemini"
    producer: str = "gemini-2.5-flash"
    auditor: str = "gemini-2.5-flash"
    api_base: str | None = None
    request_timeout_seconds: int = Field(default=120, ge=1, le=300)
    extra_body: dict = Field(default_factory=dict)

    @field_validator("api_base")
    @classmethod
    def no_url_credentials(cls, value: str | None) -> str | None:
        if value:
            url = urlsplit(value)
            if url.scheme not in {"http", "https"} or not url.hostname:
                raise ValueError("api_base must be an HTTP endpoint")
            if url.username or url.password or url.query or url.fragment:
                raise ValueError(
                    "keep endpoint credentials and query parameters out of configuration"
                )
        return value

    @field_validator("extra_body")
    @classmethod
    def safe_generation_options(cls, value: dict) -> dict:
        # Allow generation controls, not credentials or tool overrides.
        if set(value) - {"reasoning", "reasoning_effort", "thinking"}:
            raise ValueError("extra_body supports reasoning controls only")
        return value

    @model_validator(mode="after")
    def guard_litellm_openai_tool_route(self):
        # The producer is a tool-using agent, and ADK pairs its response schema with
        # those tools. On a LiteLLM "openai/" route backed by vLLM, guided decoding
        # then blocks tool calls entirely, silently voiding every producer episode.
        # Reject the combination at config time rather than lose a whole run to it.
        # The auditor is tool-free, so a schema-only "openai/" route is fine for it.
        if self.connector == "litellm" and self.producer.startswith("openai/"):
            raise ValueError(
                "the producer uses tools and ADK pairs its response schema with them; "
                "on a LiteLLM 'openai/' route vLLM's guided decoding blocks tool calls "
                "and voids the run. Serve the producer on a route that does not "
                "guided-decode alongside tools (e.g. a native provider connector)."
            )
        return self


class Settings(Contract):
    artifact_root: str = ".runs"
    source_root: str = "."
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "corsair"
    image: str = "corsair-python:0.1"
    # Recipe-kind to image-tag mapping. ``image`` remains the Python default for
    # compatibility; a kind absent from this map falls back to it. The sandbox resolves
    # the selected tag to an immutable Docker local image ID per run.
    images: dict[str, str] = Field(
        default_factory=lambda: {
            "python.secret_disclosure/1": "corsair-python:0.1",
            "perl.html_injection/1": "corsair-perl:0.1",
        }
    )
    runtime: str = "runc"
    memory_limit: str = "512m"
    nano_cpus: int = Field(default=1_000_000_000, ge=100_000_000)
    pids_limit: int = Field(default=64, ge=16, le=512)
    source_limit_bytes: int = Field(default=8_388_608, ge=1024, le=33_554_432)
    source_limit_files: int = Field(default=1000, ge=1, le=10000)
    # Independent clean negatives required before a case may be EXPLOIT_NOT_DEMONSTRATED,
    # and the cap on independent sessions per case. A lone clean negative stays
    # INCONCLUSIVE; the costly false EXPLOIT_NOT_DEMONSTRATED must be the hardest to reach.
    # The prepare activity admits both into RunManifest, which the workflow reads.
    negative_threshold: int = Field(default=2, ge=2, le=8)
    max_sessions: int = Field(default=2, ge=1, le=8)
    models: ModelSettings = Field(default_factory=ModelSettings)

    def image_for(self, recipe_kind: str) -> str:
        """Return the configured image tag for a recipe kind, or the Python default."""
        return self.images.get(recipe_kind, self.image)

    @property
    def identity(self) -> str:
        return digest(self)


def load_settings(path: str | Path | None = None) -> Settings:
    return Settings.model_validate_json(Path(path).read_text()) if path else Settings()
