import asyncio
from contextlib import asynccontextmanager
import json

import pytest
from botocore.config import Config
from httpx2 import AsyncClient, MockTransport, Response
from pydantic import ValidationError
from pydantic_ai import Agent, models
from pydantic_ai.models.test import TestModel

from corsair.inference.config import InferenceConfig, OpenAIConfig, BedrockConfig, load_inference
from corsair.inference.models import agent_models, configured_model


def config():
    return InferenceConfig.model_validate({'models': {
        'fast': {'provider': 'openai_compatible', 'base_url': 'https://model.example/v1', 'model_name': 'fast-model'},
        'deep': {'provider': 'bedrock', 'region': 'us-east-1', 'model_name': 'anthropic.claude-3-haiku-20240307-v1:0'}},
        'default': 'fast', 'agents': {'planning': 'deep', 'assessment': 'deep'}})


def test_agent_resolution_and_legacy_files(tmp_path):
    c = config()
    assert c.resolve('planning').provider == 'bedrock'
    assert c.resolve('authoring').model_name == 'fast-model'
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps({'server': 'vllm', 'base_url': 'https://local.example/v1', 'model_name': 'old'}))
    assert load_inference(path).resolve('environment').provider == 'vllm'
    for update in ({'agents': {'typo': 'fast'}}, {'default': 'missing'}, {'agents': {'planning': 'missing'}}):
        with pytest.raises(ValueError):
            InferenceConfig.model_validate(c.model_dump() | update)
    with pytest.raises(ValueError, match='unknown agent'):
        c.resolve('typo')
    with pytest.raises(ValueError, match='no model'):
        InferenceConfig(models=c.models).resolve('authoring')


def test_all_agents_resolved_before_any_client_and_clients_closed(monkeypatch):
    opened, closed = [], []
    @asynccontextmanager
    async def fake(profile):
        opened.append(profile.provider)
        try:
            yield TestModel(custom_output_text=profile.model_name)
        finally:
            closed.append(profile.provider)
    monkeypatch.setattr('corsair.inference.models.configured_model', fake)
    async def go():
        async with agent_models(config(), ['identification', 'planning', 'assessment']) as selected:
            assert selected['planning'] is selected['assessment']
            assert selected['identification'] is not selected['planning']
        incomplete = InferenceConfig(models=config().models, agents={'planning': 'deep'})
        with pytest.raises(ValueError, match='no model'):
            async with agent_models(incomplete, ['planning', 'authoring']):
                pytest.fail('not entered')
    asyncio.run(go())
    assert opened == ['openai_compatible', 'bedrock']
    assert closed == list(reversed(opened))


def test_native_openai_request_uses_selected_model_and_settings():
    observed = []
    def respond(request):
        data = json.loads(request.content); observed.append(data)
        return Response(200, json={'id': 'response-1', 'object': 'chat.completion', 'created': 1, 'model': data['model'],
                                  'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
                                  'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}})
    async def go():
        async with AsyncClient(transport=MockTransport(respond)) as client, configured_model(
            config().resolve('authoring'), http_client=client) as model:
            with models.override_allow_model_requests(True):
                result = await Agent(model).run('hello')
            assert result.output == 'ok'
    asyncio.run(go())
    assert observed[0]['model'] == 'fast-model'
    assert observed[0].get('parallel_tool_calls', False) is False
    assert 'chat_template_kwargs' not in observed[0] and 'thinking_token_budget' not in observed[0]


def test_native_bedrock_converse_uses_configured_model():
    import boto3
    from botocore.stub import Stubber, ANY
    client = boto3.client('bedrock-runtime', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test',
                          config=Config(retries={'total_max_attempts': 1}))
    from evals.issue_analysis.evaluate import describe_model
    profile = config().resolve('planning')
    with Stubber(client) as stub:
        stub.add_response('converse', {'output': {'message': {'role': 'assistant', 'content': [{'text': 'ok'}]}},
                                      'stopReason': 'end_turn', 'usage': {'inputTokens': 2, 'outputTokens': 1, 'totalTokens': 3},
                                      'metrics': {'latencyMs': 1}},
                          {'modelId': profile.model_name, 'messages': ANY, 'system': [], 'inferenceConfig': {'maxTokens': 2048}})
        async def go():
            async with configured_model(profile, bedrock_client=client) as model:
                identity = describe_model(model)
                assert identity['system'] == 'bedrock' and identity['model_name'] == profile.model_name
                assert identity['sdk_max_retries'] == 0
                with models.override_allow_model_requests(True):
                    result = await Agent(model).run('hello')
                assert result.output == 'ok'
        asyncio.run(go())
        stub.assert_no_pending_responses()
    client.close()


def test_shared_file_and_provider_specific_settings(tmp_path):
    path = tmp_path / 'providers.json'
    path.write_text(json.dumps({'inference': config().model_dump(), 'tickets': {'provider': 'github', 'repository': 'o/r'}}))
    assert load_inference(path).resolve('assessment').provider == 'bedrock'
    with pytest.raises(ValidationError):
        BedrockConfig(provider='bedrock', region='us-east-1', model_name='m', thinking_token_budget=2048)
    path.write_text(json.dumps({'inference': config().model_dump(), 'ticketz': {}}))
    with pytest.raises(ValidationError):
        load_inference(path)


def test_bedrock_native_tool_output_translation():
    import boto3
    from botocore.stub import Stubber, ANY
    from pydantic import BaseModel
    class Answer(BaseModel):
        count: int
    client = boto3.client('bedrock-runtime', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test',
                          config=Config(retries={'total_max_attempts': 1}))
    from evals.issue_analysis.evaluate import describe_model
    profile = config().resolve('planning')
    with Stubber(client) as stub:
        stub.add_response('converse', {'output': {'message': {'role': 'assistant', 'content': [
            {'toolUse': {'toolUseId': 'answer-1', 'name': 'final_result', 'input': {'count': 2}}}]}},
            'stopReason': 'tool_use', 'usage': {'inputTokens': 3, 'outputTokens': 2, 'totalTokens': 5},
            'metrics': {'latencyMs': 1}},
            {'modelId': profile.model_name, 'messages': ANY, 'system': [],
             'inferenceConfig': {'maxTokens': 2048}, 'toolConfig': ANY})
        async def go():
            async with configured_model(profile, bedrock_client=client) as model:
                identity = describe_model(model)
                assert identity['system'] == 'bedrock' and identity['model_name'] == profile.model_name
                assert identity['sdk_max_retries'] == 0
                with models.override_allow_model_requests(True):
                    result = await Agent(model, output_type=Answer).run('count')
                assert result.output.count == 2
                assert result.usage.input_tokens == 3
        asyncio.run(go())
        stub.assert_no_pending_responses()
    client.close()


def test_e2e_stage_profiles_resolve_provider_per_agent_and_reject_cross_provider_controls():
    from evals.fixture_e2e.run import stage_configs
    resolved = stage_configs(config(), {'planning': {'response_token_limit': 8192}})
    assert resolved['planning'].provider == 'bedrock' and resolved['planning'].response_token_limit == 8192
    assert resolved['control_authoring'].provider == 'openai_compatible'
    assert resolved['exploit_authoring'].provider == 'openai_compatible'
    with pytest.raises(ValueError):
        stage_configs(config(), {'planning': {'thinking_mode': 'disabled'}})
    sparse = InferenceConfig(models=config().models, agents={'planning': 'deep'})
    assert set(stage_configs(sparse, {}, ('planning',))) == {'planning'}


def test_configured_credentials_checked_for_all_agents_before_client_open(monkeypatch):
    c = config().model_dump()
    c['models']['fast']['api_key_env'] = 'CORSAIR_MODEL_API_KEY'
    monkeypatch.delenv('CORSAIR_MODEL_API_KEY', raising=False)
    @asynccontextmanager
    async def fail(_):
        pytest.fail('must not create any client before preflight')
        yield
    monkeypatch.setattr('corsair.inference.models.configured_model', fail)
    async def go():
        with pytest.raises(ValueError, match='CORSAIR_MODEL_API_KEY'):
            async with agent_models(InferenceConfig.model_validate(c), ['planning', 'authoring']):
                pass
    asyncio.run(go())


def test_bedrock_owned_client_has_bounded_retries_region_and_cleanup(monkeypatch):
    import boto3
    native = boto3.client('bedrock-runtime', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test',
                          config=Config(retries={'total_max_attempts': 1}))
    seen = {}
    class Session:
        def __init__(self, profile_name):
            seen['profile'] = profile_name
        def client(self, service, **kwargs):
            seen.update(service=service, **kwargs)
            return native
    monkeypatch.setattr(boto3, 'Session', Session)
    monkeypatch.setattr(native, 'close', lambda: seen.update(closed=True))
    async def go():
        async with configured_model(config().resolve('planning')):
            raise RuntimeError('caller failure')
    with pytest.raises(RuntimeError, match='caller failure'):
        asyncio.run(go())
    assert seen['region_name'] == 'us-east-1' and seen['service'] == 'bedrock-runtime'
    assert seen['config'].retries['total_max_attempts'] == 1
    assert seen['config'].ignore_configured_endpoint_urls and seen['closed']


def test_e2e_cli_only_requires_profiles_for_selected_live_agents(tmp_path, monkeypatch):
    from evals.fixture_e2e import run
    provider = tmp_path / 'providers.json'
    provider.write_text(InferenceConfig(models=config().models, agents={'planning': 'deep'}).model_dump_json())
    controls = tmp_path / 'controls.json'
    controls.write_text(json.dumps({'planning': {'response_token_limit': 4096}}))
    monkeypatch.setattr('sys.argv', ['fixture-e2e', '--provider-config', str(provider), '--live', 'planning',
                                   '--stage-profiles', str(controls), '--evidence', str(tmp_path / 'evidence')])
    async def admitted(*args):
        raise RuntimeError('configuration admitted without dispatch')
    monkeypatch.setattr(run, 'main_async', admitted)
    with pytest.raises(RuntimeError, match='configuration admitted without dispatch'):
        run.main()


@pytest.mark.parametrize('provider,allowed', [('vllm', 'CORSAIR_LOCAL_MODEL_API_KEY'),
                                              ('openai_compatible', 'CORSAIR_MODEL_API_KEY')])
def test_model_credentials_cannot_reference_ticket_or_ambient_secrets(provider, allowed):
    from corsair.inference.config import MODEL_CONFIG
    base = dict(provider=provider, base_url='https://model.example/v1', model_name='model')
    assert MODEL_CONFIG.validate_python(base | {'api_key_env': allowed}).api_key_env == allowed
    for name in ('CORSAIR_GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'PATH'):
        with pytest.raises(ValidationError):
            MODEL_CONFIG.validate_python(base | {'api_key_env': name})


def test_larger_local_limits_survive_legacy_and_named_profile_loading():
    from corsair.inference.config import inference_config
    from corsair.agents.provider import LocalModelConfig
    for cap in (24576, 32768):
        legacy = LocalModelConfig(server='vllm', base_url='https://local.example/v1', model_name='model',
                                  timeout_seconds=300, response_token_limit=cap)
        named = inference_config(legacy).resolve('authoring')
        assert named.timeout_seconds == 300 and named.response_token_limit == cap
