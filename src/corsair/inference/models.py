"""Native PydanticAI providers; resolve all agent choices before creating clients."""
from contextlib import AsyncExitStack, asynccontextmanager
import os

from httpx2 import AsyncClient
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from .vllm import LocalModelConfig, local_model
from .config import BedrockConfig, InferenceConfig, OpenAIConfig, VllmConfig, inference_config


def preflight(config):
    if isinstance(config, (LocalModelConfig, OpenAIConfig)) and config.api_key_env:
        if not os.environ.get(config.api_key_env):
            raise ValueError(f'configured credential {config.api_key_env} is unavailable')


@asynccontextmanager
async def configured_model(config, *, http_client: AsyncClient | None = None, bedrock_client=None):
    preflight(config)
    if isinstance(config, LocalModelConfig):
        async with local_model(config, http_client=http_client) as model:
            yield model
        return
    settings = {'max_tokens': config.response_token_limit, 'parallel_tool_calls': False}
    if config.temperature is not None:
        settings['temperature'] = config.temperature
    if isinstance(config, OpenAIConfig):
        key = os.environ[config.api_key_env] if config.api_key_env else 'corsair-explicit-anonymous'
        async with AsyncOpenAI(base_url=config.base_url, api_key=key, organization='', project='', max_retries=0,
                               timeout=config.timeout_seconds, http_client=http_client) as client:
            # Conservative generic Chat Completions profile: never infer proprietary model features from a name.
            profile = OpenAIModelProfile(default_structured_output_mode='tool', supports_json_schema_output=False,
                                         supports_json_object_output=False, openai_supports_strict_tool_definition=False)
            yield OpenAIChatModel(config.model_name, provider=OpenAIProvider(openai_client=client),
                                  profile=profile, settings=settings)
        return
    if not isinstance(config, BedrockConfig):
        raise TypeError('validated model configuration required')
    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.providers.bedrock import BedrockProvider
    import boto3
    from botocore.config import Config
    owned = bedrock_client is None
    if owned:
        # Native AWS credential chain (profile, environment, workload role); no copied credentials or retries.
        bedrock_client = boto3.Session(profile_name=config.aws_profile).client(
            'bedrock-runtime', region_name=config.region,
            config=Config(connect_timeout=config.timeout_seconds, read_timeout=config.timeout_seconds,
                          retries={'total_max_attempts': 1, 'mode': 'standard'}, ignore_configured_endpoint_urls=True))
    try:
        yield BedrockConverseModel(config.model_name, provider=BedrockProvider(bedrock_client=bedrock_client), settings=settings)
    finally:
        if owned:
            bedrock_client.close()


@asynccontextmanager
async def agent_models(config: InferenceConfig | LocalModelConfig, agents):
    selected = inference_config(config)
    resolved = {agent: selected.resolve(agent) for agent in agents}
    for profile in resolved.values():
        preflight(profile)
    async with AsyncExitStack() as stack:
        clients, result = {}, {}
        for agent, profile in resolved.items():
            if profile not in clients:
                clients[profile] = await stack.enter_async_context(configured_model(profile))
            result[agent] = clients[profile]
        yield result
