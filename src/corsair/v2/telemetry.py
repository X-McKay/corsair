"""Privacy-preserving native PydanticAI/OTel telemetry configuration."""
from __future__ import annotations

from pydantic_ai.capabilities import Instrumentation

from .contracts import OperatorConfig


def instrumentation(*, capture_content: bool = False) -> Instrumentation:
    """Return native instrumentation with source/prompt content off by default."""
    return Instrumentation.from_spec(
        include_content=capture_content,
        include_binary_content=False,
        include_model_request_parameters=False,
        version=5,
        use_aggregated_usage_attribute_names=True,
    )


def configure_local_telemetry(
    config: OperatorConfig | None = None, *, capture_content: bool | None = None
) -> Instrumentation:
    """Configure local Logfire capture, or a real OTLP exporter when configured.

    Content can be enabled only through this explicit sealed-local operator
    setting. The function never silently uploads to Logfire or pretends an
    unavailable OTLP dependency is configured.
    """
    import logfire

    requested = bool(config.capture_content) if capture_content is None and config is not None else bool(capture_content)
    endpoint = config.otlp_endpoint if config is not None else None
    if endpoint is None:
        logfire.configure(send_to_logfire=False, console=False)
        return instrumentation(capture_content=requested)
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as error:  # a refusal, not an inert config placeholder
        raise RuntimeError("OTLP was requested but the native OTLP exporter dependency is not installed") from error
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    logfire.configure(send_to_logfire=False, console=False)
    return instrumentation(capture_content=requested)


__all__ = ["configure_local_telemetry", "instrumentation"]
