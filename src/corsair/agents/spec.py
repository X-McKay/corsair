"""Trusted package specs assembled by native PydanticAI with explicit Python authority.

Manifests select only capabilities the role's Python factory admits. They cannot
supply a model, settings, schemas, retries, import strings or operator policy.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.agent.spec import AgentSpec
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models import Model

_ROOT = Path(__file__).resolve().parent
_PATHS = {
    'environment': _ROOT / 'environment/agent.yaml',
    'identification': _ROOT / 'issue_identification/agent.yaml',
    'repository_identification': _ROOT / 'issue_identification/repository-agent.yaml',
    'planning': _ROOT / 'test_planning/agent.yaml',
    'assessment': _ROOT / 'evidence_assessment/agent.yaml',
    'control_authoring': _ROOT / 'control_authoring/agent.yaml',
    'exploit_authoring': _ROOT / 'exploit_authoring/agent.yaml',
}

class SpecMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    config_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    capability_selection: tuple[str, ...] = Field(min_length=1, max_length=16)

class _PackageManifest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1)
    metadata: SpecMetadata

@dataclass(frozen=True)
class LoadedAgentSpec:
    spec: AgentSpec
    metadata: SpecMetadata
    spec_sha256: str
    selection_sha256: str
    native_envelope_sha256: str

    @property
    def identity(self) -> dict[str, str]:
        return {'spec_sha256': self.spec_sha256, 'config_version': self.metadata.config_version,
                'prompt_version': self.metadata.prompt_version,
                'capability_selection_sha256': self.selection_sha256}


def _native_envelope_sha256(native: AgentSpec) -> str:
    # Include native defaults too: mutable containers are not protected by the frozen wrapper.
    return sha256(json.dumps(native.model_dump(mode='json'), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def load_agent_spec(role: str) -> LoadedAgentSpec:
    """Load one fixed package resource; investigated-repository paths are never accepted."""
    if role not in _PATHS:
        raise ValueError(f'unknown trusted agent role: {role}')
    path = _PATHS[role]
    if path.is_symlink():
        raise ValueError('agent manifests must be package-owned files, not symlinks')
    raw = path.read_bytes()
    # Reject forbidden fields before native parsing can interpret any specification.
    import yaml
    package = _PackageManifest.model_validate(yaml.safe_load(raw.decode('utf-8')))
    native = AgentSpec.from_file(path)
    if path.read_bytes() != raw:
        raise ValueError('trusted agent manifest changed during loading')
    metadata = package.metadata
    if len(set(metadata.capability_selection)) != len(metadata.capability_selection):
        raise ValueError('agent capability selection must be unique')
    if native.instructions != package.instructions:
        raise ValueError('native agent instructions must remain a literal package string')
    return LoadedAgentSpec(native, metadata, sha256(raw).hexdigest(),
        sha256(json.dumps(metadata.capability_selection,separators=(',',':')).encode()).hexdigest(),
        _native_envelope_sha256(native))


def build_agent(loaded: LoadedAgentSpec, *, model: Model, deps_type, output_type,
                capability_registry: Mapping[str, Callable], output_retries: int,
                tool_retries: int = 0, validation_context=None,
                extra_capabilities: Sequence[TemporalDurability] = ()) -> Agent:
    """Assemble admitted objects using Agent.from_spec; no arbitrary capability imports."""
    if not isinstance(model, Model):
        raise TypeError('an explicit native Model instance is required')
    if loaded.spec.capabilities:
        raise ValueError('native capability definitions are not admitted in package manifests')
    package = _PackageManifest.model_validate(loaded.spec.model_dump(exclude_unset=True))
    if package.metadata != loaded.metadata:
        raise ValueError('loaded agent metadata differs from its native specification')
    if _native_envelope_sha256(loaded.spec) != loaded.native_envelope_sha256:
        raise ValueError('loaded native specification differs from its original envelope')
    selection = package.metadata.capability_selection
    unknown = set(selection) - set(capability_registry)
    if unknown:
        raise ValueError(f'unknown admitted capability selection: {sorted(unknown)}')
    if len(extra_capabilities) > 1 or any(not isinstance(cap, TemporalDurability) for cap in extra_capabilities):
        raise TypeError('only the existing optional native TemporalDurability capability may be added')
    # Validate all selection before invoking any builders or native assembly.
    capabilities = [capability_registry[key]() for key in selection]
    return Agent.from_spec(loaded.spec, model=model, deps_type=deps_type, output_type=output_type,
        capabilities=[*capabilities, *extra_capabilities],
        retries={'tools':tool_retries,'output':output_retries},validation_context=validation_context)


def manifest_identity(role: str) -> dict[str, str]:
    return load_agent_spec(role).identity


def factory_identity(loaded: LoadedAgentSpec, path: str | Path) -> dict[str, str]:
    """Bind native construction to the fixed package factory and this shared helper."""
    factory_path = Path(path).resolve()
    admitted = {manifest.parent/'agent.py' for manifest in _PATHS.values()}
    if factory_path not in admitted:
        raise ValueError('factory identity requires a fixed package agent.py')
    return loaded.identity | {'factory_source_sha256':sha256(factory_path.read_bytes()).hexdigest(),
                              'shared_helper_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
