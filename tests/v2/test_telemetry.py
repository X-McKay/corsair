from __future__ import annotations

import pytest

from corsair.v2.telemetry import configure_local_telemetry, instrumentation


def test_native_instrumentation_defaults_to_content_off() -> None:
    value = instrumentation()
    settings = value.settings
    assert settings.include_content is False
    assert settings.include_binary_content is False
    assert settings.include_model_request_parameters is False
    assert settings.version == 5


def test_local_telemetry_returns_native_instrumentation_without_remote_upload() -> None:
    value = configure_local_telemetry(capture_content=False)
    assert value.settings.include_content is False


def test_requested_otlp_never_silently_becomes_an_inert_configuration(tmp_path) -> None:
    from corsair.v2.contracts import ModelProfile, OperatorConfig, SandboxProfile
    config = OperatorConfig(storage_root=str(tmp_path / "store"), default_model=ModelProfile(model="test"),
        sandbox=SandboxProfile(image="example@sha256:" + "c" * 64, policy_path="/operator/policy.yaml"),
        otlp_endpoint="http://127.0.0.1:4318/v1/traces")
    try:
        value = configure_local_telemetry(config)
    except RuntimeError as error:
        assert "OTLP" in str(error)
    else:
        assert value.settings.include_content is False
