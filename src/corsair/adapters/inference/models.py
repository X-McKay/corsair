"""Native ADK model selection; credentials stay in the worker environment."""

from google.adk.models import BaseLlm

from corsair.agents.resources import RoleName
from corsair.settings import ModelSettings, Settings


def model_for_role(settings: Settings | ModelSettings, role: RoleName) -> str | BaseLlm:
    """Resolve a role model without reading or accepting provider credentials.

    Gemini model IDs are left for ADK to resolve natively. LiteLLM receives
    only the allowlisted endpoint and generation controls from ModelSettings;
    provider API keys remain in the worker process environment.
    """

    model_settings = settings.models if isinstance(settings, Settings) else settings
    model_name = getattr(model_settings, role)
    if model_settings.connector == "gemini":
        if model_settings.api_base is not None:
            raise ValueError("api_base is supported only when connector is 'litellm'")
        return model_name

    # LiteLlm is intentionally imported only when configured.  The optional
    # provider dependency is therefore not required for a normal Gemini worker.
    from google.adk.models import LiteLlm

    return LiteLlm(
        model=model_name,
        api_base=model_settings.api_base,
        timeout=model_settings.request_timeout_seconds,
        num_retries=0,
        extra_body=dict(model_settings.extra_body),
    )
