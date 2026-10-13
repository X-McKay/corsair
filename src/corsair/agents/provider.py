"""Compatibility exports for existing local vLLM callers; new selection lives in corsair.inference."""
from corsair.inference.vllm import MODEL_SETTINGS, PROFILE_OVERRIDES, PROVIDERS, LocalModelConfig, local_model, model_settings

__all__ = ['MODEL_SETTINGS', 'PROFILE_OVERRIDES', 'PROVIDERS', 'LocalModelConfig', 'local_model', 'model_settings']
