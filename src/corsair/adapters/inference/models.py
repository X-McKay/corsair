"""Native ADK model selection; credentials stay in the worker environment."""

from google.adk.models import BaseLlm
from google.genai import types

from corsair.agents.resources import RoleName
from corsair.settings import Decoding, ModelSettings, Settings


def decoding_config(decoding: Decoding) -> types.GenerateContentConfig | None:
    """A role's set sampling parameters as the SDK's native generation config.

    ``None`` when every parameter is unset, so the server's defaults apply. An unset field
    stays ``None`` on the config, which neither the Gemini SDK nor ADK's LiteLLM route sends.
    """

    if decoding.unset:
        return None
    return types.GenerateContentConfig(
        temperature=decoding.temperature, top_p=decoding.top_p, seed=decoding.seed
    )


def model_for_role(
    settings: Settings | ModelSettings,
    role: RoleName,
    *,
    request_timeout_seconds: float | None = None,
) -> str | BaseLlm:
    """Resolve a role model without reading or accepting provider credentials.

    Gemini model IDs are left for ADK to resolve natively. LiteLLM receives
    only the allowlisted endpoint and generation controls from ModelSettings;
    provider API keys remain in the worker process environment.
    ``request_timeout_seconds`` is the per-request bound already lowered to the
    episode (``policies.time_bounds.episode_bounds``); without it the configured
    ``request_timeout_seconds`` applies.
    """

    model_settings = settings.models if isinstance(settings, Settings) else settings
    model_name = getattr(model_settings, role)
    if model_settings.connector == "gemini":
        if model_settings.api_base is not None:
            raise ValueError("api_base is supported only when connector is 'litellm'")
        return model_name

    # LiteLlm is intentionally imported only when configured.  The optional
    # provider dependency is therefore not required for a normal Gemini worker.
    try:
        from google.adk.models import LiteLlm
    except ImportError as error:
        # ADK's own message names google-adk[extensions]; Corsair pins LiteLLM
        # in its providers extra, so name the remedy that matches uv.lock.
        raise ImportError(
            "connector 'litellm' requires Corsair's providers extra; install it with "
            "`just sync` (uv sync --locked --all-extras) or `uv sync --locked --extra providers`"
        ) from error

    return LiteLlm(
        model=model_name,
        api_base=model_settings.api_base,
        timeout=(
            model_settings.request_timeout_seconds
            if request_timeout_seconds is None
            else request_timeout_seconds
        ),
        num_retries=0,
        extra_body=dict(model_settings.extra_body),
    )
