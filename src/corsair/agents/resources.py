"""Validated role metadata and packaged runtime resources.

Role factories own concrete ADK construction. This module supplies immutable
prompt text, validates declared role capabilities, and admits only the two
small packaged procedural skills before native ADK receives them.
"""

from __future__ import annotations

import hashlib
import stat
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator, model_validator

from corsair.contracts import Contract

if TYPE_CHECKING:
    from google.adk.skills import Skill

RoleName = Literal["producer", "auditor"]

_RESOURCE_PACKAGES: dict[RoleName, str] = {
    "producer": "corsair.agents.producer",
    "auditor": "corsair.agents.auditor",
}
_LOADER_TOOLS = ("load_skill", "load_skill_resource")
_MAX_LOADER_CALLS = 4
_MAX_SKILL_BYTES = 12_000
_MAX_REFERENCE_BYTES = 8_000
_MAX_REFERENCE_COUNT = 4
_MAX_TOTAL_SKILL_BYTES = 24_000


def _admitted_skill_slugs(role: RoleName) -> tuple[str, ...]:
    """Return the finite role-local skill names; this is not a discovery registry."""

    match role:
        case "producer":
            return ("source-grounding",)
        case "auditor":
            return ("semantic-review",)


class AgentSpec(Contract):
    """Declarative role metadata, deliberately separate from wire schemas."""

    name: RoleName
    contract_version: Literal["corsair.agent/2"]
    execution_class: Literal["durable"]
    governance_tier: str = Field(min_length=1, max_length=120)
    risk_path: str = Field(min_length=1, max_length=240)
    tools: list[str]
    source_tools: list[str]
    loader_tools: list[str]
    runtime_skills: list[str]
    loader_call_limit: int = Field(ge=1, le=_MAX_LOADER_CALLS)
    llm_call_limit: int | None = Field(default=None, ge=1, le=4)
    instruction_resource: str = Field(min_length=1, max_length=240)
    schema_ref: str = Field(min_length=1, max_length=240)

    @field_validator("tools", "source_tools", "loader_tools", "runtime_skills")
    @classmethod
    def unique_names(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item for item in value):
            raise ValueError("capability names must be unique and non-empty")
        return value

    @model_validator(mode="after")
    def validated_runtime_layout(self) -> AgentSpec:
        if tuple(self.loader_tools) != _LOADER_TOOLS:
            raise ValueError(f"loader_tools must exactly equal {list(_LOADER_TOOLS)!r}")
        if tuple(self.runtime_skills) != _admitted_skill_slugs(self.name):
            raise ValueError("runtime_skills must exactly equal the role-local admitted skill")
        if self.tools != [*self.source_tools, *self.loader_tools]:
            raise ValueError("tools must preserve source_tools followed by loader_tools")
        if self.name == "producer":
            if self.source_tools != ["read_file", "list_files"]:
                raise ValueError("producer source_tools must exactly expose source reads")
            if self.llm_call_limit is not None:
                raise ValueError("producer LLM calls are bounded by the input and budget")
        elif self.source_tools:
            raise ValueError("auditor must not expose source tools")
        elif self.llm_call_limit is None:
            raise ValueError("auditor must declare its finite native LLM-call limit")
        return self


def _validated_role(role: str) -> RoleName:
    """Narrow a public role string before selecting package resources."""

    if role not in _RESOURCE_PACKAGES:
        raise ValueError(f"unknown Corsair role: {role!r}")
    return role


def _resource_package(role: str) -> str:
    return _RESOURCE_PACKAGES[_validated_role(role)]


def load_agent_spec(role: str) -> AgentSpec:
    """Read and validate a role's declarative metadata from package resources."""

    content = (
        resources.files(_resource_package(role)).joinpath("agent.json").read_text(encoding="utf-8")
    )
    spec = AgentSpec.model_validate_json(content)
    if spec.name != _validated_role(role):
        raise ValueError(f"agent metadata name does not match requested role {role!r}")
    return spec


def prompt_text(role: str) -> str:
    """Return the immutable system prompt used for manifest prompt digests."""

    return (
        resources.files(f"{_resource_package(role)}.instructions")
        .joinpath("system.md")
        .read_text(encoding="utf-8")
    )


def _read_utf8(path: Path, *, byte_limit: int) -> bytes:
    """Read one admitted resource after strict text and executable-file checks."""

    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        raise ValueError(f"runtime skill resource must be a regular file: {path.name!r}")
    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        raise ValueError(f"runtime skill resource must not be executable: {path.name!r}")
    with path.open("rb") as stream:
        content = stream.read(byte_limit + 1)
    if not content or len(content) > byte_limit:
        raise ValueError(f"runtime skill resource exceeds its bounded size: {path.name!r}")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"runtime skill resource must be UTF-8: {path.name!r}") from error
    if b"\x00" in content:
        raise ValueError(f"runtime skill resource must not contain NUL bytes: {path.name!r}")
    return content


def _admitted_skill_files(role: RoleName, slug: str) -> tuple[tuple[str, bytes], ...]:
    """Return bounded raw skill bytes after rejecting non-procedural resources."""

    if slug not in _admitted_skill_slugs(role):
        raise ValueError(f"runtime skill {slug!r} is not admitted for role {role!r}")
    skill_resource = resources.files(_resource_package(role)).joinpath("skills", slug)
    if not skill_resource.is_dir():
        raise ValueError(f"admitted runtime skill package resource is missing: {slug!r}")

    with resources.as_file(skill_resource) as materialized:
        skill_dir = Path(materialized)
        if skill_dir.name != slug or skill_dir.is_symlink() or not skill_dir.is_dir():
            raise ValueError(f"runtime skill must be a packaged directory named {slug!r}")
        children = {child.name: child for child in skill_dir.iterdir()}
        if set(children) - {"SKILL.md", "references"} or "SKILL.md" not in children:
            raise ValueError("runtime skills permit only SKILL.md and references/")

        loaded: list[tuple[str, bytes]] = [
            ("SKILL.md", _read_utf8(children["SKILL.md"], byte_limit=_MAX_SKILL_BYTES))
        ]
        references = children.get("references")
        if references is not None:
            if references.is_symlink() or not references.is_dir():
                raise ValueError("runtime skill references must be a directory")
            files: list[Path] = []
            for path in references.rglob("*"):
                if path.is_symlink():
                    raise ValueError("runtime skill references must not contain symlinks")
                if path.is_dir():
                    continue
                if not path.is_file():
                    raise ValueError("runtime skill references must contain regular files")
                files.append(path)
            files.sort()
            if len(files) > _MAX_REFERENCE_COUNT:
                raise ValueError("runtime skill has too many reference files")
            for reference in files:
                relative = reference.relative_to(references).as_posix()
                if (
                    reference.is_symlink()
                    or reference.suffix != ".md"
                    or not relative
                    or any(part.startswith(".") for part in reference.relative_to(references).parts)
                ):
                    raise ValueError("runtime skill references must be visible Markdown files")
                loaded.append(
                    (
                        f"references/{relative}",
                        _read_utf8(reference, byte_limit=_MAX_REFERENCE_BYTES),
                    )
                )

    if sum(len(content) for _, content in loaded) > _MAX_TOTAL_SKILL_BYTES:
        raise ValueError("runtime skill resources exceed the total byte limit")
    return tuple(loaded)


def _load_runtime_skill(role: RoleName, slug: str) -> Skill:
    """Load one already-validated package resource through ADK's native loader."""

    from google.adk.skills import load_skill_from_dir

    admitted_files = _admitted_skill_files(role, slug)
    skill_resource = resources.files(_resource_package(role)).joinpath("skills", slug)
    with resources.as_file(skill_resource) as materialized:
        skill = load_skill_from_dir(Path(materialized))
    if skill.name != slug:
        raise ValueError(f"runtime skill name does not match its admitted slug {slug!r}")
    if skill.frontmatter.allowed_tools is not None or skill.frontmatter.metadata:
        raise ValueError("runtime skills must not declare tools or state-injection metadata")
    if skill.resources.assets or skill.resources.scripts:
        raise ValueError("runtime skills must not include assets or scripts")
    expected_references = {
        path.removeprefix("references/")
        for path, _ in admitted_files
        if path.startswith("references/")
    }
    if set(skill.resources.references) != expected_references:
        raise ValueError("native runtime skill references do not match packaged resources")
    if any(not isinstance(content, str) for content in skill.resources.references.values()):
        raise ValueError("runtime skill references must remain UTF-8 text")
    return skill


def load_runtime_skills(role: str) -> list[Skill]:
    """Return only the finite packaged procedural skills declared for one role."""

    validated_role = _validated_role(role)
    spec = load_agent_spec(validated_role)
    return [_load_runtime_skill(validated_role, slug) for slug in spec.runtime_skills]


def runtime_skill_digest(role: str) -> str:
    """Hash every raw byte of the role's explicitly admitted runtime resources."""

    digest = hashlib.sha256()
    validated_role = _validated_role(role)
    for slug in load_agent_spec(validated_role).runtime_skills:
        for relative_path, content in _admitted_skill_files(validated_role, slug):
            digest.update(slug.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(relative_path.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(content)
            digest.update(b"\x00")
    return digest.hexdigest()
