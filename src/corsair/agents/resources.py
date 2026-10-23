"""Small, lazy resource helpers shared by the agent packages."""

from __future__ import annotations

import re
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Iterable

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class AgentSpec(BaseModel):
    """The intentionally small, operator-owned contract for one agent package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    version: str = Field(pattern=r"^[0-9]+$")
    owner: str = Field(min_length=1, max_length=256)
    execution: str = Field(pattern=r"^(ephemeral|ephemeral_sandbox)$")
    risk: str = Field(min_length=1, max_length=2_000)
    self_certification: str = Field(pattern=r"^prohibited$")
    contracts: dict[str, str] = Field(min_length=1)
    budgets: tuple[str, ...]
    errors: tuple[str, ...]
    tools: tuple[str, ...]
    skills: tuple[str, ...]

    @field_validator("budgets", "errors", "tools", "skills")
    @classmethod
    def _names_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _CAPABILITY_NAME.fullmatch(value) for value in values) or len(values) != len(set(values)):
            raise ValueError("agent capability names must be unique lowercase slugs")
        return values

    @model_validator(mode="after")
    def _contracts_are_bounded(self) -> "AgentSpec":
        if any(not _NAME.fullmatch(key) or not value.strip() for key, value in self.contracts.items()):
            raise ValueError("agent contracts must have named, nonempty values")
        return self


def package_resource(package: str, relative_path: str) -> Traversable:
    """Return a regular, package-relative resource; traversal and symlink resources are rejected."""
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in relative_path
    ):
        raise ValueError(f"invalid package resource path: {relative_path!r}")
    root = resources.files(package)
    target: Traversable = root
    for part in relative.parts:
        target = target.joinpath(part)
    if not target.is_file():
        raise ValueError(f"missing package resource: {package}/{relative_path}")
    # Installed wheels can expose non-Path Traversables. When a physical path is available, reject every symlink
    # along the requested resource route rather than resolving an operator-owned guide through a link.
    try:
        physical_root = Path(root)
        physical_target = physical_root.joinpath(*relative.parts)
    except TypeError:
        return target
    if physical_root.is_symlink() or any(
        physical_root.joinpath(*relative.parts[:index]).is_symlink()
        for index in range(1, len(relative.parts) + 1)
    ):
        raise ValueError(f"symlinked package resource: {package}/{relative_path}")
    if not physical_target.resolve().is_relative_to(physical_root.resolve()):
        raise ValueError(f"package resource escapes its package: {package}/{relative_path}")
    return target


def load_agent_spec(package: str) -> AgentSpec:
    """Load and validate an agent spec only when a factory is invoked."""
    try:
        value = yaml.safe_load(package_resource(package, "agent.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"invalid agent spec for {package}: {error}") from error
    return AgentSpec.model_validate(value)


def instruction(package: str) -> str:
    """Lazily read an agent's system instruction without an import-time filesystem read."""
    return package_resource(package, "instructions/system.md").read_text(encoding="utf-8")


def skill_names(package: str) -> tuple[str, ...]:
    """Return the spec allowlist after ensuring every listed reviewed skill is present and safe."""
    spec = load_agent_spec(package)
    root = resources.files(package).joinpath("skills")
    try:
        actual = tuple(
            sorted(
                child.name
                for child in root.iterdir()
                if child.is_dir() and child.joinpath("SKILL.md").is_file()
            )
        )
    except (FileNotFoundError, NotADirectoryError):
        actual = ()
    if actual != tuple(sorted(spec.skills)):
        raise ValueError(f"agent spec skill capability drift for {spec.name}")
    for name in spec.skills:
        package_resource(package, f"skills/{name}/SKILL.md")
    return spec.skills


def validate_agent_spec(
    package: str, *, tool_names: Iterable[str], skill_allowlist: Iterable[str] | None = None
) -> AgentSpec:
    """Reject a stale spec before an SDK agent can advertise undeclared capabilities."""
    spec = load_agent_spec(package)
    actual_tools = tuple(sorted(tool_names))
    actual_skills = tuple(sorted(skill_names(package) if skill_allowlist is None else skill_allowlist))
    if actual_tools != tuple(sorted(spec.tools)):
        raise ValueError(f"agent spec tool capability drift for {spec.name}")
    if actual_skills != tuple(sorted(spec.skills)):
        raise ValueError(f"agent spec skill capability drift for {spec.name}")
    return spec


def skill_inventory(skills_dir: Path) -> tuple[str, ...]:
    """Safely inventory packaged ``skills/<slug>/SKILL.md`` playbooks from a physical skills root."""
    root = Path(skills_dir)
    if not root.is_dir() or root.is_symlink():
        return ()
    root_resolved = root.resolve()
    found: list[str] = []
    try:
        children = sorted(root.iterdir(), key=lambda child: child.name)
    except OSError:
        return ()
    for directory in children:
        if not _NAME.fullmatch(directory.name) or not directory.is_dir() or directory.is_symlink():
            continue
        guide = directory / "SKILL.md"
        try:
            safe = (
                guide.is_file() and not guide.is_symlink() and guide.resolve().is_relative_to(root_resolved)
            )
        except OSError:
            safe = False
        if safe:
            found.append(directory.name)
    return tuple(found)


def read_skill_file(skills_dir: Path, name: str, allowed: Iterable[str]) -> str | None:
    """Read one physically safe operator-owned playbook, or ``None`` when it is not allowlisted/available."""
    allowed_names = frozenset(allowed)
    root = Path(skills_dir)
    if not _NAME.fullmatch(name) or name not in allowed_names:
        return None
    directory = root / name
    guide = directory / "SKILL.md"
    try:
        if (
            not root.is_dir()
            or root.is_symlink()
            or not directory.is_dir()
            or directory.is_symlink()
            or not guide.is_file()
            or guide.is_symlink()
            or not guide.resolve().is_relative_to(root.resolve())
        ):
            return None
        return guide.read_text(encoding="utf-8")
    except OSError:
        return None


def skill_body(markdown: str) -> str:
    """Return the original playbook body, excluding a required YAML frontmatter block."""
    if not markdown.startswith("---\n"):
        raise ValueError("skill must begin with YAML frontmatter")
    _, separator, body = markdown[4:].partition("\n---\n")
    if not separator:
        raise ValueError("skill frontmatter is not terminated")
    return body
