"""Worker settings. Secrets stay in provider environment variables, never in run inputs."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

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


class Settings(Contract):
    artifact_root: str = ".runs"
    source_root: str = "."
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "corsair"
    image: str = "corsair-python:0.1"
    runtime: str = "runc"
    memory_limit: str = "512m"
    nano_cpus: int = Field(default=1_000_000_000, ge=100_000_000)
    pids_limit: int = Field(default=64, ge=16, le=512)
    source_limit_bytes: int = Field(default=8_388_608, ge=1024, le=33_554_432)
    source_limit_files: int = Field(default=1000, ge=1, le=10000)
    models: ModelSettings = Field(default_factory=ModelSettings)

    @property
    def identity(self) -> str:
        return digest(self)


def load_settings(path: str | Path | None = None) -> Settings:
    return Settings.model_validate_json(Path(path).read_text()) if path else Settings()
