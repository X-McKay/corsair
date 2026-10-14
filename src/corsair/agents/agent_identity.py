"""Content identity for package-owned native agents; no loading or construction policy."""
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from pydantic_ai.agent.spec import AgentSpec


def factory_identity(spec: AgentSpec, factory_path: str | Path, manifest_path: str | Path) -> dict[str, str]:
    metadata = spec.metadata or {}
    return {
        'prompt_version': metadata['prompt_version'],
        'harness_version': version('pydantic-ai-harness'),
        'pydantic_ai_version': version('pydantic-ai-slim'),
        'config_version': metadata['config_version'],
        'spec_sha256': sha256(Path(manifest_path).read_bytes()).hexdigest(),
        'factory_source_sha256': sha256(Path(factory_path).read_bytes()).hexdigest(),
        'shared_helper_source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
    }
