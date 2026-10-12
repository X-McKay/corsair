"""Compatibility re-export: the provider seam now has a second consumer and lives in ``agents.provider``."""

from ..provider import MODEL_SETTINGS, PROFILE_OVERRIDES, PROVIDERS, LocalModelConfig, local_model, model_settings

__all__ = ["MODEL_SETTINGS", "PROFILE_OVERRIDES", "PROVIDERS", "LocalModelConfig", "local_model", "model_settings"]
