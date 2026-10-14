"""Explicit operator configuration; no source-controlled policy discovery."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import yaml

from corsair.v2.contracts import OperatorConfig, canonical_bytes, digest

DEPENDENCIES = ("pydantic-ai-slim", "pydantic-ai-harness", "pydantic-evals", "temporalio", "openshell", "pydantic")


def load_config(path: Path | str) -> OperatorConfig:
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Use a bounded operator-owned configuration file")
    data = json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())
    config = OperatorConfig.model_validate(data)
    resolve = lambda value: str((path.parent / Path(value).expanduser()).resolve())
    sandbox = config.sandbox.model_copy(update={
        "policy_path": resolve(config.sandbox.policy_path),
        "cli_path": resolve(config.sandbox.cli_path) if config.sandbox.cli_path else None,
        "qualification_path": resolve(config.sandbox.qualification_path) if config.sandbox.qualification_path else None,
    })
    policy = Path(sandbox.policy_path)
    if not policy.is_file() or policy.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("A bounded existing operator policy is required")
    return config.model_copy(update={"storage_root": resolve(config.storage_root), "sandbox": sandbox})


def config_identity(config: OperatorConfig) -> dict:
    policy = Path(config.sandbox.policy_path).read_bytes()
    policy_sha256 = hashlib.sha256(policy).hexdigest()
    qualification = None
    if config.sandbox.qualification_path:
        path = Path(config.sandbox.qualification_path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("Qualification must be an existing bounded regular operator-owned file")
        qualification = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"config_sha256": digest({"config": config.model_dump(mode="json"), "policy_sha256": policy_sha256, "qualification_sha256": qualification}),
            "policy_sha256": policy_sha256, "qualification_sha256": qualification,
            "models": {role: config.model_for(role).model_dump(mode="json") for role in
                       ("analysis", "investigator", "control_author", "exploit_author", "validity", "repair")},
            "budget": config.budget.model_dump(mode="json"), "image": config.sandbox.image}


def build_identity() -> dict:
    root = Path(__file__).parent
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".yaml", ".yml", ".md", ".json") and "__pycache__" not in path.parts:
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Reused v1 primitives are part of the new implementation's provenance.
    import corsair.adapters.git_source as source
    import corsair.adapters.local_artifacts as artifacts
    for module in (artifacts, source):
        files[module.__name__] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    versions = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
    return {"code_sha256": digest(files), "files": files, "dependencies": versions,
            "dependency_sha256": digest(versions), "schema_sha256": digest(OperatorConfig.model_json_schema())}


def safe_error(error: BaseException, config: OperatorConfig | None = None) -> str:
    text = f"{type(error).__name__}: {error}"
    if config:
        if config.temporal_api_key_env:
            key = os.environ.get(config.temporal_api_key_env)
            if key:
                text = text.replace(key, "[REDACTED]")
        profiles = [config.default_model, *config.role_models.values()]
        for profile in profiles:
            secret = os.environ.get(profile.api_key_env)
            if secret and len(secret) >= 4:
                text = text.replace(secret, "[REDACTED]")
    return text[:4096]


def write_config(path: Path, config: OperatorConfig) -> None:
    """Publish a new explicit config; refuse replacement or a symlink destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical_bytes(config))
        stream.flush()
        os.fsync(stream.fileno())
